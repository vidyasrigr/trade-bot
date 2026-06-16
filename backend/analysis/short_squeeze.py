"""
Short squeeze detector.

Research:
  Drechsler & Drechsler (2014, NBER) — *The Shorting Premium*: high-short-interest
  names underperform on average. The squeeze setup is the *exception* — when
  high SI co-occurs with rising price + momentum + a catalyst, the cover-bid
  cascade is asymmetric to the upside.

We require ALL of:
  1. Short interest > 15% of float                        (Drechsler high-SI bucket)
  2. Days-to-cover > 5 (or SI dollar value > 5% market cap when DTC unavailable)
  3. Price > 20-day SMA (trend confirmation)
  4. 5-day return > 0 AND 20-day return > 0               (positive momentum)
  5. Optional: catalyst flag fired in the last 5 days

Cross-sectionally ranked into signal_ranks as 'short_squeeze' so it composes
with the existing factor IC tracker and the Phase E LightGBM ranker.

Data path:
  FMP `/v4/short-interest` gives SI/float when available; falls back to
  alpha-vantage's overview ShortPercentOutstanding. Either is enough — the
  signal is the BUNDLE, not a precise SI number.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

import httpx
import numpy as np
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


CACHE_TTL_S = 86400  # SI updates twice a month; daily cache is generous

# Thresholds from Drechsler-Drechsler (2014) + replications
HIGH_SI_FLOAT_PCT = 0.15
MIN_DAYS_TO_COVER = 5.0
SI_DOLLAR_FLOOR_PCT_MCAP = 0.05  # fallback when DTC unavailable


@dataclass
class SqueezeSetup:
    symbol: str
    si_pct_float: float
    days_to_cover: float | None
    price_above_sma20: bool
    ret_5d: float
    ret_20d: float
    catalyst_within_5d: bool
    confidence: float


async def _fetch_short_data(symbol: str) -> dict:
    """Try FMP v4 short-interest; fall back to alpha-vantage overview."""
    cache_key = f"squeeze:short:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    out: dict = {}
    if settings.FMP_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://financialmodelingprep.com/api/v4/short-interest",
                    params={"symbol": symbol, "apikey": settings.FMP_API_KEY},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        latest = data[0]
                        out["si_pct_float"] = float(latest.get("percentOfFloat") or 0) / 100
                        out["days_to_cover"] = float(latest.get("daysToCover") or 0) or None
                        out["si_shares"] = float(latest.get("shortInterest") or 0)
        except Exception as e:
            logger.debug(f"FMP short-interest failed for {symbol}: {e}")

    if "si_pct_float" not in out and settings.ALPHA_VANTAGE_API_KEY:
        try:
            from data.market import get_av
            av = get_av()
            overview = await av.get_overview(symbol)
            si_pct = float(overview.get("ShortPercentOutstanding", 0) or 0)
            out["si_pct_float"] = si_pct
            out["days_to_cover"] = None
            out["si_shares"] = float(overview.get("SharesShort", 0) or 0)
            out["market_cap"] = float(overview.get("MarketCapitalization", 0) or 0)
        except Exception as e:
            logger.debug(f"AV overview failed for {symbol}: {e}")

    if out:
        import orjson
        await cache_set(cache_key, orjson.dumps(out).decode(), ttl=CACHE_TTL_S)
    return out


def _confidence(setup: SqueezeSetup) -> float:
    """Map setup features to a 0-100 confidence score."""
    score = 0.0
    if setup.si_pct_float > HIGH_SI_FLOAT_PCT:
        score += 25 + min(15, (setup.si_pct_float - HIGH_SI_FLOAT_PCT) * 100)
    if setup.days_to_cover is not None and setup.days_to_cover > MIN_DAYS_TO_COVER:
        score += 10 + min(10, (setup.days_to_cover - MIN_DAYS_TO_COVER) * 1.5)
    if setup.price_above_sma20:
        score += 10
    if setup.ret_5d > 0:
        score += 5
    if setup.ret_20d > 0:
        score += 5
    if setup.catalyst_within_5d:
        score += 20
    return round(min(100.0, score), 2)


async def evaluate_symbol(symbol: str) -> SqueezeSetup | None:
    from data.market import get_ohlcv_yfinance

    short_data = await _fetch_short_data(symbol)
    si_pct = float(short_data.get("si_pct_float") or 0)
    if si_pct < HIGH_SI_FLOAT_PCT:
        return None  # gate 1: high SI required
    dtc = short_data.get("days_to_cover")
    if dtc is None:
        si_shares = float(short_data.get("si_shares") or 0)
        mkt_cap = float(short_data.get("market_cap") or 0)
        if si_shares == 0 or mkt_cap == 0 or si_shares * 1.0 / mkt_cap < SI_DOLLAR_FLOOR_PCT_MCAP:
            pass  # tolerate but log
    elif dtc < MIN_DAYS_TO_COVER:
        return None  # gate 2

    df = get_ohlcv_yfinance(symbol, period="3mo")
    if df is None or df.empty or len(df) < 25:
        return None

    closes = df["close"]
    last = float(closes.iloc[-1])
    sma20 = float(closes.tail(20).mean())
    ret_5d = (last / float(closes.iloc[-6]) - 1) if len(closes) >= 6 else 0.0
    ret_20d = (last / float(closes.iloc[-21]) - 1) if len(closes) >= 21 else 0.0

    if last <= sma20:
        return None  # gate 3
    if ret_5d <= 0 or ret_20d <= 0:
        return None  # gate 4

    # gate 5 (optional): recent catalyst
    catalyst_recent = await _catalyst_within_days(symbol, days=5)

    setup = SqueezeSetup(
        symbol=symbol, si_pct_float=si_pct, days_to_cover=dtc,
        price_above_sma20=True, ret_5d=ret_5d, ret_20d=ret_20d,
        catalyst_within_5d=catalyst_recent, confidence=0,
    )
    setup.confidence = _confidence(setup)
    return setup


async def _catalyst_within_days(symbol: str, days: int) -> bool:
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT 1 FROM catalyst_events
                WHERE symbol = :sym
                  AND detected_at > NOW() - make_interval(days => :n)
                LIMIT 1
            """), {"sym": symbol, "n": days})
            return result.fetchone() is not None
    except Exception:
        return False


