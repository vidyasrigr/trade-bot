"""
Cross-sectional options-implied signal generators (0619.3 Track A2).

All read BS-inverted IV (backtest/iv_inversion) from cached chains — free, no greeks
needed. Same point-in-time + forward-return contract as skew_xs: at rebalance t use the
latest cached chain with as_of <= t (within tol) and DTE in window; hold t -> t+hold.

Signals + standard academic framing (documented per runbook authority):
  - vrp_z         : VRP = ATM_IV - realized_vol(21d). High VRP -> LOWER future returns
                    (vol risk premium / vol anomaly; An-Ang-Bali-Cakici 2014, Bali-Hovakimian).
                    z-scored cross-sectionally. SHORT high-VRP, LONG low-VRP.
  - vrp_level     : same metric, ranked on raw level (no z-score).
  - iv_call_put_spread : ATM call_IV - put_IV (Cremers-Weinbaum 2010). Positive predicts
                    HIGHER returns (~50bp/wk). LONG high spread, SHORT low.
  - iv_term_slope : far_ATM_IV - near_ATM_IV (Vasquez 2015). Contango (far>near) predicts
                    HIGHER returns. LONG high slope, SHORT low. Needs >=2 expiries per as_of.

Each generator is a thin wrapper over _xs_generate with a per-(symbol,date) metric fn
and a sign (+1 = long high metric, -1 = long low metric).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from loguru import logger

from backtest.equity_engine import EquityTrade
from backtest.iv_inversion import enrich_chain_iv
from backtest.strategies.skew_xs import _chain_index


def _atm_ivs(df: pd.DataFrame) -> tuple[float | None, float | None]:
    """(call_atm_iv, put_atm_iv) at the strike nearest spot."""
    ok = df.dropna(subset=["iv"])
    if ok.empty or "underlying_price" not in ok or ok.underlying_price.iloc[0] <= 0:
        return None, None
    spot = float(ok.underlying_price.iloc[0])
    out = {}
    for typ in ("C", "P"):
        side = ok[ok.option_type == typ]
        if side.empty:
            out[typ] = None
            continue
        row = side.iloc[(side.strike - spot).abs().argsort()[:1]]
        iv = float(row.iv.iloc[0])
        out[typ] = iv if iv > 0 else None
    return out.get("C"), out.get("P")


def _atm_iv(df: pd.DataFrame) -> float | None:
    c, p = _atm_ivs(df)
    vals = [v for v in (c, p) if v]
    return float(np.mean(vals)) if vals else None


def _realized_vol(sym: str, t: date, window: int = 21) -> float | None:
    """Annualized trailing realized vol from the equity cache (PIT: prices <= t)."""
    from backtest import equity_cache
    s = equity_cache.load_close(sym)
    if s is None or s.empty:
        return None
    s = s[s.index <= pd.Timestamp(t)]
    if len(s) < window + 1:
        return None
    rets = np.log(s.iloc[-(window + 1):]).diff().dropna()
    if rets.empty:
        return None
    return float(rets.std() * np.sqrt(252))


# --- per-(symbol, date) metric functions: return float | None ----------------

def _m_vrp(sym, t, df, near_df=None, far_df=None):
    iv = _atm_iv(df)
    rv = _realized_vol(sym, t)
    if iv is None or rv is None:
        return None
    return iv - rv


def _m_cp_spread(sym, t, df, near_df=None, far_df=None):
    c, p = _atm_ivs(df)
    if c is None or p is None:
        return None
    return c - p


def _m_term_slope(sym, t, df, near_df=None, far_df=None):
    if near_df is None or far_df is None:
        return None
    niv, fiv = _atm_iv(near_df), _atm_iv(far_df)
    if niv is None or fiv is None:
        return None
    return fiv - niv


async def _xs_generate(
    universe: list[str], start: date, end: date, *,
    metric, sign: int, zscore: bool = False, needs_term: bool = False,
    rebalance_days: int = 21, hold_days: int = 21, quantile: float = 0.3,
    min_dte: int = 25, max_dte: int = 55, chain_tol_days: int = 10,
    near_dte: tuple[int, int] = (20, 40), far_dte: tuple[int, int] = (50, 80),
    panel: pd.DataFrame | None = None, **_ignored,
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
        logger.warning(f"options_xs: only {len(indexes)} names have chains — too few")
        return []

    def chain_for(sym, t, lo, hi):
        best = None
        for asof, exp, path in indexes.get(sym, []):
            if asof > t or (t - asof).days > chain_tol_days:
                continue
            if not (lo <= (exp - asof).days <= hi):
                continue
            best = (asof, exp, path)
        return best

    def load(cf):
        asof, exp, path = cf
        try:
            return enrich_chain_iv(pd.read_parquet(path), asof, exp)
        except Exception:
            return None

    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        metrics: dict[str, float] = {}
        for sym in indexes:
            cf = chain_for(sym, t, min_dte, max_dte)
            if cf is None:
                continue
            df = load(cf)
            if df is None:
                continue
            near_df = far_df = None
            if needs_term:
                ncf, fcf = chain_for(sym, t, *near_dte), chain_for(sym, t, *far_dte)
                if ncf is None or fcf is None or ncf[1] == fcf[1]:
                    continue
                near_df, far_df = load(ncf), load(fcf)
            m = metric(sym, t, df, near_df, far_df)
            if m is not None and np.isfinite(m):
                metrics[sym] = m
        if len(metrics) < 6:
            continue
        vals = metrics
        if zscore:
            arr = np.array(list(metrics.values()))
            mu, sd = arr.mean(), arr.std()
            if sd > 0:
                vals = {k: (v - mu) / sd for k, v in metrics.items()}
        order = sorted(vals, key=lambda s: vals[s])   # ascending
        n_side = max(1, int(round(len(order) * quantile)))
        low, high = order[:n_side], order[-n_side:]
        # sign=+1 -> long HIGH metric; sign=-1 -> long LOW metric
        longs, shorts = (high, low) if sign > 0 else (low, high)
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
                        signal=f"{side}_{vals[sym]:+.3f}",
                    ))
    return raw


# --- public generators -------------------------------------------------------

async def generate_vrp_z_trades(universe, start, end, **kw):
    return await _xs_generate(universe, start, end, metric=_m_vrp, sign=-1, zscore=True, **kw)


async def generate_vrp_level_trades(universe, start, end, **kw):
    return await _xs_generate(universe, start, end, metric=_m_vrp, sign=-1, zscore=False, **kw)


async def generate_iv_cp_spread_trades(universe, start, end, **kw):
    return await _xs_generate(universe, start, end, metric=_m_cp_spread, sign=+1, **kw)


async def generate_iv_term_slope_trades(universe, start, end, **kw):
    return await _xs_generate(universe, start, end, metric=_m_term_slope, sign=+1,
                              needs_term=True, **kw)


def _m_rv_minus_iv(sym, t, df, near_df=None, far_df=None):
    """Goyal-Saretto 2009: realized vol minus ATM implied vol. High (cheap implied) ->
    options/underlying outperform. CACHE_LIMITED. (= -VRP.)"""
    iv = _atm_iv(df)
    rv = _realized_vol(sym, t)
    if iv is None or rv is None:
        return None
    return rv - iv


async def generate_rv_minus_iv_trades(universe, start, end, **kw):
    return await _xs_generate(universe, start, end, metric=_m_rv_minus_iv, sign=+1, **kw)
