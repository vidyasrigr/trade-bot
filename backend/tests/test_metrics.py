"""Backtest metrics — Sharpe, deflated Sharpe, max DD."""

import math

import numpy as np

from backtest.metrics import (
    deflated_sharpe, max_drawdown, probabilistic_sharpe, sharpe, summarize,
)


def test_sharpe_zero_for_zero_variance():
    """Single-element series can't have variance — returns 0."""
    assert sharpe(np.array([0.01])) == 0.0
    assert sharpe(np.array([])) == 0.0


def test_sharpe_positive_for_positive_drift():
    rng = np.random.default_rng(42)
    rets = 0.001 + rng.normal(0, 0.01, 250)
    s = sharpe(rets)
    assert s > 0


def test_max_drawdown_zero_for_monotone_uptrend():
    equity = np.linspace(100, 200, 100)
    assert max_drawdown(equity) == 0.0


def test_max_drawdown_positive_when_equity_drops():
    equity = np.array([100.0, 120.0, 90.0, 110.0])
    dd = max_drawdown(equity)
    assert abs(dd - 0.25) < 1e-9   # 120 → 90 = 25% drawdown


def test_probabilistic_sharpe_is_in_unit_interval():
    rng = np.random.default_rng(0)
    rets = 0.0005 + rng.normal(0, 0.01, 500)
    p = probabilistic_sharpe(rets)
    assert 0.0 <= p <= 1.0


def test_deflated_sharpe_below_psr_when_many_trials():
    """num_trials > 1 should make DSR ≤ PSR (multiple-testing penalty)."""
    rng = np.random.default_rng(7)
    rets = 0.001 + rng.normal(0, 0.015, 400)
    psr = probabilistic_sharpe(rets)
    dsr = deflated_sharpe(rets, num_trials=50)
    assert dsr <= psr


def test_summarize_returns_expected_keys():
    rng = np.random.default_rng(3)
    pnls = [float(x) for x in rng.normal(100, 50, 40)]
    equity = np.cumsum(pnls) + 100_000
    daily = (np.array(pnls) - np.mean(pnls)) / 100_000
    out = summarize(pnls, equity, daily, num_trials=5)
    for key in ("num_trades", "win_rate", "total_pnl", "sharpe",
                 "probabilistic_sharpe", "deflated_sharpe", "max_drawdown"):
        assert key in out
