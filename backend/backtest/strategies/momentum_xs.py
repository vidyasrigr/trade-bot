"""
Cross-sectional 12-1 momentum backtest (Jegadeesh-Titman 1993).

There is no equity-signal backtest harness in this repo (backtest/engine.py is
options-only), so this is a minimal, self-contained cross-sectional tester:

  - Monthly rebalance (every 21 trading days).
  - Formation at date t: momentum = P[t-21] / P[t-252] - 1  (12 months, skipping
    the most recent month to avoid 1-month reversal). All formation data ≤ t.
  - Forward return strictly after t: P[t+21] / P[t] - 1  (no lookahead).
  - Long the top quintile, short the bottom quintile, equal-weight; the
    long-short spread is the strategy return for that month.

DSR uses backtest.metrics.deflated_sharpe on the monthly return series — same
methodology as the VRP results, so the numbers are comparable. Annualized Sharpe
uses periods_per_year=12 (monthly), unlike summarize()'s 252-day default.

Caveat baked in by the data: a 3.5y train / 1.5y walk-forward window gives only
~40 / ~18 monthly observations, so the DSR is low-power. Treat a marginal result
as SANDBOX, not PASS.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backtest.metrics import deflated_sharpe, max_drawdown


def _month_end_indices(idx: pd.DatetimeIndex) -> list[int]:
    """Positions of the last trading day in each month."""
    s = pd.Series(range(len(idx)), index=idx)
    return [int(g.iloc[-1]) for _, g in s.groupby([idx.year, idx.month])]


def run_momentum_backtest(
    closes: pd.DataFrame,
    start: date,
    end: date,
    *,
    quantile: float = 0.2,
    lookback: int = 252,
    skip: int = 21,
    hold: int = 21,
    num_trials: int = 20,
) -> dict:
    """
    closes: wide DataFrame, DatetimeIndex × symbols, daily close. Should include
    >=1y of history before `start` so the first in-window formation has lookback.
    Returns a metrics dict for the [start, end] window.
    """
    closes = closes.sort_index()
    idx = closes.index
    me = _month_end_indices(idx)

    rets: list[float] = []
    dates: list[pd.Timestamp] = []
    for pos in me:
        t = idx[pos]
        if not (pd.Timestamp(start) <= t <= pd.Timestamp(end)):
            continue
        if pos - lookback < 0 or pos + hold >= len(idx):
            continue
        p_t = closes.iloc[pos]
        p_skip = closes.iloc[pos - skip]
        p_back = closes.iloc[pos - lookback]
        p_fwd = closes.iloc[pos + hold]

        mom = (p_skip / p_back - 1.0)
        fwd = (p_fwd / p_t - 1.0)
        valid = mom.notna() & fwd.notna() & (p_t > 0) & (p_back > 0)
        mom, fwd = mom[valid], fwd[valid]
        if len(mom) < 10:  # need enough names to form quintiles
            continue

        n_side = max(1, int(round(len(mom) * quantile)))
        order = mom.sort_values()
        longs = order.index[-n_side:]
        shorts = order.index[:n_side]
        ls = float(fwd[longs].mean() - fwd[shorts].mean())
        rets.append(ls)
        dates.append(t)

    if len(rets) < 3:
        return {"num_trades": len(rets), "note": "insufficient rebalances"}

    r = np.asarray(rets, dtype=float)
    equity = 100_000.0 * np.cumprod(1.0 + r)
    ann_sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(12)) if r.std(ddof=1) > 0 else 0.0
    wins = r[r > 0]
    return {
        "num_trades": int(len(r)),               # monthly rebalances
        "win_rate": float(len(wins) / len(r)),
        "total_return": float(equity[-1] / 100_000.0 - 1.0),
        "avg_monthly_ls": float(r.mean()),
        "sharpe_annualized": ann_sharpe,
        "deflated_sharpe": float(deflated_sharpe(r, num_trials)),
        "max_drawdown": float(max_drawdown(equity)),
        "first": str(dates[0].date()), "last": str(dates[-1].date()),
    }
