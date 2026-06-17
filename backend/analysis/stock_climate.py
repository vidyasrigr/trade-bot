"""
Per-stock climate + market weather — Phase L.

Why this exists:
  Each stock is in its own micro-regime. NVDA can be ripping bull while INTC
  chops sideways while a meme stock squeezes — same day. The Phase G Markov
  per-stock model already captures regime transitions, but we lacked a
  persistent NIGHTLY label that the strategist prompt, the briefing UI, and
  the IC tracker can all read.

Labels:
  per-stock climate ∈ {bull, bear, chop, squeeze, high_vol, unknown}
  market climate    ∈ {bull_trend, bear_trend, chop, high_vol, crisis}

Classifier (lightweight, deterministic, no LLM):
  - bull:      ret_60d > +10% AND price > sma200 AND momentum_score > +1σ
  - bear:      ret_60d < -10% AND price < sma200 AND momentum_score < -1σ
  - high_vol:  20d RV > 80th percentile of 1y history
  - squeeze:   short_squeeze_signal fires (confidence > 70 in last 5 days)
  - chop:      |ret_60d| < 5% AND 20d RV < 50th percentile
  - unknown:   insufficient data

Market weather (same input set on SPY + VIX):
  - crisis:     VIX > 30
  - high_vol:   VIX > 20 (and not crisis)
  - bull_trend: SPY > sma200 AND positive 20d momentum AND breadth > 50%
  - bear_trend: SPY < sma200 AND negative 20d momentum
  - chop:       everything else

Persisted nightly to stock_climate + market_weather (migration 017).
Strategist prompt receives one line per symbol:
  "AAPL: bull (RS-vs-SPY +14%, 87% confidence) | Market: bull_trend (VIX 14.2)"
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, asdict
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class StockClimate:
    symbol: str
    as_of_date: date
    climate: str
    market_climate: str
    relative_climate: str
    momentum_score: float
    rs_vs_spy: float
    rv_pct_1yr: float
    near_52w_high: float
    confidence: float


@dataclass
class MarketWeather:
    as_of_date: date
    weather: str
    vix: float | None
    vix_term: float | None
    breadth: float | None
    spy_ret_5d: float
    spy_ret_20d: float
    yield_curve_10y2y: float | None
    hy_oas: float | None
    notes: str


# ---------------------------------------------------------------------------
# Market weather (one classification, shared across all per-stock calls)
# ---------------------------------------------------------------------------

async def compute_market_weather() -> MarketWeather:
    from data.market import get_ohlcv_yfinance
    today = date.today()

    spy = get_ohlcv_yfinance("SPY", period="2y")
    if spy is None or spy.empty or len(spy) < 200:
        return MarketWeather(today, "unknown", None, None, None,
                              0.0, 0.0, None, None, "insufficient SPY history")

    closes = spy["close"]
    sma200 = float(closes.tail(200).mean())
    last = float(closes.iloc[-1])
    ret_5 = float(last / closes.iloc[-6] - 1) if len(closes) >= 6 else 0.0
    ret_20 = float(last / closes.iloc[-21] - 1) if len(closes) >= 21 else 0.0

    # VIX + term structure
    vix_val: float | None = None
    vix3m: float | None = None
    try:
        from data.macro_feeds import vix_term_structure
        vts = await vix_term_structure()
        vix_val = vts.vix
        vix3m = vts.vix3m
    except Exception as e:
        logger.debug(f"vix term structure unavailable: {e}")
    vix_term = (vix3m - vix_val) if (vix3m and vix_val) else None

    # Macro pulse
    yc, hy = None, None
    try:
        from data.macro_feeds import fred_snapshot
        macro = await fred_snapshot()
        yc = macro.get("yield_curve_10y2y")
        hy = macro.get("hy_oas")
    except Exception:
        pass

    breadth = await _market_breadth()

    if vix_val and vix_val > 30:
        weather, notes = "crisis", f"VIX={vix_val:.1f}"
    elif vix_val and vix_val > 20:
        weather, notes = "high_vol", f"VIX={vix_val:.1f}"
    elif last > sma200 and ret_20 > 0.01 and (breadth or 0.5) > 0.5:
        weather, notes = "bull_trend", f"SPY above 200dma, +{ret_20*100:.1f}% 20d"
    elif last < sma200 and ret_20 < -0.01:
        weather, notes = "bear_trend", f"SPY below 200dma, {ret_20*100:.1f}% 20d"
    else:
        weather, notes = "chop", "no decisive trend"

    return MarketWeather(
        as_of_date=today, weather=weather,
        vix=vix_val, vix_term=vix_term, breadth=breadth,
        spy_ret_5d=ret_5, spy_ret_20d=ret_20,
        yield_curve_10y2y=yc, hy_oas=hy, notes=notes,
    )


async def _market_breadth() -> float | None:
    """% of scan universe with current price above 200dma. Cached for the day."""
    try:
        from data.scanner import get_scan_universe
        from data.market import get_multi_ohlcv_yfinance
        from core.redis_client import cache_get, cache_set
        cached = await cache_get("market:breadth")
        if cached:
            return float(cached)
        symbols = (await get_scan_universe())[:1000]  # top 1k for speed
        data = get_multi_ohlcv_yfinance(symbols, period="1y")
        above = 0
        total = 0
        for sym, df in data.items():
            if df is None or df.empty or len(df) < 200:
                continue
            sma = float(df["close"].tail(200).mean())
            last = float(df["close"].iloc[-1])
            total += 1
            if last > sma:
                above += 1
        if total == 0:
            return None
        breadth = above / total
        await cache_set("market:breadth", str(breadth), ttl=43200)  # 12h
        return breadth
    except Exception as e:
        logger.debug(f"breadth calc failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Per-stock climate classifier
# ---------------------------------------------------------------------------

def _classify_stock(closes: pd.Series, spy_closes: pd.Series,
                     squeeze_recently: bool,
                     market_weather: str) -> tuple[StockClimate, float]:
    """Pure function — easy to unit-test. Returns (StockClimate, confidence)."""
    if closes is None or closes.empty or len(closes) < 210:
        return None, 0.0

    last = float(closes.iloc[-1])
    sma200 = float(closes.tail(200).mean())
    ret_60d = float(last / closes.iloc[-61] - 1) if len(closes) >= 61 else 0.0
    ret_20d = float(last / closes.iloc[-21] - 1) if len(closes) >= 21 else 0.0

    log_rets = np.log(closes.values[1:] / closes.values[:-1])
    rv20 = float(np.std(log_rets[-20:]) * math.sqrt(252))

    rv_series = pd.Series(log_rets).rolling(20).std() * math.sqrt(252)
    rv_series = rv_series.dropna()
    if len(rv_series) >= 30:
        rv_pct_1yr = float((rv_series.iloc[:-1] < rv20).mean())
    else:
        rv_pct_1yr = 0.5

    # RS line slope: 60d return vs SPY 60d
    spy_ret_60d = float(spy_closes.iloc[-1] / spy_closes.iloc[-61] - 1) if len(spy_closes) >= 61 else 0.0
    rs_vs_spy = ret_60d - spy_ret_60d

    # momentum_score = ret_20 z-scored against 1yr history of 20d returns
    rolling_20d_rets = pd.Series([
        float(closes.iloc[i] / closes.iloc[i - 21] - 1) if i - 21 >= 0 else 0.0
        for i in range(len(closes) - 252, len(closes))
    ])
    mom_std = rolling_20d_rets.std() or 1.0
    momentum_score = (ret_20d - rolling_20d_rets.mean()) / mom_std

    high_52w = float(closes.tail(252).max())
    low_52w = float(closes.tail(252).min())
    near_52w_high = (last - low_52w) / (high_52w - low_52w) if high_52w > low_52w else 0.5

    # Classification
    confidence = 50.0
    if squeeze_recently:
        climate = "squeeze"
        confidence = 80.0
    elif rv_pct_1yr > 0.80:
        climate = "high_vol"
        confidence = 70.0
    elif ret_60d > 0.10 and last > sma200 and momentum_score > 1.0:
        climate = "bull"
        confidence = min(95.0, 70 + abs(momentum_score) * 8)
    elif ret_60d < -0.10 and last < sma200 and momentum_score < -1.0:
        climate = "bear"
        confidence = min(95.0, 70 + abs(momentum_score) * 8)
    elif abs(ret_60d) < 0.05 and rv_pct_1yr < 0.50:
        climate = "chop"
        confidence = 70.0
    else:
        climate = "chop"
        confidence = 50.0

    # Relative climate label vs the market
    if rs_vs_spy > 0.05:
        relative = "outperforming"
    elif rs_vs_spy < -0.05:
        relative = "underperforming"
    else:
        relative = "inline"

    return StockClimate(
        symbol="",  # filled by caller
        as_of_date=date.today(),
        climate=climate,
        market_climate=market_weather,
        relative_climate=relative,
        momentum_score=round(float(momentum_score), 3),
        rs_vs_spy=round(rs_vs_spy, 4),
        rv_pct_1yr=round(rv_pct_1yr, 4),
        near_52w_high=round(near_52w_high, 4),
        confidence=round(confidence, 2),
    ), confidence


async def evaluate_symbol(symbol: str, spy_closes: pd.Series,
                           market_weather: str) -> StockClimate | None:
    from data.market import get_ohlcv_yfinance
    df = get_ohlcv_yfinance(symbol, period="2y")
    if df is None or df.empty:
        return None

    squeeze_recently = await _squeeze_recently(symbol)
    out, _ = _classify_stock(df["close"], spy_closes, squeeze_recently, market_weather)
    if out is None:
        return None
    out.symbol = symbol
    return out


async def _squeeze_recently(symbol: str, days: int = 5) -> bool:
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT 1 FROM short_squeeze_signals
                WHERE symbol = :sym
                  AND as_of_date >= CURRENT_DATE - make_interval(days => :n)
                  AND confidence > 70
                LIMIT 1
            """), {"sym": symbol, "n": days})
            return result.fetchone() is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Persistence + orchestration
