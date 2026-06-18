"""
Equity / forward-return backtest engine.

The options engine (backtest/engine.py) prices multi-leg structures from EOD
chains. Cross-sectional equity signals (momentum, PEAD, insider, squeeze,
lead-lag) don't need option pricing — each "trade" is a directional stock
position opened at entry_price and closed at exit_price, labeled with a forward
return. This engine aggregates those positions into a portfolio return series
and reports the SAME metrics shape as BacktestReport so scripts/run_full_validation
and its report renderer work unchanged.

Statistical treatment (this is the part that matters for not fooling ourselves):
  - win_rate / expectancy / total_pnl are per-POSITION.
  - sharpe / deflated_sharpe / max_drawdown are computed on the PORTFOLIO RETURN
    SERIES (one observation per rebalance cohort = trades sharing an entry_date),
    NOT per position. DSR on per-position returns would massively overstate n and
    understate the multiple-testing penalty. The cohort series is the honest unit.

Cohort return contract:
  Each EquityTrade carries a `weight` and `direction` (+1 long / -1 short). The
  cohort return is sum_i(weight_i * direction_i * net_return_i). Generators set
  weights so a cohort sums sensibly (e.g. dollar-neutral long-short: longs share
  +1.0, shorts share -1.0 -> cohort return = mean(long fwd) - mean(short fwd)).

Costs:
  cost_bps is charged per side (entry + exit) against each position's return.
  Default 5 bps/side (10 bps round-trip) — a reasonable liquid-equity assumption.
  Illiquid names cost more; per-name calibration is PENDING R.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from backtest.metrics import deflated_sharpe, max_drawdown, sharpe as _sharpe


@dataclass(frozen=True)
class EquityTrade:
    symbol: str
    direction: int          # +1 long, -1 short
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    weight: float = 1.0     # portfolio weight within its entry-date cohort
    signal: str = ""


@dataclass
class EquityResult:
    trade: EquityTrade
    gross_return: float     # direction * (exit/entry - 1)
    net_return: float       # gross - round-trip cost
    pnl: float              # dollars on a per-position notional


@dataclass
class EquityReport:
    results: list
    equity_curve: pd.Series
    metrics: dict = field(default_factory=dict)


def _periods_per_year(cohort_dates: list[date]) -> int:
    """Infer annualization factor from the median spacing of rebalance dates."""
    if len(cohort_dates) < 2:
        return 12
    days = np.diff([pd.Timestamp(d).value for d in sorted(cohort_dates)]) / 8.64e13
    med = float(np.median(days))
    if med <= 0:
        return 12
    return int(round(365.0 / med))


async def run_equity_backtest(
    trades: list[EquityTrade],
    num_trials: int = 1,
    *,
    cost_bps: float = 5.0,
    notional_per_position: float = 10_000.0,
    starting_equity: float = 100_000.0,
) -> EquityReport:
    """
    Aggregate forward-return-labeled positions into a portfolio return series and
    summarize. async to match the options engine's call convention in the runner.
    """
    if not trades:
        return EquityReport(results=[], equity_curve=pd.Series(dtype=float),
                            metrics={"num_trades": 0})

    rt_cost = 2.0 * cost_bps / 1e4  # round-trip cost as a fraction
    results: list[EquityResult] = []
    for t in trades:
        if t.entry_price <= 0 or t.exit_price <= 0:
            continue
        gross = t.direction * (t.exit_price / t.entry_price - 1.0)
        net = gross - rt_cost
        results.append(EquityResult(
            trade=t, gross_return=gross, net_return=net,
            pnl=net * notional_per_position,
        ))
    if not results:
        return EquityReport(results=[], equity_curve=pd.Series(dtype=float),
                            metrics={"num_trades": 0})

    # Portfolio return series: one observation per entry-date cohort.
    cohort: dict[date, float] = {}
    for r in results:
        cohort[r.trade.entry_date] = cohort.get(r.trade.entry_date, 0.0) + \
            r.trade.weight * r.net_return
    cohort_dates = sorted(cohort)
    cohort_rets = np.array([cohort[d] for d in cohort_dates], dtype=float)

    equity_vals = starting_equity * np.cumprod(1.0 + cohort_rets)
    equity = pd.Series(equity_vals, index=pd.to_datetime(cohort_dates))

    ppy = _periods_per_year(cohort_dates)
    pos_rets = np.array([r.net_return for r in results], dtype=float)
    wins = pos_rets[pos_rets > 0]

    metrics = {
        "num_trades": int(len(results)),
        "win_rate": float(len(wins) / len(results)),
        "total_pnl": float(sum(r.pnl for r in results)),
        "avg_pnl": float(np.mean([r.pnl for r in results])),
        "expectancy": float(pos_rets.mean()),
        "sharpe": float(_sharpe(cohort_rets, periods_per_year=ppy)),
        "deflated_sharpe": float(deflated_sharpe(cohort_rets, num_trials)),
        "max_drawdown": float(max_drawdown(equity_vals)),
        "num_cohorts": int(len(cohort_rets)),
        "periods_per_year": ppy,
    }
    return EquityReport(results=results, equity_curve=equity, metrics=metrics)
