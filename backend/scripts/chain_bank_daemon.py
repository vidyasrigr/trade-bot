"""
Track 1 — MarketData chain-banking daemon (CONSTRAINT_RUNBOOK_2026-06-19).

The ONE hard bottleneck: MarketData chains (10k credits/day, ~258 cr/symbol).
This daemon spends the full daily budget every day and never lets an allotment go
unspent: it banks chains for un-banked core names until credits hit the floor, then
SLEEPS until the documented reset and AUTO-RESUMES. Survives across days.

Faithfulness: it banks via the real `run_vrp_backtest` path (entry chain + daily MTM
marks + exit), so the cache contains exactly the (symbol, expiry, day) parquets the
VRP/skew/IV validations request — no guessing dates/expiries.

Credit accounting: reads MarketData's X-Api-Ratelimit-Remaining / -Reset headers
(captured by MarketDataClient._capture_rate_limit). Stops a banking pass when
remaining < FLOOR (V's standing rule: end each day <150 unspent), then sleeps until
the reset timestamp + buffer and resumes.

Run:
  python -m scripts.chain_bank_daemon            # forever, auto-resume at reset
  python -m scripts.chain_bank_daemon --once     # one pass until floor/exhausted, exit
  python -m scripts.chain_bank_daemon --max 10   # cap names this pass (testing)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

from loguru import logger

from backtest.marketdata_source import MarketDataHistoricalSource, DEFAULT_CACHE_ROOT, _safe

# Windows banked per symbol: train + walk-forward (options are 5y-capped on Starter).
BANK_START = date(2021, 7, 1)
BANK_END = date(2026, 6, 30)

REBALANCE_DAYS = 21              # monthly snapshot cadence (matches the XS signals)
TARGET_DTE = 45                 # VRP/skew canonical
MIN_DTE, MAX_DTE = 25, 60       # acceptable expiry window around target
FLOOR = 150                       # stop when daily credits remaining < this (V's rule)
RESET_BUFFER_S = 120             # wait past the reset before resuming
PROGRESS_LOG = DEFAULT_CACHE_ROOT / "_bank_progress.log"

# Core-200 seed (sector-diverse, liquid, optionable) from the runbook. Tonight's
# bank works through this in order; ~38/day means the list fills over ~5-7 days.
# Priority note: once Track-3's free sweep flags high-IC names, reorder to those
# first — for now sector-diverse order.
CORE_200 = [
    # mega-cap tech / semis
    "NVDA", "AMD", "AVGO", "MU", "ARM", "MRVL", "INTC", "QCOM", "TXN",
    # software
    "MSFT", "CRM", "ORCL", "ADBE", "NOW", "PANW", "CRWD", "NET", "DDOG", "SNOW", "PLTR",
    # internet
    "GOOGL", "META", "AMZN", "NFLX", "UBER", "ABNB", "BKNG",
    # consumer
    "AAPL", "TSLA", "COST", "WMT", "HD", "NKE", "SBUX", "MCD",
    # financials
    "JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "V", "MA", "AXP",
    # health
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ISRG",
    # energy
    "XOM", "CVX", "COP", "SLB",
    # industrials
    "CAT", "DE", "BA", "HON", "GE",
    # liquid ETFs (options core — explicitly included; excluded from equity universe)
    "SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "SMH", "DIA",
    # --- extension toward 200 (liquid, optionable, tight spreads, high OI) ---
    # more semis / hardware
    "ON", "MCHP", "ADI", "KLAC", "LRCX", "AMAT", "ASML", "TSM", "WDC", "STX", "DELL", "HPQ", "SMCI",
    # more software / internet
    "INTU", "WDAY", "TEAM", "ZS", "MDB", "HUBS", "TTD", "SHOP", "SQ", "PYPL", "COIN", "ROKU", "SPOT", "PINS", "SNAP",
    # comms / media
    "DIS", "CMCSA", "T", "VZ", "TMUS", "WBD",
    # consumer disc / retail
    "LOW", "TGT", "LULU", "CMG", "ORLY", "AZO", "DG", "DLTR", "RCL", "CCL", "MAR", "F", "GM", "RIVN", "LCID",
    # consumer staples
    "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "KHC",
    # financials / payments / insurance
    "BLK", "SPGI", "CB", "PGR", "USB", "PNC", "TFC", "COF", "BK", "AIG", "MET", "PRU",
    # healthcare / pharma / biotech
    "ABT", "DHR", "BMY", "AMGN", "GILD", "CVS", "CI", "HUM", "VRTX", "REGN", "MRNA", "BIIB", "ZTS", "BSX", "MDT", "SYK",
    # energy / materials
    "EOG", "MPC", "PSX", "VLO", "OXY", "HAL", "DVN", "FCX", "NEM", "LIN", "APD", "NUE",
    # industrials / transports / defense
    "UPS", "FDX", "LMT", "RTX", "NOC", "GD", "UNP", "CSX", "MMM", "EMR", "ETN", "ITW", "PH", "DAL", "UAL", "LUV",
    # utilities / REITs
    "NEE", "DUK", "SO", "AMT", "PLD", "O",
    # more high-vol single names
    "DKNG", "AFRM", "U", "RBLX", "DASH", "HOOD", "SOFI", "CVNA", "W", "ETSY", "ZM", "DOCU", "OKTA", "TWLO",
    # sector / vol ETFs
    "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "GLD", "SLV", "TLT", "HYG", "EEM", "EFA", "ARKK", "GDX", "USO", "UNG", "VXX",
]


# dedupe, preserve order
CORE_200 = list(dict.fromkeys(CORE_200))


def _banked_symbols() -> set[str]:
    """Symbols that already have at least one non-trivial cached chain parquet."""
    root = DEFAULT_CACHE_ROOT
    out: set[str] = set()
    if not root.exists():
        return out
    for d in root.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        # at least one parquet > 3KB (an empty marker is ~1-2KB)
        for f in d.glob("*/*.parquet"):
            try:
                if f.stat().st_size > 3000:
                    out.add(d.name)
                    break
            except OSError:
                continue
    return out


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_LOG, "a") as f:
        f.write(line + "\n")
    logger.info(msg)


async def _refresh_credits(source) -> dict:
    """One cheap real API call to populate the rate-limit headers."""
    try:
        await source.client.get_expirations("SPY", as_of=date.today().isoformat())
    except Exception as e:
        logger.debug(f"credit preflight call failed (likely rate-limited): {e}")
    return source.client.rate_limit


def _seconds_until_reset(rl: dict) -> float:
    reset = rl.get("reset")
    now = time.time()
    if reset and reset > now:
        return (reset - now) + RESET_BUFFER_S
    # fallback: MarketData resets ~09:30 ET (13:30 UTC). Sleep to next 13:35 UTC.
    nxt = datetime.now(timezone.utc).replace(hour=13, minute=35, second=0, microsecond=0)
    if nxt.timestamp() <= now:
        nxt = nxt.replace(day=nxt.day + 1)
    return max(60.0, nxt.timestamp() - now)


async def _rebalance_dates(source, sym: str) -> list[date]:
    """Monthly snapshot dates from the cached SPY trading calendar (0 credits)."""
    cal = await source.trading_days(sym, BANK_START, BANK_END)
    if not cal:
        # fall back to SPY calendar if the per-symbol calendar is empty
        cal = await source.trading_days("SPY", BANK_START, BANK_END)
    return cal[::REBALANCE_DAYS]


async def _pick_expiry(source, sym: str, as_of: date) -> date | None:
    """~45-DTE expiry in [MIN_DTE, MAX_DTE] listed as-of `as_of` (counted call)."""
    exps = await source.expirations(sym, as_of)
    best, best_gap = None, 1e9
    for e in exps:
        try:
            ed = date.fromisoformat(e[:10])
        except ValueError:
            continue
        dte = (ed - as_of).days
        if MIN_DTE <= dte <= MAX_DTE and abs(dte - TARGET_DTE) < best_gap:
            best, best_gap = ed, abs(dte - TARGET_DTE)
    return best


async def _bank_one(source, sym: str) -> None:
    """Bank one ~45-DTE chain snapshot per monthly rebalance date across the window.

    No yfinance dependency: dates come from the cached calendar, expiry from the
    (counted) expirations endpoint, chain via _load_chain (persists parquet).
    """
    before = source.client.rate_limit.get("remaining")
    dates = await _rebalance_dates(source, sym)
    banked = 0
    for d in dates:
        # stop early if we cross the floor mid-symbol
        rem = source.client.rate_limit.get("remaining")
        if rem is not None and rem < FLOOR:
            break
        expiry = await _pick_expiry(source, sym, d)
        if expiry is None:
            continue
        try:
            await source._load_chain(sym, expiry, d)   # persists parquet
            banked += 1
        except Exception as e:
            logger.debug(f"bank {sym} {d}: {e}")
    after = source.client.rate_limit.get("remaining")
    spent = (before - after) if (before is not None and after is not None) else "?"
    st = source.stats
    _log(f"bank {sym}: snapshots={banked}/{len(dates)} credits_spent={spent} "
         f"remaining={after} api_fetches={st['api_fetches']}")


async def run(once: bool, max_names: int | None) -> None:
    source = MarketDataHistoricalSource()
    while True:
        rl = await _refresh_credits(source)
        remaining = rl.get("remaining")
        targets = [s for s in CORE_200 if s not in _banked_symbols()]
        if max_names:
            targets = targets[:max_names]

        if not targets:
            _log("all core-200 names banked. sleeping 1h then re-scan.")
            if once:
                return
            await asyncio.sleep(3600)
            continue

        if remaining is not None and remaining < FLOOR:
            sleep_s = _seconds_until_reset(rl)
            _log(f"credits {remaining} < floor {FLOOR}. {len(targets)} names left. "
                 f"sleeping {sleep_s/3600:.1f}h until reset.")
            if once:
                return
            await asyncio.sleep(sleep_s)
            continue

        _log(f"banking pass: remaining={remaining}, {len(targets)} names queued "
             f"(next: {targets[:5]})")
        for sym in targets:
            rl = source.client.rate_limit
            if rl.get("remaining") is not None and rl["remaining"] < FLOOR:
                _log(f"hit floor mid-pass (remaining={rl['remaining']}). pausing pass.")
                break
            await _bank_one(source, sym)

        if once and (source.client.rate_limit.get("remaining") or 0) < FLOOR:
            _log("once: floor reached, exiting.")
            return
        if once and not [s for s in CORE_200 if s not in _banked_symbols()][:1]:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()
    already = _banked_symbols()
    print(f"chain-bank daemon: {len(already)} core names already banked; "
          f"target core-200 seed={len(CORE_200)}. floor={FLOOR}.")
    asyncio.run(run(args.once, args.max))


if __name__ == "__main__":
    main()
