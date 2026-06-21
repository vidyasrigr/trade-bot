"""
True daily-portfolio MTM simulator (0620.2 Phase 2.0, GPT amendment B).

equity_engine.py reports per-ENTRY-DATE cohort returns — it does NOT account for many
overlapping holding-period cohorts running at once. So its max_drawdown understates the
real account drawdown (when several overlapping cohorts draw down on the same days, the
account feels the sum). Phase 3 grades candidates on DD, so DD must be the TRUE account
drawdown, not cohort DD.

This simulates a daily account holding all overlapping cohorts:
  - each cohort = trades sharing an entry_date; its daily return rc(t) = sum_i
    weight_i*dir_i*ret_i(t), net of round-trip cost charged on entry,
  - the account deploys equal capital across the cohorts open on day t (gross ~1x),
    so account daily return R(t) = mean of open cohorts' rc(t),
  - equity(t) = cumprod(1+R(t)); true_account_dd = max drawdown of that curve.

Also reports: sharpe (daily, annualized), CAGR, turnover, max concurrent cohorts,
max gross exposure, max single-day sector concentration (if sector_map given).
DD is scale-invariant, so the equal-capital normalization does not bias it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade


@dataclass
class PortfolioResult:
    metrics: dict = field(default_factory=dict)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


def _daily_returns(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.pct_change()


def run_long_only_account(
    trades: list[EquityTrade],
    panel: pd.DataFrame,
    *,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
    fully_invested_when_active: bool = True,
) -> PortfolioResult:
    """Cash-aware EQUAL-WEIGHT long-only account for timing strategies (e.g. ETF dip-buys).

    Each day, capital is split EQUALLY across all currently-open positions (gross <= 100%),
    and sits in CASH (0 return) when nothing is open. This is the realistic sizing for a
    dip-buy strategy — 20 ETFs triggering the same day each get ~5%, not 20x leverage — so
    the drawdown is a true account DD, not a leverage artifact. Round-trip cost per position.
    """
    if not trades or panel is None or panel.empty:
        return PortfolioResult(metrics={"num_trades": 0, "true_account_dd": None})
    rets = panel.pct_change()
    idx = panel.index
    rt_cost = 2.0 * cost_bps / 1e4

    # per-day list of (symbol-position daily return) for open positions
    open_legs: dict[pd.Timestamp, list[float]] = {}
    cost_by_day: dict[pd.Timestamp, float] = {}
    for tr in trades:
        if tr.symbol not in panel.columns:
            continue
        e, x = pd.Timestamp(tr.entry_date), pd.Timestamp(tr.exit_date)
        seg = rets.loc[(rets.index > e) & (rets.index <= x), tr.symbol]
        if seg.empty:
            continue
        for d, r in seg.items():
            open_legs.setdefault(d, []).append(float(r))
        # charge round-trip cost on the first held day
        cost_by_day[seg.index[0]] = cost_by_day.get(seg.index[0], 0.0) + rt_cost

    if not open_legs:
        return PortfolioResult(metrics={"num_trades": len(trades), "true_account_dd": None})

    days = sorted(set(open_legs) | set(cost_by_day))
    acct = []
    n_open_series = []
    for d in days:
        legs = open_legs.get(d, [])
        n = len(legs)
        n_open_series.append(n)
        # equal-weight across open positions; cash (0) if none open
        day_ret = (sum(legs) / n) if (n and fully_invested_when_active) else (sum(legs) if n else 0.0)
        # cost: spread the day's entries' cost across the equal weights
        day_ret -= cost_by_day.get(d, 0.0) / max(n, 1)
        acct.append(day_ret)
    acct = pd.Series(acct, index=pd.to_datetime(days)).sort_index()
    equity = (1.0 + acct).cumprod()
    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()
    ann = np.sqrt(periods_per_year)
    sharpe = (acct.mean() / acct.std() * ann) if acct.std() > 0 else 0.0
    n_years = max(len(acct) / periods_per_year, 1e-6)
    cagr = equity.iloc[-1] ** (1 / n_years) - 1.0 if equity.iloc[-1] > 0 else None
    return PortfolioResult(
        metrics={
            "num_trades": len(trades),
            "account_days": int(len(acct)),
            "true_account_dd": float(abs(dd)),
            "sharpe_daily": float(sharpe),
            "cagr": float(cagr) if cagr is not None else None,
            "max_concurrent_positions": int(max(n_open_series)) if n_open_series else 0,
            "pct_days_invested": float(np.mean([1 if n else 0 for n in n_open_series])),
        },
        equity_curve=equity,
    )


def run_daily_portfolio(
    trades: list[EquityTrade],
    panel: pd.DataFrame,
    *,
    sector_map: dict[str, str] | None = None,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
) -> PortfolioResult:
    if not trades or panel is None or panel.empty:
        return PortfolioResult(metrics={"num_trades": 0, "true_account_dd": None})

    rets = _daily_returns(panel)
    idx = panel.index
    pos_of = {ts: i for i, ts in enumerate(idx)}
    rt_cost = 2.0 * cost_bps / 1e4

    # group trades into cohorts by entry_date
    cohorts: dict[date, list[EquityTrade]] = {}
    for t in trades:
        cohorts.setdefault(t.entry_date, []).append(t)

    # each cohort -> its own daily return series over [entry, exit)
    cohort_daily: dict[date, pd.Series] = {}
    open_count = pd.Series(0, index=idx, dtype=int)
    gross_by_day = pd.Series(0.0, index=idx, dtype=float)
    sector_day: dict[pd.Timestamp, dict[str, float]] = {}

    for entry, ts in cohorts.items():
        e_ts = pd.Timestamp(entry)
        if e_ts not in pos_of:
            # snap to next available trading day
            future = idx[idx >= e_ts]
            if len(future) == 0:
                continue
            e_ts = future[0]
        legs = []
        for tr in ts:
            sym = tr.symbol
            if sym not in panel.columns:
                continue
            x_ts = pd.Timestamp(tr.exit_date)
            seg = rets.loc[(rets.index > e_ts) & (rets.index <= x_ts), sym]
            if seg.empty:
                continue
            contrib = tr.weight * tr.direction * seg
            # round-trip cost charged on the first held day
            contrib.iloc[0] -= rt_cost * abs(tr.weight)
            legs.append((sym, tr.weight, contrib))
        if not legs:
            continue
        cret = pd.concat([c for _, _, c in legs], axis=1).sum(axis=1)
        cohort_daily[entry] = cret
        # bookkeeping: open cohorts, gross, sector exposure per day
        for d in cret.index:
            open_count[d] += 1
            gw = sum(abs(w) for _, w, _ in legs)
            gross_by_day[d] += gw
            if sector_map:
                sd = sector_day.setdefault(d, {})
                for sym, w, _ in legs:
                    sec = sector_map.get(sym, "Unknown")
                    sd[sec] = sd.get(sec, 0.0) + abs(w)

    if not cohort_daily:
        return PortfolioResult(metrics={"num_trades": len(trades), "true_account_dd": None})

    # account daily return = mean of open cohorts' returns (equal capital across cohorts)
    mat = pd.DataFrame(cohort_daily)               # index=days, cols=cohorts (NaN when closed)
    account_ret = mat.mean(axis=1).fillna(0.0).sort_index()
    equity = (1.0 + account_ret).cumprod()

    # drawdown on the true account curve
    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()

    ann = np.sqrt(periods_per_year)
    sharpe = (account_ret.mean() / account_ret.std() * ann) if account_ret.std() > 0 else 0.0
    n_years = max(len(account_ret) / periods_per_year, 1e-6)
    cagr = equity.iloc[-1] ** (1 / n_years) - 1.0 if equity.iloc[-1] > 0 else None

    # turnover: total entered notional / equity / yr (each cohort deploys ~gross once)
    total_entered = sum(sum(abs(t.weight) for t in ts) for ts in cohorts.values())
    turnover = total_entered / max(len(cohort_daily), 1) / n_years

    # max single-day sector concentration
    max_sec_conc = None
    if sector_map and sector_day:
        max_sec_conc = max(
            (max(sd.values()) / sum(sd.values())) for sd in sector_day.values() if sum(sd.values()) > 0
        )

    return PortfolioResult(
        metrics={
            "num_trades": len(trades),
            "num_cohorts": len(cohort_daily),
            "account_days": int(len(account_ret)),
            "true_account_dd": float(abs(dd)),
            "sharpe_daily": float(sharpe),
            "cagr": float(cagr) if cagr is not None else None,
            "max_concurrent_cohorts": int(open_count.max()),
            "max_gross_exposure": float(gross_by_day.max()),
            "turnover_per_yr": float(turnover),
            "max_sector_concentration": (round(float(max_sec_conc), 3)
                                         if max_sec_conc is not None else None),
        },
        equity_curve=equity,
    )
