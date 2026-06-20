"""
FMP 24/7 ingest daemon.

Runs forever. Saturates the FMP rate limit (default plan: 300 calls/min) to bank
every FMP-sourced dataset the signal registry needs, for the full listed universe,
to disk. Once banked, every backtest re-reads from disk for free.

Design:
  - Token-bucket paced to FMP_DAEMON_RATE calls/min (default 280, leaving headroom).
  - Priority queue: highest-signal-value endpoints first, so partial completion still
    unblocks the most valuable signals (earnings dates -> PEAD, insider -> insider_cluster).
  - Idempotent: a (endpoint, symbol) whose disk file is younger than its TTL is skipped
    with NO api call. Re-runs are cheap; a killed daemon resumes where it stopped.
  - Persistent disk cache at data/cache/fmp/<endpoint>/<symbol>.json (survives restarts,
    unlike the Redis TTL cache the live app uses).
  - Hourly progress line to data/cache/fmp/_daemon_progress.log (calls made, cache hits,
    queue remaining) so the journal can quote real throughput.

Run:
  python -m scripts.fmp_daemon                 # full universe, all endpoints, forever
  python -m scripts.fmp_daemon --once          # one full pass then exit
  python -m scripts.fmp_daemon --universe 500  # cap to 500 most-liquid names
  python -m scripts.fmp_daemon --endpoints earnings,insider   # subset

NOTE ON ENDPOINTS: FMP migrated legacy v3/v4 paths to the `stable/` namespace in
Aug-2025 (PCO confirmed legacy is dead app-wide). The ENDPOINTS table below uses the
paths we believe are live; on first run the daemon logs the HTTP status of each distinct
endpoint once. If any logs a non-200, fix that one row — the rest keep flowing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from core.config import settings

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

RATE_PER_MIN = int(os.environ.get("FMP_DAEMON_RATE", "280"))   # leave 20/min headroom
BASE_URL = "https://financialmodelingprep.com/"
CACHE_ROOT = Path(os.environ.get("FMP_CACHE_DIR", "data/cache/fmp"))
PROGRESS_LOG = CACHE_ROOT / "_daemon_progress.log"
HTTP_TIMEOUT = 20.0


@dataclass
class Endpoint:
    """One FMP dataset. `path` may contain {symbol}; `query` is extra params."""
    name: str
    path: str
    query: dict = field(default_factory=dict)
    ttl_days: int = 1           # re-fetch cadence; historical/static use large values
    per_symbol: bool = True     # False = one universe-wide call, symbol ignored
    priority: int = 50          # lower = fetched first


# Ordered by signal value. Earnings + insider + short-interest unblock the most
# signals, so they lead. Static reference data (profile) is cheap and rarely changes.
ENDPOINTS: list[Endpoint] = [
    # --- unblocks PEAD + beat_and_raise + earnings guards ---
    Endpoint("earnings",        "stable/earnings",             {"limit": 200}, ttl_days=2,  priority=10),
    Endpoint("earnings_surprise","stable/earnings-surprises-bulk", {},         ttl_days=2,  priority=11, per_symbol=False),
    # --- unblocks insider_cluster + insider_analyst_combo ---
    Endpoint("insider",         "stable/insider-trading/search", {"limit": 200}, ttl_days=1, priority=20),
    # --- unblocks short_squeeze ---
    Endpoint("short_interest",  "stable/short-interest",       {},             ttl_days=1,  priority=30),
    # --- sizing + sector_dispersion + universe metadata ---
    Endpoint("profile",         "stable/profile",              {},             ttl_days=30, priority=40),
    Endpoint("float",           "stable/shares-float",         {},             ttl_days=7,  priority=41),
    # --- unblocks analyst_revision_cascade ---
    # NOTE: period=quarter is a premium param on Starter (402). Annual is allowed.
    Endpoint("analyst_est",     "stable/analyst-estimates",    {"period": "annual", "limit": 40}, ttl_days=2, priority=50),
    Endpoint("price_target",    "stable/price-target-summary", {},             ttl_days=2,  priority=51),
    Endpoint("grades",          "stable/grades-historical",    {"limit": 100}, ttl_days=2,  priority=52),
    # --- fundamental engine signal (annual on Starter; bumped priority so the
    #     quality factors unblock — 0619.3 Track D) ---
    Endpoint("income",          "stable/income-statement",     {"period": "annual", "limit": 10}, ttl_days=7, priority=33),
    Endpoint("balance_sheet",   "stable/balance-sheet-statement", {"period": "annual", "limit": 10}, ttl_days=7, priority=34),
    Endpoint("cash_flow",       "stable/cash-flow-statement",  {"period": "annual", "limit": 10}, ttl_days=7, priority=35),
    Endpoint("ratios",          "stable/ratios",               {"period": "annual", "limit": 10}, ttl_days=7, priority=36),
    Endpoint("key_metrics",     "stable/key-metrics",          {"period": "annual", "limit": 10}, ttl_days=7, priority=37),
    # --- sentiment (replaces AlphaVantage spend) ---
    Endpoint("news",            "stable/news/stock",           {"limit": 100}, ttl_days=1,  priority=70),
]


# --------------------------------------------------------------------------- #
# Rate limiter (token bucket)
# --------------------------------------------------------------------------- #

class RateLimiter:
    def __init__(self, per_min: int):
        self.interval = 60.0 / per_min
        self._next = time.monotonic()

    async def wait(self):
        now = time.monotonic()
        if now < self._next:
            await asyncio.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


# --------------------------------------------------------------------------- #
# Cache I/O
# --------------------------------------------------------------------------- #

def _cache_path(endpoint: str, key: str) -> Path:
    safe = key.replace("/", "_") or "_universe"
    return CACHE_ROOT / endpoint / f"{safe}.json"


def _fresh(path: Path, ttl_days: int) -> bool:
    if not path.exists():
        return False
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    return age_days < ttl_days


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Daemon
# --------------------------------------------------------------------------- #

class Stats:
    def __init__(self):
        self.calls = 0
        self.hits = 0
        self.errors = 0
        self.start = time.monotonic()

    def log(self, queue_left: int, note: str = ""):
        mins = max((time.monotonic() - self.start) / 60.0, 0.01)
        line = (f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"calls={self.calls} hits={self.hits} errors={self.errors} "
                f"rate={self.calls/mins:.0f}/min queue_left={queue_left} {note}\n")
        PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(PROGRESS_LOG, "a") as f:
            f.write(line)
        print(line, end="")


async def _fetch(client: httpx.AsyncClient, ep: Endpoint, symbol: str) -> object | None:
    params = dict(ep.query)
    params["apikey"] = settings.FMP_API_KEY
    if ep.per_symbol:
        params["symbol"] = symbol
    url = BASE_URL + ep.path
    resp = await client.get(url, params=params)
    if resp.status_code != 200:
        raise RuntimeError(f"{ep.name} HTTP {resp.status_code}: {resp.text[:120]}")
    return resp.json()


async def run(universe: list[str], endpoints: list[Endpoint], once: bool):
    if not settings.FMP_API_KEY:
        raise SystemExit("FMP_API_KEY not set. Export it before running the daemon.")

    limiter = RateLimiter(RATE_PER_MIN)
    stats = Stats()
    probed: set[str] = set()      # endpoints we've logged a first-call status for
    dead: set[str] = set()        # endpoints whose first call failed (tier-locked / bad path)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        while True:
            # Build the work list: (priority, endpoint, symbol) for everything stale.
            # Skip endpoints whose probe failed (402/404) so we don't burn a call per
            # symbol per pass on a permanently-restricted endpoint.
            work: list[tuple[int, Endpoint, str]] = []
            for ep in sorted(endpoints, key=lambda e: e.priority):
                if ep.name in dead:
                    continue
                syms = universe if ep.per_symbol else ["_universe"]
                for sym in syms:
                    if not _fresh(_cache_path(ep.name, sym), ep.ttl_days):
                        work.append((ep.priority, ep, sym))

            if not work:
                stats.log(0, note="QUEUE EMPTY - all fresh")
                if once:
                    return
                await asyncio.sleep(3600)      # everything fresh; re-check hourly
                continue

            last_log = time.monotonic()
            for _, ep, sym in work:
                if ep.name in dead:                 # probe failed earlier this pass
                    continue
                path = _cache_path(ep.name, sym)
                if _fresh(path, ep.ttl_days):       # filled by a concurrent pass
                    stats.hits += 1
                    continue
                await limiter.wait()
                try:
                    data = await _fetch(client, ep, sym)
                    stats.calls += 1
                    if ep.name not in probed:
                        probed.add(ep.name)
                        stats.log(len(work), note=f"PROBE {ep.name} OK")
                    if data:                         # don't persist empty/None
                        _write(path, data)
                except Exception as e:
                    stats.errors += 1
                    if ep.name not in probed:
                        probed.add(ep.name)
                        dead.add(ep.name)   # restricted/bad path -> skip rest of its symbols
                        stats.log(len(work), note=f"PROBE {ep.name} FAIL (endpoint disabled this run): {e}")

                if time.monotonic() - last_log > 3600:     # hourly heartbeat
                    stats.log(len(work))
                    last_log = time.monotonic()

            stats.log(0, note="pass complete")
            if once:
                return


def _load_universe(cap: int | None) -> list[str]:
    """Full listed universe via the keyless directory fetch (no Redis needed).

    NOTE: symbols come back alphabetically sorted, not liquidity-ordered, so a --cap
    takes the alphabetical head. For full-universe banking (the default) order is
    irrelevant; only --universe N is affected. Endpoint priority drives signal value.
    """
    import asyncio as _a
    from data.universe import fetch_listed_symbols
    syms = _a.run(fetch_listed_symbols(include_other_listed=True))
    if cap:
        syms = syms[:cap]
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one full pass then exit")
    ap.add_argument("--universe", type=int, default=None, help="cap to N most-liquid names")
    ap.add_argument("--endpoints", type=str, default=None, help="comma list of endpoint names")
    args = ap.parse_args()

    eps = ENDPOINTS
    if args.endpoints:
        wanted = {x.strip() for x in args.endpoints.split(",")}
        eps = [e for e in ENDPOINTS if e.name in wanted]

    universe = _load_universe(args.universe)
    print(f"FMP daemon: {len(universe)} symbols x {len(eps)} endpoints "
          f"@ {RATE_PER_MIN}/min -> {CACHE_ROOT}")
    asyncio.run(run(universe, eps, args.once))


if __name__ == "__main__":
    main()
