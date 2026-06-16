"""
Markov regime forecasting — Phase G.2.

Why this module exists:
  The existing volatility_regime.py classifies *today's* regime (bull_trend /
  bear_trend / chop / high_vol). It doesn't tell us what's likely in 21 days,
  which is exactly the horizon that matters for:
    - LEAPS / LT position sizing (long horizons = regime persistence dominates)
    - Premium-selling vs buying decisions at 45 DTE (forecast > current)
    - Empirical-Bayes prior for sparse (category, regime) cells in ic_tracker

Method (per Roan / RohOnChain's "Markov Hedge Fund Method" — extended to 4 states):
  1. Generate a daily regime label series for SPY going back N years by running
     analysis/volatility_regime.py over rolling windows
  2. Fit a 4x4 transition matrix via maximum-likelihood (state-i row = empirical
     distribution of next-day states observed from i)
  3. Forecast n steps ahead via Chapman-Kolmogorov (matrix powers)
  4. Compute stationary distribution as the left eigenvector of P^T at λ=1
     (or via power iteration as a fallback)
  5. Expose to:
     - Strategist prompt via agents/graph.py
     - ic_tracker hierarchical pooling (replaces flat regime='all' prior)

Diff vs Roan's original:
  - 4 states instead of 3 (we already have a richer classifier; don't downgrade)
  - Use vol_regime labels, not 20d/±5% rolling-return rule (richer signal)
  - Persist forecasts to a table so the LLM sees a stable snapshot per scan

Cost: one nightly job, runs in seconds, no new data dependencies.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd
from loguru import logger


STATES = ("bull_trend", "bear_trend", "chop", "high_vol")
STATE_INDEX = {s: i for i, s in enumerate(STATES)}
SHRINKAGE_PSEUDO_COUNT = 0.5  # Laplace smoothing for transitions never observed


@dataclass
class MarkovModel:
    states: tuple[str, ...]
    transition_matrix: np.ndarray   # shape (n_states, n_states); row-stochastic
    stationary: dict[str, float]
    sample_size: int
    last_state: str

    def forecast(self, horizon_days: int) -> dict[str, float]:
        """P(state at +horizon | current state) — Chapman-Kolmogorov."""
        if horizon_days < 1:
            row = {s: 0.0 for s in self.states}
            row[self.last_state] = 1.0
            return row
        powered = np.linalg.matrix_power(self.transition_matrix, horizon_days)
        i = STATE_INDEX[self.last_state]
        row = powered[i]
        return {s: float(row[STATE_INDEX[s]]) for s in self.states}


# ---------------------------------------------------------------------------
# Transition-matrix fit
# ---------------------------------------------------------------------------

def fit_transition_matrix(labels: Iterable[str]) -> MarkovModel:
    """
    Maximum-likelihood transition matrix with Laplace smoothing so unseen
    transitions don't have probability 0 (which would break Chapman-Kolmogorov
    when the chain has a low-probability state that nonetheless appears once).
    """
    seq = [s for s in labels if s in STATE_INDEX]
    if len(seq) < 5:
        raise RuntimeError(f"fit_transition_matrix: only {len(seq)} valid labels")

    n = len(STATES)
    counts = np.full((n, n), SHRINKAGE_PSEUDO_COUNT, dtype=float)
    for a, b in zip(seq[:-1], seq[1:]):
        counts[STATE_INDEX[a], STATE_INDEX[b]] += 1
    matrix = counts / counts.sum(axis=1, keepdims=True)
    stationary = _stationary_distribution(matrix)
    return MarkovModel(
        states=STATES,
        transition_matrix=matrix,
        stationary={STATES[i]: float(stationary[i]) for i in range(n)},
        sample_size=len(seq),
        last_state=seq[-1],
    )


def _stationary_distribution(matrix: np.ndarray, max_iter: int = 200,
                              tol: float = 1e-10) -> np.ndarray:
    """
    Left eigenvector of P at eigenvalue 1, normalized to sum 1.
    Falls back to power iteration if eigen decomposition is numerically dodgy.
    """
    eigvals, eigvecs = np.linalg.eig(matrix.T)
    idx = np.argmin(np.abs(eigvals - 1.0))
    vec = np.real(eigvecs[:, idx])
    if vec.sum() != 0:
        vec = vec / vec.sum()
        if (vec >= -1e-12).all():
            return np.clip(vec, 0, 1)
    # Power iteration fallback
    n = matrix.shape[0]
    pi = np.full(n, 1.0 / n)
    for _ in range(max_iter):
        nxt = pi @ matrix
        if np.linalg.norm(nxt - pi, ord=1) < tol:
            return nxt
        pi = nxt
    return pi


# ---------------------------------------------------------------------------
# Label series construction
# ---------------------------------------------------------------------------

def _classify_one(close_window: pd.Series, vix_current: float | None) -> str:
    """
    Cheap reimplementation of volatility_regime.py's logic for backfill —
    avoids spinning up the full async analyzer per day. Keeps the same
    thresholds so historical labels match what the live analyzer produces.
    """
    from analysis.volatility_regime import (
        VIX_CALM, VIX_NORMAL_HIGH, VIX_ELEVATED,
    )
    if len(close_window) < 50:
        return "chop"
    last = float(close_window.iloc[-1])
    sma50 = close_window.tail(50).mean()
    if len(close_window) >= 5:
        prev = float(close_window.iloc[-5])
        sma50_slope = (last - prev) / max(prev, 1e-9)
    else:
        sma50_slope = 0.0
    trend_threshold = 0.015

    if vix_current is not None:
        if vix_current > VIX_ELEVATED:
            return "high_vol"
        if vix_current > VIX_NORMAL_HIGH:
            return "high_vol"
        if sma50_slope > trend_threshold and last > sma50:
            return "bull_trend"
        if sma50_slope < -trend_threshold and last < sma50:
            return "bear_trend"
        return "chop"

    # No-VIX fallback — same as volatility_regime.py:92
    log_rets = np.log(close_window.values[1:] / close_window.values[:-1])
    rv20 = float(np.std(log_rets[-20:])) * math.sqrt(252) if len(log_rets) >= 20 else 0.0
    if rv20 > 0.35:
        return "high_vol"
    if sma50_slope > trend_threshold and last > sma50:
        return "bull_trend"
    if sma50_slope < -trend_threshold and last < sma50:
        return "bear_trend"
    return "chop"


def label_history(closes: pd.Series, vix_series: pd.Series | None = None,
                  warmup: int = 50) -> list[str]:
    """Sequential per-day label series given a price history (and optional VIX)."""
    labels: list[str] = []
    closes = closes.dropna()
    vix_lookup: dict = {}
    if vix_series is not None:
        vix_lookup = {idx: float(v) for idx, v in vix_series.dropna().items()}
    for i in range(warmup, len(closes)):
        window = closes.iloc[:i + 1]
        vix_today = vix_lookup.get(closes.index[i])
        labels.append(_classify_one(window, vix_today))
    return labels


# ---------------------------------------------------------------------------
# Persistence + orchestrator
# ---------------------------------------------------------------------------

async def _persist_forecast(scope: str, model: MarkovModel, as_of: date) -> None:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    import orjson

    async with AsyncSessionLocal() as session:
        await session.execute(text("""
            INSERT INTO regime_forecasts
                (scope, as_of_date, current_state, forecast_5d, forecast_21d,
                 forecast_63d, stationary, sample_size)
            VALUES
                (:scope, :d, :cur, :f5::jsonb, :f21::jsonb, :f63::jsonb,
                 :stat::jsonb, :n)
            ON CONFLICT (scope, as_of_date) DO UPDATE SET
                current_state = EXCLUDED.current_state,
                forecast_5d = EXCLUDED.forecast_5d,
                forecast_21d = EXCLUDED.forecast_21d,
                forecast_63d = EXCLUDED.forecast_63d,
                stationary = EXCLUDED.stationary,
                sample_size = EXCLUDED.sample_size
        """), {
            "scope": scope, "d": as_of,
            "cur": model.last_state,
            "f5": orjson.dumps(model.forecast(5)).decode(),
            "f21": orjson.dumps(model.forecast(21)).decode(),
            "f63": orjson.dumps(model.forecast(63)).decode(),
            "stat": orjson.dumps(model.stationary).decode(),
            "n": model.sample_size,
        })
        await session.commit()


async def _vix_series() -> pd.Series | None:
    """Fetch ^VIX history for label conditioning. Returns None if unavailable."""
    try:
        from data.market import get_ohlcv_yfinance
        df = get_ohlcv_yfinance("^VIX", period="5y")
        if df is None or df.empty:
            return None
        return df["close"]
    except Exception:
        return None


async def fit_market_model() -> MarkovModel | None:
    from data.market import get_ohlcv_yfinance
    spx = get_ohlcv_yfinance("SPY", period="5y")
    if spx is None or spx.empty or len(spx) < 300:
        logger.warning("regime_markov: insufficient SPY history")
        return None
    vix = await _vix_series()
    labels = label_history(spx["close"], vix_series=vix)
    if len(labels) < 200:
        logger.warning(f"regime_markov: only {len(labels)} labels, skipping")
        return None
    return fit_transition_matrix(labels)


async def fit_symbol_model(symbol: str) -> MarkovModel | None:
    """
    PER-SYMBOL Markov fit. Phase H.10: labels are computed from each stock's OWN
    rolling realized volatility, NOT VIX.

    Why this matters: when every per-symbol model conditions on the same VIX
    series, the per-symbol transition matrices end up very similar to the
    market-wide model (we proved this in the original Phase G.2 implementation).
    The added compute bought almost no information. Conditioning on the stock's
    own RV instead captures genuinely per-stock regime dynamics — high-vol names
    like TSLA spend more time in high_vol regimes, KO spends almost none.
    """
    from data.market import get_ohlcv_yfinance
    df = get_ohlcv_yfinance(symbol, period="3y")
    if df is None or df.empty or len(df) < 250:
        return None
    # Pass vix_series=None so label_history uses the RV fallback (which is what
    # we want here — RV is per-stock, VIX is market-wide).
    labels = label_history(df["close"], vix_series=None)
    if len(labels) < 200:
        return None
    return fit_transition_matrix(labels)


async def run_regime_markov_job(per_symbol_top_n: int = 100) -> int:
    """
    Nightly: market-wide model + per-symbol models for the most-liquid names.
    Returns the number of (scope, date) rows written.
    """
    today = date.today()
    written = 0

    market = await fit_market_model()
    if market is not None:
        await _persist_forecast("market", market, today)
        written += 1
        logger.info(
            f"regime_markov[market]: current={market.last_state} "
            f"forecast_21d={ {k: round(v, 2) for k, v in market.forecast(21).items()} } "
            f"stationary={ {k: round(v, 2) for k, v in market.stationary.items()} }"
        )

    # Per-symbol fits for the top N most active names in today's scan
    try:
        from core.redis_client import cache_get
        import orjson
        cached = await cache_get("scan:latest")
        symbols: list[str] = []
        if cached:
            scan_items = orjson.loads(cached)
            symbols = [it.get("symbol") for it in scan_items if it.get("symbol")]
        symbols = symbols[:per_symbol_top_n]
    except Exception:
        symbols = []

    sem = asyncio.Semaphore(8)

    async def _one(sym: str) -> None:
        nonlocal written
        async with sem:
            try:
                model = await fit_symbol_model(sym)
                if model is None:
                    return
                await _persist_forecast(sym, model, today)
                written += 1
            except Exception as e:
                logger.debug(f"regime_markov[{sym}] failed: {e}")

    if symbols:
        await asyncio.gather(*[_one(s) for s in symbols])

    logger.info(f"regime_markov job: {written} forecasts persisted for {today}")
    return written


# ---------------------------------------------------------------------------
# Read helpers for the prompt / IC pooling
# ---------------------------------------------------------------------------

async def load_forecast(scope: str, session=None) -> dict | None:
    """
    Most recent forecast for a scope. Returns the JSON-friendly dict ready for
    direct injection into the strategist prompt.
    """
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await load_forecast(scope, s)
    from sqlalchemy import text
    result = await session.execute(text("""
        SELECT current_state, forecast_5d, forecast_21d, forecast_63d,
               stationary, sample_size, as_of_date
        FROM regime_forecasts
        WHERE scope = :scope
        ORDER BY as_of_date DESC
        LIMIT 1
    """), {"scope": scope})
    row = result.mappings().first()
    if row is None:
        return None
    return {
        "scope": scope,
        "as_of_date": row["as_of_date"].isoformat() if row["as_of_date"] else None,
        "current_state": row["current_state"],
        "forecast_5d": row["forecast_5d"] or {},
        "forecast_21d": row["forecast_21d"] or {},
        "forecast_63d": row["forecast_63d"] or {},
        "stationary": row["stationary"] or {},
        "sample_size": int(row["sample_size"] or 0),
    }


def format_regime_context(market: dict | None, symbol_model: dict | None) -> str:
    """Compact text block injected into the strategist prompt."""
    if market is None and symbol_model is None:
        return ""
    lines = ["Regime forecast (Markov, 4-state):"]

    def _fmt(label: str, dist: dict) -> str:
        ordered = sorted(dist.items(), key=lambda kv: -kv[1])
        return label + " " + ", ".join(f"{k}={v:.2f}" for k, v in ordered)

    if market is not None:
        lines.append(f"  market current: {market['current_state']}")
        lines.append("  market " + _fmt("21d:", market["forecast_21d"]))
        lines.append("  market " + _fmt("63d:", market["forecast_63d"]))
        lines.append("  market " + _fmt("stationary:", market["stationary"]))
    if symbol_model is not None:
        lines.append(f"  symbol current: {symbol_model['current_state']}")
        lines.append("  symbol " + _fmt("21d:", symbol_model["forecast_21d"]))
        lines.append("  symbol " + _fmt("stationary:", symbol_model["stationary"]))
    return "\n".join(lines)
