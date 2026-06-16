"""
CFTC Commitments of Traders — weekly speculator vs commercial positioning.

Free, public, updated every Friday for the prior Tuesday. We track the most
liquid futures: SPX (E-mini), VIX, gold, oil, 10y treasury, dollar index.

Net non-commercial positioning is the classic contrarian indicator — when
specs are max-long, reversal probability rises; when max-short, bounce likely.

CFTC publishes legacy + disaggregated reports. We use the disaggregated short
report's JSON endpoint (Socrata API), which exposes:
  - Money manager longs/shorts/spreads
  - Producer/merchant longs/shorts
  - Open interest

Output: per-contract dataclass with the long_specs / short_specs / net /
percentile-of-trailing-3-years for the strategist prompt.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx
from loguru import logger

from core.redis_client import cache_get, cache_set


SOCRATA_BASE = "https://publicreporting.cftc.gov/resource"
DATASET_LEGACY_FUT = "6dca-aqww"  # Commitments of Traders — Futures Only — Legacy report

# Contract codes per CFTC legacy report
TRACKED_CONTRACTS = {
    "spx_emini":  "13874A",
    "vix":        "1170E1",
    "gold":       "088691",
    "wti_oil":    "067651",
    "us_10y":     "043602",
    "dxy":        "098662",
}

CACHE_TTL_S = 86400  # daily — file refreshes once a week, daily cache is fine


@dataclass
class CotPosition:
    contract: str
    as_of: date
    noncomm_long: int
    noncomm_short: int
    noncomm_spread: int
    comm_long: int
    comm_short: int
    open_interest: int

    @property
    def noncomm_net(self) -> int:
        return self.noncomm_long - self.noncomm_short

    @property
    def noncomm_net_pct_of_oi(self) -> float:
        if self.open_interest == 0:
            return 0.0
        return self.noncomm_net / self.open_interest


async def _fetch_contract_history(code: str, weeks: int = 156) -> list[CotPosition]:
    cache_key = f"cot:{code}:{weeks}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        rows = orjson.loads(cached)
        return [CotPosition(
            contract=r["contract"], as_of=date.fromisoformat(r["as_of"]),
            noncomm_long=r["noncomm_long"], noncomm_short=r["noncomm_short"],
            noncomm_spread=r["noncomm_spread"],
            comm_long=r["comm_long"], comm_short=r["comm_short"],
            open_interest=r["open_interest"],
        ) for r in rows]

    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{SOCRATA_BASE}/{DATASET_LEGACY_FUT}.json",
                params={
                    "$where": f"cftc_contract_market_code='{code}' "
                              f"AND report_date_as_yyyy_mm_dd > '{cutoff}'",
                    "$order": "report_date_as_yyyy_mm_dd DESC",
                    "$limit": weeks * 2,
                },
            )
        if resp.status_code != 200:
            logger.debug(f"CFTC fetch for {code}: status={resp.status_code}")
            return []
        rows = resp.json() or []
    except Exception as e:
        logger.debug(f"CFTC fetch for {code} failed: {e}")
        return []

    out: list[CotPosition] = []
    for r in rows:
        try:
            out.append(CotPosition(
                contract=code,
                as_of=date.fromisoformat(r["report_date_as_yyyy_mm_dd"][:10]),
                noncomm_long=int(float(r.get("noncomm_positions_long_all") or 0)),
                noncomm_short=int(float(r.get("noncomm_positions_short_all") or 0)),
                noncomm_spread=int(float(r.get("noncomm_postions_spread_all") or 0)),
                comm_long=int(float(r.get("comm_positions_long_all") or 0)),
                comm_short=int(float(r.get("comm_positions_short_all") or 0)),
                open_interest=int(float(r.get("open_interest_all") or 0)),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    if out:
        import orjson
        await cache_set(cache_key, orjson.dumps([{
            "contract": p.contract, "as_of": p.as_of.isoformat(),
            "noncomm_long": p.noncomm_long, "noncomm_short": p.noncomm_short,
            "noncomm_spread": p.noncomm_spread,
            "comm_long": p.comm_long, "comm_short": p.comm_short,
            "open_interest": p.open_interest,
        } for p in out]).decode(), ttl=CACHE_TTL_S)
    return out


@dataclass
class CotSnapshot:
    contract: str
    latest: CotPosition
    net_pct_3y: float          # 0..1 percentile of net positioning vs 3y history
    extreme: str | None        # 'spec_max_long' / 'spec_max_short' / None


def _percentile(history: list[int], current: int) -> float:
    if not history:
        return 0.5
    below = sum(1 for v in history if v < current)
    return below / len(history)


async def cot_snapshot(name: str) -> CotSnapshot | None:
    code = TRACKED_CONTRACTS.get(name)
    if code is None:
        return None
    history = await _fetch_contract_history(code, weeks=156)
    if not history:
        return None
    latest = history[0]
    nets = [h.noncomm_net for h in history]
    pct = _percentile(nets, latest.noncomm_net)
    extreme = None
    if pct >= 0.95:
        extreme = "spec_max_long"
    elif pct <= 0.05:
        extreme = "spec_max_short"
    return CotSnapshot(contract=name, latest=latest, net_pct_3y=round(pct, 3), extreme=extreme)


async def all_cot_snapshots() -> dict[str, CotSnapshot]:
    results = await asyncio.gather(*[cot_snapshot(name) for name in TRACKED_CONTRACTS])
    return {snap.contract: snap for snap in results if snap is not None}