# ---------------------------------------------------------------------------

async def _persist_market_weather(w: MarketWeather) -> None:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        await session.execute(text("""
            INSERT INTO market_weather
                (as_of_date, weather, vix, vix_term, breadth, spy_ret_5d, spy_ret_20d,
                 yield_curve_10y2y, hy_oas, notes)
            VALUES
                (:d, :w, :vix, :vt, :br, :r5, :r20, :yc, :hy, :n)
            ON CONFLICT (as_of_date) DO UPDATE SET
                weather = EXCLUDED.weather,
                vix = EXCLUDED.vix,
                vix_term = EXCLUDED.vix_term,
                breadth = EXCLUDED.breadth,
                spy_ret_5d = EXCLUDED.spy_ret_5d,
                spy_ret_20d = EXCLUDED.spy_ret_20d,
                yield_curve_10y2y = EXCLUDED.yield_curve_10y2y,
                hy_oas = EXCLUDED.hy_oas,
                notes = EXCLUDED.notes
        """), {
            "d": w.as_of_date, "w": w.weather, "vix": w.vix, "vt": w.vix_term,
            "br": w.breadth, "r5": w.spy_ret_5d, "r20": w.spy_ret_20d,
            "yc": w.yield_curve_10y2y, "hy": w.hy_oas, "n": w.notes,
        })
        await session.commit()


