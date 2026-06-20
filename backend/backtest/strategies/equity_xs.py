"""
Cross-sectional equity-primitive generators (0619.3 Track A1 + primitive decomposition).

Each generator scores every name at rebalance t from its PIT close history, ranks
cross-sectionally, goes decile/quintile long-short, forward-return labelled t->t+hold.
Same EquityTrade/run_equity_backtest contract as momentum_xs_v2, so the sweep + MTM +
costs apply unchanged.

Primitives decompose the engine rollups (V's explicit ask) so we learn which carries
edge. Standard academic/TA definitions; sign documented per signal. `sign=+1` longs the
HIGH-score names, `-1` longs the LOW-score names.

  RSI(14)        mean-reversion: long LOW rsi (oversold)            sign=-1
  MACD hist      trend: long HIGH                                   sign=+1
  Stochastic %K  mean-reversion: long LOW                           sign=-1
  ROC(63)        momentum: long HIGH                                sign=+1
  EMA align      trend (ema20>50>200 stack): long HIGH              sign=+1
  price slope    trend (norm. regression slope): long HIGH         sign=+1
  ADX*dir        trend strength x direction: long HIGH             sign=+1
  Bollinger wid  low-vol anomaly: long LOW width                    sign=-1
  ATR%           low-vol anomaly: long LOW                          sign=-1
  realized vol   low-vol anomaly: long LOW                          sign=-1
  support_res    52w-range position (Donchian): long HIGH (breakout)sign=+1
Rollups (composite z-mean of constituent primitives):
  trend          (ema_align + slope + adx)                          sign=+1
  risk           (bb_width + atr + rvol, low-vol)                   sign=-1
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade
from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions


# --- indicator helpers: take a close Series, return latest scalar -------------

def _rsi(c: pd.Series, n: int = 14):
    if len(c) < n + 1:
        return None
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    v = 100 - 100 / (1 + rs)
    return float(v.iloc[-1]) if pd.notna(v.iloc[-1]) else None


def _macd_hist(c: pd.Series):
    if len(c) < 35:
        return None
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    sig = macd.ewm(span=9).mean()
    h = (macd - sig).iloc[-1]
    return float(h / c.iloc[-1]) if c.iloc[-1] else None   # normalize by price


def _stoch(c: pd.Series, n: int = 14):
    if len(c) < n:
        return None
    lo, hi = c.iloc[-n:].min(), c.iloc[-n:].max()
    return float((c.iloc[-1] - lo) / (hi - lo)) if hi > lo else None


def _roc(c: pd.Series, n: int = 63):
    if len(c) < n + 1:
        return None
    return float(c.iloc[-1] / c.iloc[-n - 1] - 1.0)


def _ema_align(c: pd.Series):
    if len(c) < 200:
        return None
    e20, e50, e200 = c.ewm(span=20).mean().iloc[-1], c.ewm(span=50).mean().iloc[-1], c.ewm(span=200).mean().iloc[-1]
    # stacked-bull score: +1 each for e20>e50, e50>e200, price>e200
    return float((e20 > e50) + (e50 > e200) + (c.iloc[-1] > e200))


def _slope(c: pd.Series, n: int = 63):
    if len(c) < n:
        return None
    y = np.log(c.iloc[-n:].values)
    x = np.arange(n)
    b = np.polyfit(x, y, 1)[0]
    return float(b)   # log-price slope per day (annualizable)


def _adx_dir(c: pd.Series, n: int = 14):
    """Close-only proxy: |trend| strength x sign, via slope/vol."""
    if len(c) < n + 1:
        return None
    rets = c.pct_change().iloc[-n:]
    vol = rets.std()
    if not vol or np.isnan(vol):
        return None
    return float(rets.mean() / vol)   # signed trend strength (sharpe-like)


def _bb_width(c: pd.Series, n: int = 20):
    if len(c) < n:
        return None
    m, s = c.iloc[-n:].mean(), c.iloc[-n:].std()
    return float(4 * s / m) if m else None


def _atr_pct(c: pd.Series, n: int = 14):
    if len(c) < n + 1:
        return None
    tr = c.diff().abs().iloc[-n:].mean()
    return float(tr / c.iloc[-1]) if c.iloc[-1] else None


def _rvol(c: pd.Series, n: int = 21):
    if len(c) < n + 1:
        return None
    r = np.log(c.iloc[-(n + 1):]).diff().dropna()
    return float(r.std() * np.sqrt(252)) if len(r) else None


def _support_res(c: pd.Series, n: int = 252):
    if len(c) < 60:
        return None
    w = c.iloc[-n:]
    lo, hi = w.min(), w.max()
    return float((c.iloc[-1] - lo) / (hi - lo)) if hi > lo else None


_SCORERS = {
    "rsi_14": (_rsi, -1), "macd": (_macd_hist, +1), "stoch": (_stoch, -1),
    "roc_63": (_roc, +1), "ema_align": (_ema_align, +1), "slope": (_slope, +1),
    "adx_dir": (_adx_dir, +1), "bb_width": (_bb_width, -1), "atr_pct": (_atr_pct, -1),
    "rvol": (_rvol, -1), "support_res": (_support_res, +1),
}


async def _xs_generate(universe, start, end, *, scorer, sign,
                       rebalance_days=21, hold_days=21, quantile=0.2,
                       panel=None, **_ignored) -> list[EquityTrade]:
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
        scores: dict[str, float] = {}
        for sym in panel.columns:
            c = panel[sym].iloc[:pos + 1].dropna()
            if len(c) < 60:
                continue
            v = scorer(c)
            if v is not None and np.isfinite(v):
                scores[sym] = v
        if len(scores) < 10:
            continue
        order = sorted(scores, key=lambda s: scores[s])
        ns = max(1, int(round(len(order) * quantile)))
        low, high = order[:ns], order[-ns:]
        longs, shorts = (high, low) if sign > 0 else (low, high)
        for side, names, d in (("L", longs, +1), ("S", shorts, -1)):
            w = 1.0 / len(names)
            for sym in names:
                ep = panel.columns.get_loc(sym)
                e, x = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
                if e > 0 and x > 0:
                    raw.append(EquityTrade(symbol=sym, direction=d, entry_date=t,
                                           exit_date=idx[pos + hold_days].date(),
                                           entry_price=e, exit_price=x, weight=w,
                                           signal=f"{side}_{scores[sym]:+.3f}"))
    return raw


def make_generator(primitive: str):
    """Factory: returns an async generator for a named primitive in _SCORERS."""
    scorer, sign = _SCORERS[primitive]

    async def _gen(universe, start, end, **kw):
        kw.pop("lookback_days", None)
        return await _xs_generate(universe, start, end, scorer=scorer, sign=sign, **kw)
    _gen.__name__ = f"generate_{primitive}_trades"
    return _gen


# --- rollups: composite z-mean of constituent primitives ---------------------

async def _rollup_generate(universe, start, end, *, parts, sign,
                           rebalance_days=21, hold_days=21, quantile=0.2,
                           panel=None, **_ignored) -> list[EquityTrade]:
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    scorers = [_SCORERS[p][0] for p in parts]
    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        # per-primitive raw scores, then z-score each, then mean
        rawmat: dict[str, list] = {}
        for sym in panel.columns:
            c = panel[sym].iloc[:pos + 1].dropna()
            if len(c) < 60:
                continue
            vals = [s(c) for s in scorers]
            if any(v is None or not np.isfinite(v) for v in vals):
                continue
            rawmat[sym] = vals
        if len(rawmat) < 10:
            continue
        arr = np.array(list(rawmat.values()))
        mu, sd = arr.mean(0), arr.std(0)
        sd[sd == 0] = 1.0
        z = (arr - mu) / sd
        comp = {sym: float(z[i].mean()) for i, sym in enumerate(rawmat)}
        order = sorted(comp, key=lambda s: comp[s])
        ns = max(1, int(round(len(order) * quantile)))
        low, high = order[:ns], order[-ns:]
        longs, shorts = (high, low) if sign > 0 else (low, high)
        for side, names, d in (("L", longs, +1), ("S", shorts, -1)):
            w = 1.0 / len(names)
            for sym in names:
                ep = panel.columns.get_loc(sym)
                e, x = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
                if e > 0 and x > 0:
                    raw.append(EquityTrade(symbol=sym, direction=d, entry_date=t,
                                           exit_date=idx[pos + hold_days].date(),
                                           entry_price=e, exit_price=x, weight=w))
    return raw


def make_rollup(parts, sign):
    async def _gen(universe, start, end, **kw):
        return await _rollup_generate(universe, start, end, parts=parts, sign=sign, **kw)
    return _gen


# rollup definitions
def generate_trend_trades(u, s, e, **kw):
    return make_rollup(["ema_align", "slope", "adx_dir"], +1)(u, s, e, **kw)


def generate_risk_trades(u, s, e, **kw):
    return make_rollup(["bb_width", "atr_pct", "rvol"], -1)(u, s, e, **kw)
