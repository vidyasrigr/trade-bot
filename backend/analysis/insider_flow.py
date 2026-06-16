"""
Insider opportunistic-buy detector (Cohen, Malloy & Pomorski 2012, *JF*).

Pulls FMP's `v4/insider-trading` feed (already used in lt_scoring.py:476 — no
new data dependency), filters to open-market purchases ("P-Purchase"), and
classifies each into:

  - routine: same insider buys within ±10 calendar days of the same month in
    at least 2 prior years (e.g. quarterly buying programs)
  - opportunistic: everything else

The Cohen-Malloy result: opportunistic buys predict ~6%/yr abnormal returns;
routine buys predict zero. So we only fire on opportunistic CLUSTERS:
  ≥3 opportunistic buys by ≥2 distinct insiders within 30 days.

Output written to `insider_signals` (migration 012) and surfaced to the trader
via the cross-section rank context (signal_type=insider_cluster).
"""

from __future__ import annotations

import asyncio
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set

FMP_ENDPOINT = "https://financialmodelingprep.com/api/v4/insider-trading"
CACHE_TTL_S = 86400  # 24h — insider filings update slowly

# Cluster thresholds
MIN_OPPORTUNISTIC = 3
MIN_DISTINCT_INSIDERS = 2
CLUSTER_WINDOW_DAYS = 30


async def _fetch_insider_trades(symbol: str, limit: int = 100) -> list[dict]:
    """FMP v4/insider-trading for one symbol — cached 24h. Returns [] on any error."""
    if not settings.FMP_API_KEY:
        return []
    cache_key = f"insider_flow:{symbol}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FMP_ENDPOINT, params={
                "symbol": symbol, "limit": limit, "apikey": settings.FMP_API_KEY,
            })
            data = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.debug(f"insider_flow: FMP fetch failed for {symbol}: {e}")
        return []

    if not isinstance(data, list):
        return []
    import orjson
    await cache_set(cache_key, orjson.dumps(data).decode(), ttl=CACHE_TTL_S)
    return data


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_open_market_buy(trade: dict) -> bool:
    """FMP transactionType is 'P-Purchase' for open-market buys."""
    tt = str(trade.get("transactionType") or "").lower()
    return tt.startswith("p-purchase") or tt == "p"


def _classify_routine(trades: list[dict]) -> dict[int, bool]:
    """
    For each trade index, return True if it looks routine.

    Routine ≡ same insider has at least one buy in the same calendar month
    within ±10 days, in at least 2 prior calendar years.
    """
    by_insider: dict[str, list[tuple[int, date]]] = defaultdict(list)
    for i, t in enumerate(trades):
        d = _parse_date(t.get("transactionDate") or t.get("filingDate"))
        if d is None:
            continue
        insider = str(t.get("reportingName") or "unknown")
        by_insider[insider].append((i, d))

    routine: dict[int, bool] = {}
    for insider, entries in by_insider.items():
        entries.sort(key=lambda x: x[1])
        for i, this_date in entries:
            same_window_years: set[int] = set()
            for j, other_date in entries:
                if j == i or other_date.year == this_date.year:
                    continue
                synthetic = date(other_date.year, this_date.month, min(28, this_date.day))
                if abs((other_date - synthetic).days) <= 10:
                    same_window_years.add(other_date.year)
            routine[i] = len(same_window_years) >= 2
    return routine


def detect_cluster(trades: list[dict], today: date | None = None) -> dict | None:
    """
    Returns a cluster signal dict or None if no cluster fires.

    A cluster = ≥MIN_OPPORTUNISTIC opportunistic open-market buys by
    ≥MIN_DISTINCT_INSIDERS distinct insiders within the trailing 30 days.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=CLUSTER_WINDOW_DAYS)

    buys = [t for t in trades if _is_open_market_buy(t)]
    if not buys:
        return None
    routine_flags = _classify_routine(buys)

    opportunistic_recent = []
    for i, t in enumerate(buys):
        if routine_flags.get(i, False):
            continue
        td = _parse_date(t.get("transactionDate") or t.get("filingDate"))
        if td is None or td < cutoff or td > today:
            continue
        opportunistic_recent.append((i, td, t))

    insiders = {str(t.get("reportingName") or "unknown") for _, _, t in opportunistic_recent}
    if len(opportunistic_recent) < MIN_OPPORTUNISTIC or len(insiders) < MIN_DISTINCT_INSIDERS:
        return None

    total_value = 0.0
    for _, _, t in opportunistic_recent:
        try:
            shares = float(t.get("securitiesTransacted") or 0)
            price = float(t.get("price") or 0)
            total_value += shares * price
        except (TypeError, ValueError):
            continue

    cluster_date = max(td for _, td, _ in opportunistic_recent)
    confidence = min(95.0, 60 + len(opportunistic_recent) * 5 + len(insiders) * 3)

    return {
        "cluster_date": cluster_date,
        "n_opportunistic": len(opportunistic_recent),
        "n_distinct": len(insiders),
        "total_value": round(total_value, 2),
        "insiders": sorted(insiders),
        "confidence": round(confidence, 2),
    }


async def evaluate_symbol(symbol: str) -> dict | None:
    trades = await _fetch_insider_trades(symbol)
    if not trades:
        return None
    cluster = detect_cluster(trades)
    if cluster is None:
        return None
    cluster["symbol"] = symbol
    return cluster


async def run_insider_flow_job(symbols: list[str] | None = None, max_symbols: int = 600,
                                concurrency: int = 10) -> int:
    """Nightly: scan the universe, persist clusters, rank cross-sectionally."""
    from data.scanner import get_scan_universe
    from core.database import AsyncSessionLocal
    from scoring.cross_section import rank_values, persist_ranks
    from sqlalchemy import text

    if symbols is None:
        symbols = await get_scan_universe()
    symbols = symbols[:max_symbols]
    logger.info(f"insider_flow job: scanning {len(symbols)} symbols")

    sem = asyncio.Semaphore(concurrency)

    async def _one(s: str) -> dict | None:
        async with sem:
            return await evaluate_symbol(s)

    results = await asyncio.gather(*[_one(s) for s in symbols])
    clusters = [r for r in results if r]

    today = date.today()
    written = 0
    async with AsyncSessionLocal() as session:
        for c in clusters:
            try:
                await session.execute(text("""
                    INSERT INTO insider_signals
                        (symbol, cluster_date, n_opportunistic, n_distinct,
                         total_value, insiders, confidence)
                    VALUES
                        (:sym, :cd, :n_opp, :n_dist, :tv, :ins, :conf)
                    ON CONFLICT (symbol, cluster_date) DO UPDATE SET
                        n_opportunistic = EXCLUDED.n_opportunistic,
                        n_distinct = EXCLUDED.n_distinct,
                        total_value = EXCLUDED.total_value,
                        insiders = EXCLUDED.insiders,
                        confidence = EXCLUDED.confidence
                """), {
                    "sym": c["symbol"], "cd": c["cluster_date"],
                    "n_opp": c["n_opportunistic"], "n_dist": c["n_distinct"],
                    "tv": c["total_value"], "ins": c["insiders"], "conf": c["confidence"],
                })
                written += 1
            except Exception as e:
                logger.debug(f"insider_signals upsert failed for {c['symbol']}: {e}")
        await session.commit()

        # Cross-sectional rank by confidence (sparse — only firing symbols get a rank)
        scores = {c["symbol"]: float(c["confidence"]) for c in clusters}
        if scores:
            ranks = rank_values(scores)
            await persist_ranks("insider_cluster", ranks, today, session)

    logger.info(f"insider_flow job: {written} clusters persisted")
    return written
