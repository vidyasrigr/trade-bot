"""
Backtest performance metrics.

Includes the deflated Sharpe ratio (Bailey & López de Prado 2014) — the guard
against promoting strategies that only look good because many variants were tried.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

EULER_GAMMA = 0.5772156649015329


def sharpe(returns: np.ndarray, periods_per_year: int = 252) -> float:
    r = np.asarray(returns, dtype=float)
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * math.sqrt(periods_per_year))


def max_drawdown(equity: np.ndarray) -> float:
    """Max peak-to-trough drawdown as a positive fraction (0.25 = -25%)."""
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 2:
        return 0.0
    peaks = np.maximum.accumulate(eq)
    dd = (peaks - eq) / np.where(peaks > 0, peaks, 1.0)
    return float(dd.max())


def probabilistic_sharpe(returns: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """
    PSR (Bailey & López de Prado): P(true SR > sr_benchmark) given the observed
    per-period SR, adjusted for skew/kurtosis and sample length.
    sr_benchmark is PER-PERIOD (not annualized).
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 3 or r.std(ddof=1) == 0:
        return 0.0
    sr = float(r.mean() / r.std(ddof=1))
    from scipy.stats import kurtosis, skew
    g3 = float(skew(r))
    g4 = float(kurtosis(r, fisher=False))
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr * sr))
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / denom
    return float(norm.cdf(z))


def deflated_sharpe(returns: np.ndarray, num_trials: int) -> float:
    """
    DSR: PSR against the expected max Sharpe of `num_trials` unskilled tries.
    Pass the honest number of strategy variants tested — that is the whole point.
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 3 or r.std(ddof=1) == 0 or num_trials < 1:
        return 0.0
    sr = float(r.mean() / r.std(ddof=1))
    # Variance of the SR estimator (per-period) as proxy for cross-trial variance
    from scipy.stats import kurtosis, skew
    g3 = float(skew(r))
    g4 = float(kurtosis(r, fisher=False))
    var_sr = max(1e-12, (1 - g3 * sr + (g4 - 1) / 4 * sr * sr) / (n - 1))
    if num_trials == 1:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(var_sr) * (
            (1 - EULER_GAMMA) * norm.ppf(1 - 1 / num_trials)
            + EULER_GAMMA * norm.ppf(1 - 1 / (num_trials * math.e))
        )
    return probabilistic_sharpe(r, sr_benchmark=sr0)


def summarize(trade_pnls: list[float], equity: np.ndarray,
              daily_returns: np.ndarray, num_trials: int = 1) -> dict:
    pnls = np.asarray(trade_pnls, dtype=float)
    wins = pnls[pnls > 0]
    return {
        "num_trades": int(len(pnls)),
        "win_rate": float(len(wins) / len(pnls)) if len(pnls) else 0.0,
        "total_pnl": float(pnls.sum()),
        "avg_pnl": float(pnls.mean()) if len(pnls) else 0.0,
        "expectancy": float(pnls.mean()) if len(pnls) else 0.0,
        "sharpe": sharpe(daily_returns),
        "probabilistic_sharpe": probabilistic_sharpe(daily_returns),
        "deflated_sharpe": deflated_sharpe(daily_returns, num_trials),
        "max_drawdown": max_drawdown(equity),
    }
