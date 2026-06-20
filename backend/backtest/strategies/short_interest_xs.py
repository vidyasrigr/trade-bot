"""
Short-interest cross-sectional generators (0619.3 Track E), reframed per research.

Raw high short interest is NOT bullish. Two distinct signals:
  - short_interest_bearish  (Boehmer-Jones-Zhang-Zhang 2008): high/rising days-to-cover
    predicts LOWER returns. LONG low-DTC, SHORT high-DTC. sign=-1.
  - squeeze_candidate: a squeeze needs short crowding AND price strength. Among the
    high-DTC quantile, LONG names with positive trailing momentum (ignition), SHORT
    high-DTC names with negative momentum (the bearish-drag majority). Captures the
    rare squeeze without treating all high-SI as bullish.

Point-in-time: at rebalance t use the most recent settlement with date <= t. Days-to-cover
from FINRA consolidated biweekly (analysis.short_interest_ingest).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade
from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions
from analysis import short_interest_ingest as si


def _dtc_asof(sym: str, t: date):
    df = si.read_symbol(sym)
    if df is None or df.empty:
        return None
    sub = df[df.index <= pd.Timestamp(t)]
    if sub.empty:
        return None
    return float(sub["days_to_cover"].iloc[-1])


def _mom_asof(panel, sym, pos, lookback=63):
    if pos - lookback < 0:
        return None
    c = panel[sym]
    a, b = c.iloc[pos - lookback], c.iloc[pos]
    if a and a > 0 and b and b > 0:
        return float(b / a - 1.0)
    return None


async def _generate(universe, start, end, *, mode, rebalance_days=21, hold_days=21,
                    quantile=0.3, panel=None, **_ignored) -> list[EquityTrade]:
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        dtc = {s: _dtc_asof(s, t) for s in panel.columns}
        dtc = {s: v for s, v in dtc.items() if v is not None and np.isfinite(v)}
        if len(dtc) < 10:
            continue
        order = sorted(dtc, key=lambda s: dtc[s])     # ascending DTC
        ns = max(1, int(round(len(order) * quantile)))
        if mode == "bearish":
            low, high = order[:ns], order[-ns:]
            longs, shorts = low, high                  # long low-SI, short high-SI
        else:  # squeeze: within the high-DTC quantile, split by momentum
            high = order[-ns:]
            moms = {s: _mom_asof(panel, s, pos) for s in high}
            moms = {s: v for s, v in moms.items() if v is not None}
            if len(moms) < 4:
                continue
            mo = sorted(moms, key=lambda s: moms[s])
            half = max(1, len(mo) // 3)
            longs, shorts = mo[-half:], mo[:half]      # long high-SI+up, short high-SI+down
        for side, names, d in (("L", longs, +1), ("S", shorts, -1)):
            if not names:
                continue
            w = 1.0 / len(names)
            for sym in names:
                ep = panel.columns.get_loc(sym)
                e, x = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
                if e > 0 and x > 0:
                    raw.append(EquityTrade(symbol=sym, direction=d, entry_date=t,
                                           exit_date=idx[pos + hold_days].date(),
                                           entry_price=e, exit_price=x, weight=w))
    return raw


async def generate_si_bearish_trades(universe, start, end, **kw):
    return await _generate(universe, start, end, mode="bearish", **kw)


async def generate_squeeze_candidate_trades(universe, start, end, **kw):
    return await _generate(universe, start, end, mode="squeeze", **kw)