async def _persist_stock_climates(climates: list[StockClimate]) -> int:
    if not climates:
        return 0
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    written = 0
    async with AsyncSessionLocal() as session:
        for c in climates:
            try:
                await session.execute(text("""
                    INSERT INTO stock_climate
                        (symbol, as_of_date, climate, market_climate, relative_climate,
                         momentum_score, rs_vs_spy, rv_pct_1yr, near_52w_high, confidence)
                    VALUES
                        (:sym, :d, :c, :mc, :rc, :ms, :rs, :rv, :h52, :conf)
                    ON CONFLICT (symbol, as_of_date) DO UPDATE SET
                        climate = EXCLUDED.climate,
                        market_climate = EXCLUDED.market_climate,
                        relative_climate = EXCLUDED.relative_climate,
                        momentum_score = EXCLUDED.momentum_score,
                        rs_vs_spy = EXCLUDED.rs_vs_spy,
                        rv_pct_1yr = EXCLUDED.rv_pct_1yr,
                        near_52w_high = EXCLUDED.near_52w_high,
                        confidence = EXCLUDED.confidence
                """), {
                    "sym": c.symbol, "d": c.as_of_date, "c": c.climate,
                    "mc": c.market_climate, "rc": c.relative_climate,
                    "ms": c.momentum_score, "rs": c.rs_vs_spy,
                    "rv": c.rv_pct_1yr, "h52": c.near_52w_high, "conf": c.confidence,
                })
                written += 1
            except Exception as e:
                logger.debug(f"stock_climate upsert failed for {c.symbol}: {e}")
        await session.commit()
    return written


