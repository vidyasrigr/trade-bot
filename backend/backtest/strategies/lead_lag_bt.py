"""
Supply-chain / economic-link lead-lag generator (Cohen & Frazzini 2008).

Reuses analysis.lead_lag.build_edges (the same learner the live nightly job uses)
to discover leader->follower edges, then trades the follower in the direction the
leader's recent move predicts.

Point-in-time:
  At each rebalance date t, edges are learned on the trailing `correlation_window_days`
  ending at t (data <= t only). The leader's signal return is measured over the last
  `lag` days ending at t. The follower position is entered at t and exited hold_days
  later (strictly after t). No future data enters edge-learning, signal, or fill.

Compute is bounded by top_leaders (default 25) and a monthly rebalance.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from analysis.lead_lag import build_edges
from backtest.equity_engine import EquityTrade


async def generate_lead_lag_trades(
    universe: list[str],
    start: date,
    end: date,
    *,
    correlation_window_days: int = 252,
    max_lag_days: int = 15,
    min_abs_corr: float = 0.25,
    hold_days: int = 10,
    top_leaders: int = 25,
    rebalance_days: int = 21,
    panel: pd.DataFrame | None = None,
    **_ignored,
) -> list[EquityTrade]:
    from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index

    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end):
            continue
        if pos - correlation_window_days < 0 or pos + hold_days >= len(idx):
            continue
        window = panel.iloc[pos - correlation_window_days: pos + 1]
        edges = build_edges(window, top_leaders=top_leaders)
        if not edges:
            continue

        # Aggregate per-follower signed conviction from its leader edges.
        conviction: dict[str, float] = {}
        for e in edges:
            leader, follower, lag, corr = (
                e["leader"], e["follower"], e["lag_days"], e["correlation"])
            if follower not in panel.columns or leader not in panel.columns:
                continue
            lead_series = window[leader].dropna()
            if len(lead_series) <= lag:
                continue
            lead_ret = float(lead_series.iloc[-1] / lead_series.iloc[-1 - lag] - 1.0)
            conviction[follower] = conviction.get(follower, 0.0) + corr * np.sign(lead_ret)

        signals = {f: c for f, c in conviction.items() if c != 0}
        if len(signals) < 4:
            continue
        n = len(signals)
        for follower, c in signals.items():
            fp = panel.columns.get_loc(follower)
            entry_px = float(panel.iloc[pos, fp])
            exit_px = float(panel.iloc[pos + hold_days, fp])
            if entry_px <= 0 or exit_px <= 0:
                continue
            raw.append(EquityTrade(
                symbol=follower, direction=int(np.sign(c)),
                entry_date=t, exit_date=idx[pos + hold_days].date(),
                entry_price=entry_px, exit_price=exit_px,
                weight=1.0 / n, signal=f"lead_lag_conv{c:+.2f}",
            ))
    return raw
