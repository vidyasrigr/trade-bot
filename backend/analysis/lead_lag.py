"""
Supply-chain lead-lag graph (Cohen-Frazzini 2008, "Economic Links and
Predictable Returns").

REPLACES the hand-coded HYPERSCALER_LAG dict that mapped specific tickers to
fixed day-counts. That dict was hindsight-fit; this module *learns* the graph
nightly from the past year of daily returns.

Method:
  - Pull 1-year close-price series for the universe (yfinance batch)
  - For each candidate (leader, follower) pair with adequate sample size:
      compute Pearson(leader_returns[t], follower_returns[t + lag]) for
      lag ∈ {1..15} trading days. Keep the lag with the highest correlation
      if |corr| > 0.25 AND lag with that correlation has at least 60 bars.
  - Persist top-K edges per follower to lead_lag_edges (migration 012).

To keep wall time bounded, we restrict leader candidates to the most-liquid
top-N symbols (default 200) and consider all symbols as followers.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd
from loguru import logger


MAX_LAG_DAYS = 15
MIN_ABS_CORRELATION = 0.25
MIN_SAMPLES = 60
TOP_K_PER_FOLLOWER = 5


def _compute_returns_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """Log returns; drops symbols with fewer than 200 bars."""
    if prices is None or prices.empty:
        return pd.DataFrame()
    keep = [c for c in prices.columns if prices[c].dropna().shape[0] >= 200]
    prices = prices[keep]
    return np.log(prices / prices.shift(1)).dropna(how="all")


def _best_lag(leader: pd.Series, follower: pd.Series) -> tuple[int, float, int] | None:
    """
    Returns (lag, correlation, n_samples) where corr is largest in absolute value
    across lags 1..MAX_LAG_DAYS. Drops pairs with too few aligned samples.
    """
    best: tuple[int, float, int] | None = None
    for lag in range(1, MAX_LAG_DAYS + 1):
        shifted = follower.shift(-lag)
        aligned = pd.concat([leader, shifted], axis=1).dropna()
        if len(aligned) < MIN_SAMPLES:
            continue
        a, b = aligned.iloc[:, 0].to_numpy(), aligned.iloc[:, 1].to_numpy()
        if a.std() == 0 or b.std() == 0:
            continue
        corr = float(np.corrcoef(a, b)[0, 1])
        if math.isnan(corr):
            continue
        if best is None or abs(corr) > abs(best[1]):
            best = (lag, corr, len(aligned))
    if best is None or abs(best[1]) < MIN_ABS_CORRELATION:
        return None
    return best


def _liquid_leaders(prices: pd.DataFrame, top_n: int) -> list[str]:
    """Use median absolute return as a liquidity proxy when volume isn't available."""
    if prices.empty:
        return []
    rets = np.log(prices / prices.shift(1)).abs()
    median_abs = rets.median().sort_values(ascending=False)
    return median_abs.head(top_n).index.tolist()


def build_edges(prices: pd.DataFrame, top_leaders: int = 200) -> list[dict]:
    """Returns a list of edge dicts ready for persistence."""
    if prices is None or prices.empty or prices.shape[1] < 5:
        return []

    returns = _compute_returns_matrix(prices)
    if returns.empty:
        return []

    leaders = _liquid_leaders(prices, top_leaders)
    followers = list(returns.columns)
    logger.info(f"lead_lag: scanning {len(leaders)} leaders × {len(followers)} followers")

    per_follower: dict[str, list[dict]] = {}
    for follower in followers:
        f_series = returns[follower].dropna()
        if len(f_series) < MIN_SAMPLES + MAX_LAG_DAYS:
            continue
        for leader in leaders:
            if leader == follower or leader not in returns.columns:
                continue
            l_series = returns[leader].dropna()
            if len(l_series) < MIN_SAMPLES + MAX_LAG_DAYS:
                continue
            best = _best_lag(l_series, f_series)
            if best is None:
                continue
            lag, corr, n = best
            per_follower.setdefault(follower, []).append({
                "leader": leader, "follower": follower,
                "lag_days": lag, "correlation": round(corr, 4),
                "sample_size": n,
            })

    edges: list[dict] = []
    for follower, candidates in per_follower.items():
        candidates.sort(key=lambda e: abs(e["correlation"]), reverse=True)
        edges.extend(candidates[:TOP_K_PER_FOLLOWER])
    return edges


async def _fetch_universe_prices(symbols: Iterable[str], chunk_size: int = 200) -> pd.DataFrame:
    from data.market import get_multi_ohlcv_yfinance
    symbols = list(symbols)
    frames: dict[str, pd.Series] = {}
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        try:
            data = get_multi_ohlcv_yfinance(chunk, period="1y")
        except Exception as e:
            logger.warning(f"lead_lag: ohlcv chunk failed: {e}")
            continue
        for sym, df in data.items():
            if df is None or df.empty:
                continue
            frames[sym] = df["close"]
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames)


async def run_lead_lag_job(symbols: list[str] | None = None, max_symbols: int = 500) -> int:
    """Nightly: rebuild the lead-lag graph for today, persist top-K per follower."""
    from data.scanner import get_scan_universe
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    if symbols is None:
        symbols = await get_scan_universe()
    symbols = symbols[:max_symbols]

    prices = await _fetch_universe_prices(symbols)
    if prices.empty:
        logger.warning("lead_lag: no price data, skipping")
        return 0

    edges = build_edges(prices)
    if not edges:
        logger.info("lead_lag: no edges meeting threshold this run")
        return 0

    today = date.today()
    async with AsyncSessionLocal() as session:
        # Replace today's edges atomically (so re-runs are idempotent)
        await session.execute(text(
            "DELETE FROM lead_lag_edges WHERE computed_on = :d"
        ), {"d": today})
        await session.execute(text("""
            INSERT INTO lead_lag_edges
                (leader, follower, lag_days, correlation, sample_size, computed_on)
            VALUES
                (:leader, :follower, :lag_days, :correlation, :sample_size, :computed_on)
            ON CONFLICT (leader, follower, computed_on) DO UPDATE SET
                lag_days = EXCLUDED.lag_days,
                correlation = EXCLUDED.correlation,
                sample_size = EXCLUDED.sample_size
        """), [{**e, "computed_on": today} for e in edges])
        await session.commit()

    logger.info(f"lead_lag: wrote {len(edges)} edges for {today}")
    return len(edges)


async def predictors_for(symbol: str, computed_on: date | None = None,
                          session=None) -> list[dict]:
    """Return the top-K learned predictors for one follower symbol."""
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await predictors_for(symbol, computed_on, s)
    from sqlalchemy import text
    if computed_on is None:
        result = await session.execute(text(
            "SELECT MAX(computed_on) AS d FROM lead_lag_edges"
        ))
        row = result.mappings().first()
        computed_on = row["d"] if row and row["d"] else None
        if computed_on is None:
            return []
    result = await session.execute(text("""
        SELECT leader, lag_days, correlation, sample_size
        FROM lead_lag_edges
        WHERE follower = :sym AND computed_on = :d
        ORDER BY ABS(correlation) DESC
    """), {"sym": symbol, "d": computed_on})
    return [dict(r) for r in result.mappings().all()]
