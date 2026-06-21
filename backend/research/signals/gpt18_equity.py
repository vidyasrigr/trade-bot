"""
GPT-18 equity/OHLCV signal adapters (0620.2 Phase 2, research namespace, ISOLATED).

Cross-sectional, PIT, same EquityTrade/forward-return contract as the incumbents so the
Phase 3 harness + daily-MTM simulator apply unchanged. De-dup: rvol (low_realized_vol) and
iv_term_slope already NO_EDGE -> not here.

Each scorer takes per-symbol close (and where needed volume + market return), all sliced to
<= t, and returns a scalar at t. `sign=+1` longs HIGH score, `-1` longs LOW. Cautions from the
runbook are implemented inline (PIT rolling betas; liquidity/min-price filters on reversals;
two-condition contraction-then-breakout + volume confirm; inverse-vol scaling for TSMOM;
solvency proxy for long-term reversal).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade
from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions

MIN_PRICE = 5.0          # liquidity/junk filter for reversals (they hide in penny names)


def _beta(r_i: pd.Series, r_m: pd.Series) -> float | None:
    df = pd.concat([r_i, r_m], axis=1).dropna()
    if len(df) < 60:
        return None
    v = df.iloc[:, 1].var()
    return float(df.iloc[:, 0].cov(df.iloc[:, 1]) / v) if v > 0 else None


# --- scorers: (close, vol, mkt) sliced <= t -> scalar | None -------------------

def _residual_momentum(close, vol, mkt):
    if len(close) < 260 or close.iloc[-1] < MIN_PRICE:
        return None
    r = close.pct_change().dropna()
    rm = mkt.reindex(r.index).dropna()
    r = r.reindex(rm.index)
    b = _beta(r.iloc[-252:], rm.iloc[-252:])
    if b is None:
        return None
    resid = (r - b * rm).iloc[-252:-21]          # skip last month
    return float(resid.sum())


def _high_52w_proximity(close, vol, mkt):
    if len(close) < 252 or close.iloc[-1] < MIN_PRICE:
        return None
    hi = close.iloc[-252:].max()
    return float(close.iloc[-1] / hi) if hi > 0 else None


def _ts_momentum(close, vol, mkt):
    if len(close) < 260:
        return None
    ret = close.iloc[-1] / close.iloc[-252] - 1.0
    vol21 = close.pct_change().iloc[-21:].std()
    if not vol21 or np.isnan(vol21) or vol21 == 0:
        return None
    return float(ret / vol21)                      # inverse-vol scaled


def _short_term_reversal(close, vol, mkt):
    if len(close) < 30 or close.iloc[-1] < MIN_PRICE:
        return None
    return float(-(close.iloc[-1] / close.iloc[-21] - 1.0))   # reversal: high score = recent loser


def _long_term_reversal(close, vol, mkt):
    if len(close) < 760 or close.iloc[-1] < MIN_PRICE:
        return None
    # solvency proxy: still trading + price not collapsed >95% from its own 3y high
    if close.iloc[-1] < 0.05 * close.iloc[-756:].max():
        return None
    return float(-(close.iloc[-252] / close.iloc[-756] - 1.0))


def _idiosyncratic_vol(close, vol, mkt):
    if len(close) < 200:
        return None
    r = close.pct_change().dropna()
    rm = mkt.reindex(r.index).dropna()
    r = r.reindex(rm.index)
    b = _beta(r.iloc[-126:], rm.iloc[-126:])
    if b is None:
        return None
    resid = (r - b * rm).iloc[-126:]
    return float(-resid.std())                     # low idio-vol anomaly: high score = low vol


def _max_lottery_avoid(close, vol, mkt):
    if len(close) < 30 or close.iloc[-1] < MIN_PRICE:
        return None
    return float(-close.pct_change().iloc[-21:].max())   # avoid high-MAX: high score = low max


def _vol_contraction_breakout(close, vol, mkt):
    if len(close) < 80:
        return None
    r = close.pct_change()
    v_now = r.iloc[-10:].std()
    v_prev = r.iloc[-60:-10].std()
    if not v_prev or v_prev == 0:
        return None
    contracted = v_now < 0.7 * v_prev               # condition 1: vol contraction
    breakout = close.iloc[-1] >= close.iloc[-60:-1].max()  # condition 2: price breakout
    vol_confirm = (vol is not None and len(vol) >= 21
                   and vol.iloc[-1] > 1.3 * vol.iloc[-21:].mean())
    return 1.0 if (contracted and breakout and vol_confirm) else 0.0


def _betting_against_beta(close, vol, mkt):
    if len(close) < 260:
        return None
    r = close.pct_change().dropna()
    rm = mkt.reindex(r.index).dropna()
    r = r.reindex(rm.index)
    b = _beta(r.iloc[-252:], rm.iloc[-252:])
    return float(-b) if b is not None else None     # long low beta: high score = low beta


def _volume_confirmed_momentum(close, vol, mkt):
    if len(close) < 150 or vol is None or len(vol) < 60 or close.iloc[-1] < MIN_PRICE:
        return None
    mom = close.iloc[-21] / close.iloc[-126] - 1.0  # 6-1 momentum (skip last month)
    vconf = vol.iloc[-21:].mean() / vol.iloc[-126:-21].mean() if vol.iloc[-126:-21].mean() else 1.0
    return float(mom * max(vconf, 0.0))             # momentum scaled by rising volume


SCORERS = {
    "residual_momentum": (_residual_momentum, +1, True),
    "high_52w_proximity": (_high_52w_proximity, +1, False),
    "time_series_momentum": (_ts_momentum, +1, True),
    "short_term_reversal": (_short_term_reversal, +1, False),
    "long_term_reversal": (_long_term_reversal, +1, False),
    "idiosyncratic_vol": (_idiosyncratic_vol, +1, True),
    "max_lottery_avoid": (_max_lottery_avoid, +1, False),
    "vol_contraction_breakout": (_vol_contraction_breakout, +1, False),
    "betting_against_beta": (_betting_against_beta, +1, True),
    "volume_confirmed_momentum": (_volume_confirmed_momentum, +1, True),
}


def _vol_panel(universe):
    """Volume panel from the equity cache (for volume-confirm scorers)."""
    from backtest import equity_cache
    cols = {}
    for s in dict.fromkeys(universe):
        p = equity_cache._path(s)
        if p.exists():
            try:
                df = pd.read_parquet(p)
                cols[s] = pd.Series(df["volume"].values, index=pd.to_datetime(df["date"]))
            except Exception:
                continue
    return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()


async def _generate(universe, start, end, *, scorer, sign, needs_vol=False,
                    rebalance_days=21, hold_days=21, quantile=0.2,
                    panel=None, **_ignored) -> list[EquityTrade]:
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    mkt = panel.pct_change().mean(axis=1)             # equal-weight market proxy
    vol = _vol_panel(panel.columns) if needs_vol else None
    if vol is not None and not vol.empty:
        vol = vol.reindex(idx).ffill(limit=3)
    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        mkt_t = mkt.iloc[:pos + 1]
        scores = {}
        for sym in panel.columns:
            c = panel[sym].iloc[:pos + 1].dropna()
            if len(c) < 60:
                continue
            v = (vol[sym].iloc[:pos + 1].dropna() if (vol is not None and sym in vol) else None)
            try:
                s = scorer(c, v, mkt_t)
            except Exception:
                s = None
            if s is not None and np.isfinite(s):
                scores[sym] = s
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
                                           entry_price=e, exit_price=x, weight=w))
    return raw


def make_generator(name: str):
    scorer, sign, needs_vol = SCORERS[name]

    async def _gen(universe, start, end, **kw):
        kw.pop("lookback_days", None)
        return await _generate(universe, start, end, scorer=scorer, sign=sign,
                               needs_vol=needs_vol, **kw)
    _gen.__name__ = f"generate_{name}_trades"
    return _gen
