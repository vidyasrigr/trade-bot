"""
Cross-sectional 25-delta skew generator (Xing, Zhang & Zhao 2010, JFQA).

Steep put skew (25d put IV >> 25d call IV) predicts LOWER future equity returns:
the "smirk" carries information about crash fear / informed put buying. So we
short the high-skew names and go long the low-skew names, cross-sectionally,
rebalanced monthly.

This is the first signal validated on the BS-inverted IV (backtest/iv_inversion.py)
rather than vendor greeks — MarketData Starter ships no historical greeks, so we
recover per-strike IV+delta from cached option mid prices. Entirely free (cached
chains only).

Point-in-time: at rebalance date t we use the most recent cached chain with
as_of <= t (within `chain_tol_days`) and DTE in [min_dte, max_dte]. Forward
equity return is t -> t+hold, strictly after. No lookahead.
"""

from __future__ import annotations

import glob
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
from loguru import logger

from backtest.equity_engine import EquityTrade
from backtest.iv_inversion import enrich_chain_iv
from backtest.marketdata_source import DEFAULT_CACHE_ROOT, _safe


def _chain_index(symbol: str) -> list[tuple[date, date, str]]:
    """(as_of, expiry, path) for every non-empty cached chain of `symbol`."""
    base = DEFAULT_CACHE_ROOT / _safe(symbol)
    out: list[tuple[date, date, str]] = []
    for f in glob.glob(str(base / "*" / "*.parquet")):
        try:
            if os.path.getsize(f) < 3000:  # skip empty markers / tiny chains
                continue
            exp = date.fromisoformat(os.path.basename(os.path.dirname(f)))
            asof = date.fromisoformat(os.path.basename(f).replace(".parquet", ""))
            out.append((asof, exp, f))
        except (ValueError, OSError):
            continue
    return sorted(out)


def _skew_25d(df_enriched: pd.DataFrame) -> float | None:
    ok = df_enriched.dropna(subset=["iv", "delta"])
    puts = ok[ok.option_type == "P"]
    calls = ok[ok.option_type == "C"]
    if puts.empty or calls.empty:
        return None
    p25 = puts.iloc[(puts.delta + 0.25).abs().argsort()[:1]]
    c25 = calls.iloc[(calls.delta - 0.25).abs().argsort()[:1]]
    if abs(p25.delta.iloc[0] + 0.25) > 0.12 or abs(c25.delta.iloc[0] - 0.25) > 0.12:
        return None  # no strike close enough to 25 delta
    return float(p25.iv.iloc[0] - c25.iv.iloc[0])


async def generate_skew_trades(
    universe: list[str],
    start: date,
    end: date,
    *,
    rebalance_days: int = 21,
    hold_days: int = 21,
    quantile: float = 0.3,
    min_dte: int = 25,
    max_dte: int = 55,
    chain_tol_days: int = 10,
    panel: pd.DataFrame | None = None,
    **_ignored,
) -> list[EquityTrade]:
    from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    indexes = {s: _chain_index(s) for s in panel.columns}
    indexes = {s: v for s, v in indexes.items() if v}
    if len(indexes) < 6:
        logger.warning(f"skew: only {len(indexes)} names have cached chains — too few to rank")
        return []

    def chain_for(sym: str, t: date):
        best = None
        for asof, exp, path in indexes.get(sym, []):
            if asof > t or (t - asof).days > chain_tol_days:
                continue
            if not (min_dte <= (exp - asof).days <= max_dte):
                continue
            best = (asof, exp, path)  # latest qualifying (list is sorted asc)
        return best

    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        skews: dict[str, float] = {}
        for sym in indexes:
            cf = chain_for(sym, t)
            if cf is None:
                continue
            asof, exp, path = cf
            try:
                df = enrich_chain_iv(pd.read_parquet(path), asof, exp)
            except Exception:
                continue
            sk = _skew_25d(df)
            if sk is not None:
                skews[sym] = sk
        if len(skews) < 6:
            continue
        order = sorted(skews, key=lambda s: skews[s])
        n_side = max(1, int(round(len(order) * quantile)))
        longs = order[:n_side]          # low skew -> long
        shorts = order[-n_side:]        # high skew -> short (bearish)
        for side, names, direction in (("L", longs, +1), ("S", shorts, -1)):
            w = 1.0 / len(names)
            for sym in names:
                ep = panel.columns.get_loc(sym)
                entry_px = float(panel.iloc[pos, ep])
                exit_px = float(panel.iloc[pos + hold_days, ep])
                if entry_px > 0 and exit_px > 0:
                    raw.append(EquityTrade(
                        symbol=sym, direction=direction,
                        entry_date=t, exit_date=idx[pos + hold_days].date(),
                        entry_price=entry_px, exit_price=exit_px, weight=w,
                        signal=f"skew25_{side}_{skews[sym]:+.3f}",
                    ))
    return raw
