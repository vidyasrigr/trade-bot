"""
0621.2 Part B — new EVIDENCED signals (real mechanisms + literature), research namespace.

Each returns a list[EquityTrade] so the existing engine (run_equity_backtest), the true
daily-MTM account simulator (portfolio_mtm), realistic costs, and the regime arms all apply.
These have genuine economic mechanisms — the thing the dead RSI/MACD primitives lacked.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade
from backtest import equity_cache

# ---- liquid ETF set for mean-reversion (deep-cached) -------------------------
ETF_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV", "XLI", "XLY",
                "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH", "IBB", "XBI", "KRE", "XOP",
                "XHB", "ITB", "EEM", "EFA", "HYG", "TLT", "GLD"]


def _rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


async def generate_etf_mean_reversion_trades(
    universe=None, start: date = date(2010, 1, 1), end: date = date(2026, 6, 18), *,
    ibs_thresh: float = 0.20, rsi_n: int = 2, rsi_exit: float = 70.0,
    max_hold: int = 5, trend_filter: bool = True, panel=None, **_ignored,
) -> list[EquityTrade]:
    """Connors-style ETF dip-buy: long when IBS<thresh AND px>200dma; exit on up-close /
    RSI(rsi_n) normalize / max_hold. Long-only, cash when flat. (QuantifiedStrategies/Connors;
    mechanism = paid to provide liquidity into short-term panic in instruments that trend up.)"""
    etfs = universe or ETF_UNIVERSE
    trades: list[EquityTrade] = []
    for sym in etfs:
        df = equity_cache.load_ohlc(sym)
        if df is None or len(df) < 260:
            continue
        df = df[(df.index >= pd.Timestamp(start) - pd.Timedelta(days=300))]
        c, h, l = df["close"], df["high"], df["low"]
        rng = (h - l).replace(0, np.nan)
        ibs = (c - l) / rng
        ma200 = c.rolling(200, min_periods=120).mean()
        rsi = _rsi(c, rsi_n)
        idx = df.index
        i = 0
        n = len(idx)
        while i < n - 1:
            t = idx[i].date()
            if not (start <= t <= end):
                i += 1
                continue
            entry_ok = (ibs.iloc[i] < ibs_thresh) and (not trend_filter or c.iloc[i] > (ma200.iloc[i] or 1e18))
            if not entry_ok or not np.isfinite(ibs.iloc[i]):
                i += 1
                continue
            entry_px = float(c.iloc[i])
            # find exit
            j = i + 1
            while j < n and (j - i) <= max_hold:
                up_close = c.iloc[j] > c.iloc[j - 1]
                rsi_norm = rsi.iloc[j] > rsi_exit
                if up_close or rsi_norm or (j - i) == max_hold:
                    break
                j += 1
            j = min(j, n - 1)
            exit_px = float(c.iloc[j])
            if entry_px > 0 and exit_px > 0:
                trades.append(EquityTrade(symbol=sym, direction=+1, entry_date=t,
                                          exit_date=idx[j].date(), entry_price=entry_px,
                                          exit_price=exit_px, weight=1.0))
            i = j + 1   # no overlap within a symbol
    return trades


# --- sector_relative_strength (industry momentum, Moskowitz-Grinblatt) ----------
_SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Utilities": "XLU", "Basic Materials": "XLB",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}


async def generate_sector_relative_strength_trades(
    universe, start, end, *, lookback=126, skip=21, rebalance_days=21, hold_days=21,
    quantile=0.2, panel=None, **_ignored,
) -> list[EquityTrade]:
    """Long leaders / short laggards by stock return MINUS its sector-ETF return (relative
    strength), not raw momentum. Moskowitz-Grinblatt industry momentum."""
    from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions
    from backtest.liquid_universe import sector_map
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    smap = sector_map()
    etf_close = {e: equity_cache.load_close(e) for e in set(_SECTOR_ETF.values())}
    idx = panel.index
    raw: list[EquityTrade] = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx) or pos - lookback < 0:
            continue
        scores = {}
        for sym in panel.columns:
            etf = _SECTOR_ETF.get(smap.get(sym))
            if etf is None or etf_close.get(etf) is None:
                continue
            c = panel[sym]
            smom = c.iloc[pos - skip] / c.iloc[pos - lookback] - 1.0 if c.iloc[pos - lookback] > 0 else None
            ec = etf_close[etf].reindex(idx)
            try:
                emom = ec.iloc[pos - skip] / ec.iloc[pos - lookback] - 1.0
            except Exception:
                emom = None
            if smom is None or emom is None or not np.isfinite(smom) or not np.isfinite(emom):
                continue
            scores[sym] = smom - emom
        if len(scores) < 20:
            continue
        order = sorted(scores, key=lambda s: scores[s])
        ns = max(1, int(round(len(order) * quantile)))
        longs, shorts = order[-ns:], order[:ns]
        for side, names, d in (("L", longs, +1), ("S", shorts, -1)):
            w = 1.0 / len(names)
            for sym in names:
                ep = panel.columns.get_loc(sym)
                a, b = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
                if a > 0 and b > 0:
                    raw.append(EquityTrade(sym, d, t, idx[pos + hold_days].date(), a, b, w))
    return raw


# --- pairs_statarb (market-neutral; Gatev-Goetzmann) ---------------------------
async def generate_pairs_statarb_trades(
    universe, start, end, *, formation=252, entry_z=2.0, exit_z=0.5, max_hold=42,
    rebalance_days=21, top_pairs=40, panel=None, **_ignored,
) -> list[EquityTrade]:
    """Same-sector cointegration-lite pairs: form on trailing `formation` days, trade the
    spread (long under-/short out-performer) when |z|>entry_z, exit at |z|<exit_z or max_hold.
    Beta-neutral-ish (equal dollar legs). Market-neutral -> should survive regime change."""
    from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions
    from backtest.liquid_universe import sector_map
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    smap = sector_map()
    idx = panel.index
    logp = np.log(panel.clip(lower=1e-6))
    raw: list[EquityTrade] = []
    rebs = _rebalance_positions(idx, rebalance_days)
    for pos in rebs:
        t = idx[pos].date()
        if not (start <= t <= end) or pos - formation < 0 or pos + max_hold >= len(idx):
            continue
        win = logp.iloc[pos - formation:pos]
        cols = [c for c in win.columns if win[c].notna().sum() > formation * 0.9]
        # candidate pairs within sector, ranked by formation-spread stability (low std of z)
        bysec = {}
        for c in cols:
            bysec.setdefault(smap.get(c, "?"), []).append(c)
        pairs = []
        for sec, members in bysec.items():
            if sec == "?" or len(members) < 2:
                continue
            sub = win[members].dropna(axis=1)
            if sub.shape[1] < 2:
                continue
            corr = sub.corr()
            for i in range(len(corr.columns)):
                for j in range(i + 1, len(corr.columns)):
                    a, b = corr.columns[i], corr.columns[j]
                    if corr.iloc[i, j] > 0.8:
                        pairs.append((a, b, corr.iloc[i, j]))
        pairs.sort(key=lambda x: -x[2])
        for a, b, _c in pairs[:top_pairs]:
            spread = win[a] - win[b]
            mu, sd = spread.mean(), spread.std()
            if not sd or sd <= 0:
                continue
            cur = logp[a].iloc[pos] - logp[b].iloc[pos]
            z = (cur - mu) / sd
            if abs(z) < entry_z:
                continue
            # z>0: a rich vs b -> short a, long b. exit at |z|<exit_z or max_hold.
            la, lb = (-1, +1) if z > 0 else (+1, -1)
            # find exit
            ex = pos + max_hold
            for k in range(pos + 1, min(pos + max_hold, len(idx) - 1)):
                ck = logp[a].iloc[k] - logp[b].iloc[k]
                zk = (ck - mu) / sd
                if abs(zk) < exit_z:
                    ex = k
                    break
            for sym, dirn in ((a, la), (b, lb)):
                ep = panel.columns.get_loc(sym)
                e_px, x_px = float(panel.iloc[pos, ep]), float(panel.iloc[ex, ep])
                if e_px > 0 and x_px > 0:
                    raw.append(EquityTrade(sym, dirn, t, idx[ex].date(), e_px, x_px, 0.5))
    return raw