async def run_climate_job(symbols: Iterable[str] | None = None,
                           max_symbols: int = 1000,
                           concurrency: int = 16) -> dict:
    """Nightly: market weather + per-stock climate for liquid universe."""
    from data.scanner import get_scan_universe
    from data.market import get_ohlcv_yfinance

    weather = await compute_market_weather()
    await _persist_market_weather(weather)
    logger.info(f"market weather: {weather.weather} ({weather.notes})")

    spy = get_ohlcv_yfinance("SPY", period="2y")
    if spy is None or spy.empty:
        logger.warning("climate job: SPY history unavailable, skipping per-stock")
        return {"market": weather.weather, "stocks": 0}
    spy_closes = spy["close"]

    if symbols is None:
        symbols = await get_scan_universe()
    symbols = list(symbols)[:max_symbols]

    sem = asyncio.Semaphore(concurrency)

    async def _one(s: str) -> StockClimate | None:
        async with sem:
            return await evaluate_symbol(s, spy_closes, weather.weather)

    results = await asyncio.gather(*[_one(s) for s in symbols])
    climates = [c for c in results if c is not None]
    written = await _persist_stock_climates(climates)

    logger.info(f"stock_climate: {written} symbols classified for {weather.as_of_date}")
    return {"market": weather.weather, "stocks": written}


# ---------------------------------------------------------------------------
# Read helpers for the strategist prompt
# ---------------------------------------------------------------------------

async def get_climate(symbol: str, session=None) -> StockClimate | None:
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await get_climate(symbol, s)
    from sqlalchemy import text
    result = await session.execute(text("""
        SELECT symbol, as_of_date, climate, market_climate, relative_climate,
               momentum_score, rs_vs_spy, rv_pct_1yr, near_52w_high, confidence
        FROM stock_climate
        WHERE symbol = :sym
        ORDER BY as_of_date DESC
        LIMIT 1
    """), {"sym": symbol})
    row = result.mappings().first()
    if row is None:
        return None
    return StockClimate(**dict(row))


def format_climate_context(c: StockClimate | None) -> str:
    if c is None:
        return ""
    return (
        f"Climate: {c.symbol} is in **{c.climate}** "
        f"(RS-vs-SPY {c.rs_vs_spy*100:+.1f}%, momentum z={c.momentum_score:+.2f}, "
        f"RV pct={c.rv_pct_1yr:.0%}, near-52w-high={c.near_52w_high:.0%}, "
        f"{c.relative_climate} the market) "
        f"| Market: **{c.market_climate}**"
    )
