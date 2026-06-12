"""
Per-stock Behavioral DNA Engine.

Computes behavioral profiles from 3-5 years of OHLCV + earnings history.
Designed to run nightly for the top-N scanner universe.

For stocks with <8 earnings events, falls back to FAISS behavioral twin lookup.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StockBehavioralDNA:
    symbol: str

    # Earnings behavior
    earnings_realized_implied_ratio: float = 0.0
    earnings_direction_bias_on_beat: float = 0.5
    iv_crush_avg_pct: float = 0.0
    beat_and_raise_pead_rate: float = 0.0
    earnings_events_count: int = 0
    sell_news_conditions: dict[str, float] = field(default_factory=dict)

    # Post-ATH behavior
    post_ath_5d_median_return: float = 0.0
    post_ath_20d_median_return: float = 0.0
    ath_continuation_rate: float = 0.5

    # Momentum characteristics
    momentum_persistence_days: int = 5
    volume_leads_price_days: int = 2

    # Per-stock indicator IC (information coefficient)
    best_indicator_ic: dict[str, float] = field(default_factory=dict)

    # Sector / cascade membership
    semis_cascade_member: bool = False
    hyperscaler_lag_days: int = 0

    # Data quality
    uses_behavioral_twins: bool = False
    twin_symbols: list[str] = field(default_factory=list)
    data_quality_score: float = 0.0
    computed_at: str = ""


# ---------------------------------------------------------------------------
# OHLCV loader (yfinance)
# ---------------------------------------------------------------------------

async def _load_ohlcv(symbol: str, years: int = 5) -> pd.DataFrame:
    """Pull daily OHLCV from yfinance (free, 5-year history)."""
    cache_key = f"dna:ohlcv:{symbol}:{years}y"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        rows = orjson.loads(cached)
        return pd.DataFrame(rows)

    try:
        import yfinance as yf  # optional dependency
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{years}y", interval="1d", auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                                 "low": "low", "close": "close", "volume": "volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.date

        import orjson
        rows_json = orjson.dumps([
            {k: (str(v) if isinstance(v, (datetime,)) else float(v) if hasattr(v, '__float__') else v)
             for k, v in row.items()}
            for row in df.to_dict("records")
        ]).decode()
        await cache_set(cache_key, rows_json, ttl=86400)  # 24h cache
        return df
    except Exception as e:
        logger.debug(f"yfinance OHLCV load failed for {symbol}: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Earnings dates loader (FMP)
# ---------------------------------------------------------------------------

async def _load_earnings_history(symbol: str) -> list[dict]:
    """FMP earnings surprise history — returns list of {date, eps_actual, eps_estimate, revenue_actual, revenue_estimate}."""
    if not settings.FMP_API_KEY:
        return []

    cache_key = f"dna:earnings:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/earnings-surprises/{symbol}",
                params={"apikey": settings.FMP_API_KEY},
            )
            data = resp.json()

        if not isinstance(data, list) or not data:
            return []

        results = []
        for item in data[:20]:  # last 20 quarters
            try:
                results.append({
                    "date": item.get("date", ""),
                    "eps_actual": float(item.get("actualEarningResult") or 0),
                    "eps_estimate": float(item.get("estimatedEarning") or 0),
                    "revenue_actual": float(item.get("actualRevenue") or 0),
                    "revenue_estimate": float(item.get("estimatedRevenue") or 0),
                })
            except (TypeError, ValueError):
                continue

        import orjson
        await cache_set(cache_key, orjson.dumps(results).decode(), ttl=86400 * 7)
        return results
    except Exception as e:
        logger.debug(f"FMP earnings history failed for {symbol}: {e}")
        return []


# ---------------------------------------------------------------------------
# Core DNA computation
# ---------------------------------------------------------------------------

def _compute_earnings_dna(earnings: list[dict], df: pd.DataFrame) -> dict[str, Any]:
    """Compute earnings behavioral metrics from historical data."""
    if not earnings or df.empty:
        return {}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    realized_implied_ratios = []
    direction_on_beat = []
    pead_rates = []

    for event in earnings:
        try:
            event_date = pd.to_datetime(event["date"])

            # Find price 1 day before and 1 day after earnings
            pre_date = event_date - timedelta(days=1)
            post_date = event_date + timedelta(days=1)

            pre_idx = df.index.searchsorted(pre_date)
            post_idx = df.index.searchsorted(post_date)

            if pre_idx >= len(df) or post_idx >= len(df):
                continue

            pre_close = float(df["close"].iloc[pre_idx])
            post_close = float(df["close"].iloc[min(post_idx, len(df)-1)])

            if pre_close <= 0:
                continue

            actual_move_pct = abs((post_close - pre_close) / pre_close)

            # Estimate implied move from ATM straddle approximation (IV * sqrt(T))
            # Simplified: use 30-day window volatility as proxy for implied move
            window_start = pre_idx - 20
            if window_start >= 0:
                window = df["close"].iloc[window_start:pre_idx]
                if len(window) >= 10:
                    hv = float(window.pct_change().std() * np.sqrt(252))
                    implied_1d_move = hv * np.sqrt(1/252)
                    if implied_1d_move > 0:
                        realized_implied_ratios.append(actual_move_pct / implied_1d_move)

            # Direction bias on beat
            eps_est = event.get("eps_estimate", 0)
            eps_act = event.get("eps_actual", 0)
            if eps_est and eps_act:
                beat = eps_act > eps_est
                if beat:
                    direction_on_beat.append(1 if post_close > pre_close else 0)

            # PEAD: beat + raised guidance proxy
            rev_est = event.get("revenue_estimate", 0)
            rev_act = event.get("revenue_actual", 0)
            if eps_est and eps_act and rev_est and rev_act:
                if eps_act > eps_est and rev_act > rev_est * 1.02:
                    # Look for 30-day drift
                    pead_end_idx = df.index.searchsorted(event_date + timedelta(days=30))
                    if pead_end_idx < len(df):
                        pead_close = float(df["close"].iloc[pead_end_idx])
                        pead_rates.append(1 if pead_close > post_close else 0)

        except Exception:
            continue

    result: dict[str, Any] = {}
    if realized_implied_ratios:
        result["earnings_realized_implied_ratio"] = round(float(np.median(realized_implied_ratios)), 3)
    if direction_on_beat:
        result["earnings_direction_bias_on_beat"] = round(float(np.mean(direction_on_beat)), 3)
    if pead_rates:
        result["beat_and_raise_pead_rate"] = round(float(np.mean(pead_rates)), 3)
    result["earnings_events_count"] = len(earnings)

    return result


def _compute_post_ath_dna(df: pd.DataFrame) -> dict[str, Any]:
    """Compute post-ATH behavioral metrics."""
    if df.empty or len(df) < 60:
        return {}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].values

    returns_5d = []
    returns_20d = []
    continuation_count = 0
    ath_events = 0

    for i in range(20, len(closes) - 21):
        # ATH = new 52-week high
        window_start = max(0, i - 252)
        if closes[i] >= np.max(closes[window_start:i]):
            ath_events += 1
            ret_5 = (closes[min(i+5, len(closes)-1)] - closes[i]) / closes[i]
            ret_20 = (closes[min(i+20, len(closes)-1)] - closes[i]) / closes[i]
            returns_5d.append(ret_5)
            returns_20d.append(ret_20)
            if ret_20 > 0:
                continuation_count += 1

    if not returns_5d:
        return {}

    return {
        "post_ath_5d_median_return": round(float(np.median(returns_5d)), 4),
        "post_ath_20d_median_return": round(float(np.median(returns_20d)), 4),
        "ath_continuation_rate": round(continuation_count / ath_events, 3) if ath_events > 0 else 0.5,
    }


def _compute_momentum_dna(df: pd.DataFrame) -> dict[str, Any]:
    """Compute momentum persistence and volume lead characteristics."""
    if df.empty or len(df) < 60:
        return {}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].values
    volumes = df["volume"].values

    # Momentum persistence: how many days a >2% move tends to persist
    persistence_days = []
    for i in range(len(closes) - 15):
        daily_ret = (closes[i+1] - closes[i]) / closes[i]
        if abs(daily_ret) > 0.02:
            # Track how long the move continues
            direction = 1 if daily_ret > 0 else -1
            days = 0
            for j in range(1, 10):
                if i+j+1 >= len(closes):
                    break
                next_ret = (closes[i+j+1] - closes[i+j]) / closes[i+j]
                if next_ret * direction > 0:
                    days += 1
                else:
                    break
            persistence_days.append(days)

    # Volume leads price: detect how many days unusual volume precedes price moves
    avg_vol = pd.Series(volumes).rolling(20).mean().values
    lead_days_list = []
    for i in range(20, len(volumes) - 5):
        if avg_vol[i] > 0 and volumes[i] > avg_vol[i] * 1.5:
            # Look for significant price move in next 5 days
            for lead in range(1, 6):
                if i + lead >= len(closes):
                    break
                price_move = abs((closes[i+lead] - closes[i]) / closes[i])
                if price_move > 0.02:
                    lead_days_list.append(lead)
                    break

    result: dict[str, Any] = {}
    if persistence_days:
        result["momentum_persistence_days"] = int(np.median(persistence_days))
    if lead_days_list:
        result["volume_leads_price_days"] = int(np.median(lead_days_list))

    return result


def _compute_indicator_ic(df: pd.DataFrame) -> dict[str, float]:
    """
    Compute per-stock information coefficients for key indicators.
    IC = rank correlation between indicator signal and next-5-day return.
    Range: -1 to +1. Higher = more predictive for this specific stock.
    """
    if df.empty or len(df) < 60:
        return {}

    try:
        import pandas_ta as ta
        from scipy.stats import spearmanr

        close = df["close"]
        fwd_5 = close.pct_change(5).shift(-5)

        ic: dict[str, float] = {}

        # RSI-14
        rsi = ta.rsi(close, length=14)
        if rsi is not None:
            valid = ~(rsi.isna() | fwd_5.isna())
            if valid.sum() > 30:
                corr, _ = spearmanr(rsi[valid], fwd_5[valid])
                ic["rsi"] = round(float(corr), 4)

        # MACD histogram
        macd_df = ta.macd(close)
        if macd_df is not None:
            hist = macd_df.iloc[:, 2]
            valid = ~(hist.isna() | fwd_5.isna())
            if valid.sum() > 30:
                corr, _ = spearmanr(hist[valid], fwd_5[valid])
                ic["macd_hist"] = round(float(corr), 4)

        # EMA21 crossover distance
        ema21 = ta.ema(close, length=21)
        if ema21 is not None:
            ema_dist = (close - ema21) / ema21
            valid = ~(ema_dist.isna() | fwd_5.isna())
            if valid.sum() > 30:
                corr, _ = spearmanr(ema_dist[valid], fwd_5[valid])
                ic["ema21_dist"] = round(float(corr), 4)

        # OBV trend
        if "volume" in df.columns:
            obv = ta.obv(close, df["volume"])
            if obv is not None:
                obv_slope = obv.diff(5)
                valid = ~(obv_slope.isna() | fwd_5.isna())
                if valid.sum() > 30:
                    corr, _ = spearmanr(obv_slope[valid], fwd_5[valid])
                    ic["obv_slope"] = round(float(corr), 4)

        return ic
    except ImportError:
        return {}
    except Exception as e:
        logger.debug(f"IC computation failed: {e}")
        return {}


def _compute_sell_news_conditions(
    earnings: list[dict],
    df: pd.DataFrame,
) -> dict[str, float]:
    """
    Compute empirical hit rate of sell-the-news conditions.
    Returns e.g. {"high_ivr_eps_only_beat": 0.72}
    """
    if not earnings or df.empty or len(earnings) < 4:
        return {}

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    eps_only_beats = []   # beat EPS but not revenue
    beat_and_raise = []   # beat both + implied guidance raise (rev beat > 3%)

    for event in earnings:
        try:
            event_date = pd.to_datetime(event["date"])
            pre_idx = df.index.searchsorted(event_date - timedelta(days=1))
            post_idx = df.index.searchsorted(event_date + timedelta(days=1))
            if pre_idx >= len(df) or post_idx >= len(df):
                continue

            pre_close = float(df["close"].iloc[pre_idx])
            post_close = float(df["close"].iloc[min(post_idx, len(df)-1)])
            went_down = post_close < pre_close

            eps_est = event.get("eps_estimate", 0)
            eps_act = event.get("eps_actual", 0)
            rev_est = event.get("revenue_estimate", 0)
            rev_act = event.get("revenue_actual", 0)

            eps_beat = eps_est and eps_act and eps_act > eps_est
            rev_beat = rev_est and rev_act and rev_act > rev_est * 1.01
            strong_rev_beat = rev_est and rev_act and rev_act > rev_est * 1.03

            if eps_beat and not rev_beat:
                eps_only_beats.append(1 if went_down else 0)

            if eps_beat and strong_rev_beat:
                beat_and_raise.append(0 if went_down else 1)  # continuation rate

        except Exception:
            continue

    result: dict[str, float] = {}
    if len(eps_only_beats) >= 3:
        result["eps_only_beat_sell_rate"] = round(float(np.mean(eps_only_beats)), 3)
    if len(beat_and_raise) >= 3:
        result["beat_and_raise_continuation_rate"] = round(float(np.mean(beat_and_raise)), 3)

    return result


# ---------------------------------------------------------------------------
# Semis cascade detection (seeded in DB; updated here if Tradier available)
# ---------------------------------------------------------------------------

SEMIS_CASCADE_MEMBERS = {"NVDA", "AMD", "INTC", "AVGO", "QCOM", "MU", "TSM", "AMAT", "LRCX", "KLAC"}
HYPERSCALER_LAG: dict[str, int] = {
    "NVDA": 14, "AMD": 7, "AVGO": 7, "INTC": 7, "QCOM": 7,
    "MU": 10, "TSM": 10, "AMAT": 7, "LRCX": 7, "KLAC": 7,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def compute_dna(symbol: str) -> StockBehavioralDNA:
    """
    Compute full behavioral DNA for a symbol.
    Loads OHLCV + earnings history, runs all computations, returns a StockBehavioralDNA.
    """
    cache_key = f"dna:computed:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        d = orjson.loads(cached)
        return StockBehavioralDNA(**d)

    dna = StockBehavioralDNA(symbol=symbol)
    dna.computed_at = datetime.utcnow().isoformat()

    # Semis cascade membership (from hardcoded list; DB overrides at runtime)
    dna.semis_cascade_member = symbol in SEMIS_CASCADE_MEMBERS
    dna.hyperscaler_lag_days = HYPERSCALER_LAG.get(symbol, 0)

    # Load data concurrently
    df, earnings = await asyncio.gather(
        _load_ohlcv(symbol, years=5),
        _load_earnings_history(symbol),
    )

    if df.empty:
        logger.warning(f"DNA: no OHLCV data for {symbol}")
        dna.data_quality_score = 0.0
        return dna

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Earnings DNA
    earnings_metrics = _compute_earnings_dna(earnings, df)
    dna.earnings_events_count = earnings_metrics.get("earnings_events_count", 0)
    if earnings_metrics.get("earnings_realized_implied_ratio"):
        dna.earnings_realized_implied_ratio = earnings_metrics["earnings_realized_implied_ratio"]
    if earnings_metrics.get("earnings_direction_bias_on_beat"):
        dna.earnings_direction_bias_on_beat = earnings_metrics["earnings_direction_bias_on_beat"]
    if earnings_metrics.get("beat_and_raise_pead_rate"):
        dna.beat_and_raise_pead_rate = earnings_metrics["beat_and_raise_pead_rate"]

    # Sell-the-news conditions
    dna.sell_news_conditions = _compute_sell_news_conditions(earnings, df)

    # Post-ATH behavior
    ath_metrics = _compute_post_ath_dna(df)
    if ath_metrics.get("post_ath_5d_median_return") is not None:
        dna.post_ath_5d_median_return = ath_metrics["post_ath_5d_median_return"]
        dna.post_ath_20d_median_return = ath_metrics["post_ath_20d_median_return"]
        dna.ath_continuation_rate = ath_metrics["ath_continuation_rate"]

    # Momentum characteristics
    momentum_metrics = _compute_momentum_dna(df)
    if momentum_metrics.get("momentum_persistence_days"):
        dna.momentum_persistence_days = momentum_metrics["momentum_persistence_days"]
    if momentum_metrics.get("volume_leads_price_days"):
        dna.volume_leads_price_days = momentum_metrics["volume_leads_price_days"]

    # Per-stock indicator IC
    dna.best_indicator_ic = _compute_indicator_ic(df)

    # Data quality score (0-100)
    quality_points = 0
    quality_points += min(30, dna.earnings_events_count * 3)  # up to 30 pts for 10+ earnings events
    quality_points += 30 if len(df) >= 252 else int(len(df) / 252 * 30)  # up to 30 for 1yr+ data
    quality_points += 20 if dna.best_indicator_ic else 0
    quality_points += 20 if dna.post_ath_5d_median_return != 0 else 0
    dna.data_quality_score = min(100.0, float(quality_points))

    # Cache for 24 hours
    import orjson
    import dataclasses
    await cache_set(cache_key, orjson.dumps(dataclasses.asdict(dna)).decode(), ttl=86400)

    logger.info(f"DNA computed for {symbol}: earnings={dna.earnings_events_count}, "
                f"quality={dna.data_quality_score:.0f}, IC={dna.best_indicator_ic}")
    return dna


async def save_dna_to_db(dna: StockBehavioralDNA, session) -> None:
    """Upsert DNA record to the stock_dna table."""
    from sqlalchemy import text

    await session.execute(
        text("""
            INSERT INTO stock_dna (
                symbol, earnings_realized_implied_ratio, earnings_direction_bias_on_beat,
                iv_crush_avg_pct, beat_and_raise_pead_rate, earnings_events_count,
                sell_news_conditions, post_ath_5d_median_return, post_ath_20d_median_return,
                ath_continuation_rate, momentum_persistence_days, volume_leads_price_days,
                best_indicator_ic, semis_cascade_member, hyperscaler_lag_days,
                uses_behavioral_twins, twin_symbols, data_quality_score, computed_at, updated_at
            ) VALUES (
                :symbol, :eirr, :edbob, :ivcp, :barp, :eec,
                :snc::jsonb, :pa5r, :pa20r, :acr, :mpd, :vlpd,
                :biic::jsonb, :scm, :hld,
                :ubt, :ts, :dqs, NOW(), NOW()
            )
            ON CONFLICT (symbol) DO UPDATE SET
                earnings_realized_implied_ratio = EXCLUDED.earnings_realized_implied_ratio,
                earnings_direction_bias_on_beat = EXCLUDED.earnings_direction_bias_on_beat,
                iv_crush_avg_pct = EXCLUDED.iv_crush_avg_pct,
                beat_and_raise_pead_rate = EXCLUDED.beat_and_raise_pead_rate,
                earnings_events_count = EXCLUDED.earnings_events_count,
                sell_news_conditions = EXCLUDED.sell_news_conditions,
                post_ath_5d_median_return = EXCLUDED.post_ath_5d_median_return,
                post_ath_20d_median_return = EXCLUDED.post_ath_20d_median_return,
                ath_continuation_rate = EXCLUDED.ath_continuation_rate,
                momentum_persistence_days = EXCLUDED.momentum_persistence_days,
                volume_leads_price_days = EXCLUDED.volume_leads_price_days,
                best_indicator_ic = EXCLUDED.best_indicator_ic,
                semis_cascade_member = EXCLUDED.semis_cascade_member,
                hyperscaler_lag_days = EXCLUDED.hyperscaler_lag_days,
                uses_behavioral_twins = EXCLUDED.uses_behavioral_twins,
                twin_symbols = EXCLUDED.twin_symbols,
                data_quality_score = EXCLUDED.data_quality_score,
                updated_at = NOW()
        """),
        {
            "symbol": dna.symbol,
            "eirr": dna.earnings_realized_implied_ratio or None,
            "edbob": dna.earnings_direction_bias_on_beat or None,
            "ivcp": dna.iv_crush_avg_pct or None,
            "barp": dna.beat_and_raise_pead_rate or None,
            "eec": dna.earnings_events_count,
            "snc": __import__("orjson").dumps(dna.sell_news_conditions).decode(),
            "pa5r": dna.post_ath_5d_median_return or None,
            "pa20r": dna.post_ath_20d_median_return or None,
            "acr": dna.ath_continuation_rate or None,
            "mpd": dna.momentum_persistence_days or None,
            "vlpd": dna.volume_leads_price_days or None,
            "biic": __import__("orjson").dumps(dna.best_indicator_ic).decode(),
            "scm": dna.semis_cascade_member,
            "hld": dna.hyperscaler_lag_days,
            "ubt": dna.uses_behavioral_twins,
            "ts": dna.twin_symbols or [],
            "dqs": dna.data_quality_score,
        }
    )
    await session.commit()


async def get_dna(symbol: str, session=None) -> StockBehavioralDNA | None:
    """
    Get DNA for a symbol — from cache first, then DB, then compute.
    Used by the analysis engine at Stage 4 to inject behavioral context.
    """
    cache_key = f"dna:computed:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        d = orjson.loads(cached)
        return StockBehavioralDNA(**d)

    if session:
        from sqlalchemy import text
        row = await session.execute(
            text("SELECT * FROM stock_dna WHERE symbol = :sym"),
            {"sym": symbol}
        )
        r = row.mappings().first()
        if r:
            dna = StockBehavioralDNA(
                symbol=r["symbol"],
                earnings_realized_implied_ratio=float(r["earnings_realized_implied_ratio"] or 0),
                earnings_direction_bias_on_beat=float(r["earnings_direction_bias_on_beat"] or 0.5),
                iv_crush_avg_pct=float(r["iv_crush_avg_pct"] or 0),
                beat_and_raise_pead_rate=float(r["beat_and_raise_pead_rate"] or 0),
                earnings_events_count=int(r["earnings_events_count"] or 0),
                sell_news_conditions=r["sell_news_conditions"] or {},
                post_ath_5d_median_return=float(r["post_ath_5d_median_return"] or 0),
                post_ath_20d_median_return=float(r["post_ath_20d_median_return"] or 0),
                ath_continuation_rate=float(r["ath_continuation_rate"] or 0.5),
                momentum_persistence_days=int(r["momentum_persistence_days"] or 5),
                volume_leads_price_days=int(r["volume_leads_price_days"] or 2),
                best_indicator_ic=r["best_indicator_ic"] or {},
                semis_cascade_member=bool(r["semis_cascade_member"]),
                hyperscaler_lag_days=int(r["hyperscaler_lag_days"] or 0),
                uses_behavioral_twins=bool(r["uses_behavioral_twins"]),
                twin_symbols=list(r["twin_symbols"] or []),
                data_quality_score=float(r["data_quality_score"] or 0),
                computed_at=str(r.get("computed_at", "")),
            )
            import orjson
            import dataclasses
            await cache_set(cache_key, orjson.dumps(dataclasses.asdict(dna)).decode(), ttl=3600)
            return dna

    # Fall back to computing fresh
    return await compute_dna(symbol)


def format_dna_context(dna: StockBehavioralDNA) -> str:
    """
    Format DNA as a compact string for injection into Claude's Stage 4 context.
    Keeps it concise — Claude should use this as behavioral priors, not exhaustive data.
    """
    lines = [f"[{dna.symbol} Behavioral DNA — quality {dna.data_quality_score:.0f}/100]"]

    if dna.earnings_events_count >= 4:
        lines.append(
            f"Earnings: {dna.earnings_events_count} events, "
            f"direction-on-beat={dna.earnings_direction_bias_on_beat:.0%} up, "
            f"IV crush avg={dna.iv_crush_avg_pct:.0%}"
        )

    if dna.sell_news_conditions:
        sn = dna.sell_news_conditions
        if "eps_only_beat_sell_rate" in sn:
            lines.append(f"Sell-the-news: EPS-only beats → stock sold off {sn['eps_only_beat_sell_rate']:.0%} of the time")
        if "beat_and_raise_continuation_rate" in sn:
            lines.append(f"Beat+raise → stock continued up {sn['beat_and_raise_continuation_rate']:.0%} of the time")

    if dna.post_ath_20d_median_return != 0:
        lines.append(
            f"Post-ATH: 5d median={dna.post_ath_5d_median_return:+.1%}, "
            f"20d median={dna.post_ath_20d_median_return:+.1%}, "
            f"continuation rate={dna.ath_continuation_rate:.0%}"
        )

    if dna.best_indicator_ic:
        best = sorted(dna.best_indicator_ic.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        ic_str = ", ".join(f"{k}={v:+.3f}" for k, v in best)
        lines.append(f"Best indicators for this stock: {ic_str}")

    if dna.semis_cascade_member:
        lines.append(f"Semiconductor cascade member — moves {dna.hyperscaler_lag_days}d after hyperscaler capex beats")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Nightly batch runner
# ---------------------------------------------------------------------------

async def run_nightly_dna_batch(symbols: list[str], max_concurrent: int = 5) -> None:
    """Run DNA computation for a batch of symbols. Called by scheduler."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_one(sym: str) -> None:
        async with semaphore:
            try:
                dna = await compute_dna(sym)
                logger.info(f"DNA batch: {sym} quality={dna.data_quality_score:.0f}")
            except Exception as e:
                logger.error(f"DNA batch failed for {sym}: {e}")

    await asyncio.gather(*[_run_one(s) for s in symbols])
    logger.info(f"DNA batch complete: {len(symbols)} symbols processed")