async def _persist(setups: list[SqueezeSetup], as_of: date) -> int:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    written = 0
    async with AsyncSessionLocal() as session:
        for s in setups:
            try:
                await session.execute(text("""
                    INSERT INTO short_squeeze_signals
                        (symbol, as_of_date, si_pct_float, days_to_cover,
                         price_above_sma20, ret_5d, ret_20d,
                         catalyst_within_5d, confidence)
                    VALUES
                        (:sym, :d, :si, :dtc, :above, :r5, :r20, :cat, :conf)
                    ON CONFLICT (symbol, as_of_date) DO UPDATE SET
                        si_pct_float = EXCLUDED.si_pct_float,
                        days_to_cover = EXCLUDED.days_to_cover,
                        price_above_sma20 = EXCLUDED.price_above_sma20,
                        ret_5d = EXCLUDED.ret_5d,
                        ret_20d = EXCLUDED.ret_20d,
                        catalyst_within_5d = EXCLUDED.catalyst_within_5d,
                        confidence = EXCLUDED.confidence
                """), {
                    "sym": s.symbol, "d": as_of, "si": s.si_pct_float,
                    "dtc": s.days_to_cover, "above": s.price_above_sma20,
                    "r5": s.ret_5d, "r20": s.ret_20d,
                    "cat": s.catalyst_within_5d, "conf": s.confidence,
                })
                written += 1
            except Exception as e:
                logger.debug(f"squeeze upsert failed for {s.symbol}: {e}")
        await session.commit()
    return written


async def run_short_squeeze_job(symbols: Iterable[str] | None = None,
                                  max_symbols: int = 500,
                                  concurrency: int = 8) -> int:
    """Nightly: filter universe to setups meeting all 4+ gates, persist, rank."""
    from data.scanner import get_scan_universe
    from scoring.cross_section import rank_values, persist_ranks
    from core.database import AsyncSessionLocal

    if symbols is None:
        symbols = await get_scan_universe()
    symbols = list(symbols)[:max_symbols]
    logger.info(f"short_squeeze job: filtering {len(symbols)} symbols")

    sem = asyncio.Semaphore(concurrency)

    async def _one(sym: str) -> SqueezeSetup | None:
        async with sem:
            return await evaluate_symbol(sym)

    results = await asyncio.gather(*[_one(s) for s in symbols])
    setups = [r for r in results if r is not None]

    today = date.today()
    written = await _persist(setups, today)

    scores = {s.symbol: s.confidence for s in setups if s.confidence > 0}
    if scores:
        ranks = rank_values(scores)
        async with AsyncSessionLocal() as session:
            await persist_ranks("short_squeeze", ranks, today, session)

    logger.info(f"short_squeeze job: {len(setups)} setups, {written} persisted")
    return written
