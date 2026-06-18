"""
Cross-sectional momentum generator (Jegadeesh-Titman 1993) for the equity engine.

generate_momentum_trades(universe, start, end, lookback_days, rebalance_days)
returns a list[EquityTrade] — decile (or quintile on small universes) long-short,
rebalanced every `rebalance_days` trading days, forward-return labeled.

Point-in-time:
  - Formation at rebalance date t: mom = P[t-skip] / P[t-lookback] - 1, skip=21
    trading days (the "1" in 12-1, avoids 1-month reversal). All formation data <= t.
  - Position held t -> t+rebalance_days; exit price strictly after t. No lookahead.

Weights: longs share +1.0 / n_long, shorts share -1.0 / n_short, so the cohort
return the equity engine computes = mean(long fwd) - mean(short fwd).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade


# Process-level panel cache. _close_panel is synchronous and blocks the event
# loop during the yfinance download, so without this every equity variant triggers
# its own sequential ~150-name fetch — and yfinance rate-limits partway, handing
# later variants (PEAD, lead_lag) empty panels = false 0-trade verdicts. One fetch
# per (universe, period) for the whole run fixes it.
_PANEL_CACHE: dict[tuple, pd.DataFrame] = {}


def _close_panel(universe: list[str], period: str = "10y") -> pd.DataFrame:
    from data.market import get_multi_ohlcv_yfinance
    key = (tuple(sorted(set(universe))), period)
    if key in _PANEL_CACHE:
        return _PANEL_CACHE[key]
    prices = get_multi_ohlcv_yfinance(list(dict.fromkeys(universe)), period=period)
    cols = {s: df["close"] for s, df in prices.items()
            if df is not None and not df.empty and len(df) > 260}
    if not cols:
        return pd.DataFrame()  # don't cache an empty (rate-limited) result
    panel = pd.DataFrame(cols)
    panel.index = pd.to_datetime(panel.index)
    panel = panel.sort_index()
    _PANEL_CACHE[key] = panel
    return panel


def _rebalance_positions(idx: pd.DatetimeIndex, rebalance_days: int) -> list[int]:
    """Integer positions spaced rebalance_days apart across the index."""
    return list(range(0, len(idx), max(1, rebalance_days)))


async def generate_momentum_trades(
    universe: list[str],
    start: date,
    end: date,
    *,
    lookback_days: int = 252,
    rebalance_days: int = 21,
    skip_days: int = 21,
    panel: pd.DataFrame | None = None,
    **_ignored,
) -> list[EquityTrade]:
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    n_names = panel.shape[1]
    q = 0.1 if n_names >= 50 else 0.2  # decile on big universe, quintile on small

    trades: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos]
        if not (pd.Timestamp(start) <= t <= pd.Timestamp(end)):
            continue
        if pos - lookback_days < 0 or pos + rebalance_days >= len(idx):
            continue
        p_t = panel.iloc[pos]
        p_skip = panel.iloc[pos - skip_days]
        p_back = panel.iloc[pos - lookback_days]
        p_fwd = panel.iloc[pos + rebalance_days]
        exit_date = idx[pos + rebalance_days].date()

        mom = p_skip / p_back - 1.0
        valid = mom.notna() & p_t.notna() & p_fwd.notna() & (p_t > 0) & (p_back > 0)
        mom = mom[valid]
        if len(mom) < 10:
            continue
        n_side = max(1, int(round(len(mom) * q)))
        order = mom.sort_values()
        shorts = list(order.index[:n_side])
        longs = list(order.index[-n_side:])

        for side, names, direction in (("L", longs, +1), ("S", shorts, -1)):
            w = (1.0 / len(names)) if names else 0.0
            for sym in names:
                trades.append(EquityTrade(
                    symbol=sym, direction=direction,
                    entry_date=t.date(), exit_date=exit_date,
                    entry_price=float(p_t[sym]), exit_price=float(p_fwd[sym]),
                    weight=w, signal=f"momentum_lookback{lookback_days}_{side}",
                ))
    return trades
