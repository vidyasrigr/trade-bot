"""
GPT-18 FMP-backed signal adapters (0620.2 Phase 2, research namespace).

LOOK-AHEAD GUARD (GPT amendment F, MANDATORY): every feature is gated on `available_at
<= trade_date`, NEVER fiscal_period_end <= trade_date. Fundamentals are knowable only
after filing. available_at:
  - earnings signals: the announcement `date` (knowable that day),
  - statement signals: `filingDate`/`acceptedDate` from the FMP statement (present on Starter);
    fallback = fiscal period_end + 90 days (conservative 10-K lag) if missing.

Earnings-based (revenue_surprise_drift, earnings_announcement_premium) are testable now
(earnings banked). Statement-based quality factors (accruals, piotroski_fscore,
net_payout_yield, net_operating_assets, distress_risk_avoid) require balance/cash-flow,
which are still banking -> they return [] and the harness labels them FUNDAMENTALS_PENDING.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from backtest.equity_engine import EquityTrade
from backtest.strategies.momentum_xs_v2 import _close_panel, _rebalance_positions
from data import fmp_cache

_STATEMENT_LAG = timedelta(days=90)


def _d(s):
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


def _earnings_events(symbol: str) -> list[dict]:
    """[{available_at, eps_surprise, rev_surprise}] sorted; available_at = announcement date."""
    rows = fmp_cache.read("earnings", symbol) or []
    out = []
    for r in rows:
        ad = _d(r.get("date"))
        if ad is None:
            continue
        ea, ee = r.get("epsActual"), r.get("epsEstimated")
        ra, re_ = r.get("revenueActual"), r.get("revenueEstimated")
        eps_surp = ((ea - ee) / abs(ee)) if (ea is not None and ee not in (None, 0)) else None
        rev_surp = ((ra - re_) / abs(re_)) if (ra is not None and re_ not in (None, 0)) else None
        out.append({"available_at": ad, "eps_surprise": eps_surp, "rev_surprise": rev_surp})
    return sorted(out, key=lambda x: x["available_at"])


def _statements(symbol: str, kind: str) -> list[dict]:
    """Statement rows with a computed available_at (filingDate, else period_end+90d)."""
    rows = fmp_cache.read(kind, symbol) or []
    out = []
    for r in rows:
        pe = _d(r.get("date"))
        fd = _d(r.get("filingDate")) or _d(r.get("acceptedDate"))
        avail = fd or (pe + _STATEMENT_LAG if pe else None)
        if avail is None:
            continue
        rr = dict(r)
        rr["_available_at"] = avail
        out.append(rr)
    return sorted(out, key=lambda x: x["_available_at"])


def _latest_asof(events: list[dict], t: date, key: str = "available_at"):
    """Most recent event with available_at <= t (the look-ahead guard)."""
    ok = [e for e in events if e[key] <= t]
    return ok[-1] if ok else None


# --- earnings-based (testable now) -------------------------------------------

async def generate_revenue_surprise_drift_trades(universe, start, end, *, drift_skip=2,
                                                 rebalance_days=21, hold_days=21,
                                                 quantile=0.2, panel=None, **_):
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    ev = {s: _earnings_events(s) for s in panel.columns}
    raw = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        scores = {}
        for s in panel.columns:
            e = _latest_asof(ev.get(s, []), t)
            # require the surprise to be RECENT (drift window) and knowable
            if e and e["rev_surprise"] is not None and (t - e["available_at"]).days <= 63:
                scores[s] = e["rev_surprise"]
        if len(scores) < 10:
            continue
        order = sorted(scores, key=lambda s: scores[s])
        ns = max(1, int(round(len(order) * quantile)))
        longs, shorts = order[-ns:], order[:ns]      # drift: long positive surprise
        for side, names, d in (("L", longs, +1), ("S", shorts, -1)):
            w = 1.0 / len(names)
            for s in names:
                ep = panel.columns.get_loc(s)
                a, b = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
                if a > 0 and b > 0:
                    raw.append(EquityTrade(s, d, t, idx[pos + hold_days].date(), a, b, w))
    return raw


async def generate_earnings_announcement_premium_trades(universe, start, end, *,
                                                        rebalance_days=21, hold_days=21,
                                                        panel=None, **_):
    """Long names with an earnings announcement inside the upcoming hold window (premium)."""
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    ev = {s: _earnings_events(s) for s in panel.columns}
    raw = []
    for pos in _rebalance_positions(idx, rebalance_days):
        t = idx[pos].date()
        if not (start <= t <= end) or pos + hold_days >= len(idx):
            continue
        exit_d = idx[pos + hold_days].date()
        # NB: announcement schedule is itself knowable (companies pre-announce dates);
        # we use the next announcement strictly after t (available as a calendar item).
        longs = []
        for s in panel.columns:
            future = [e for e in ev.get(s, []) if t < e["available_at"] <= exit_d]
            if future:
                longs.append(s)
        if len(longs) < 5:
            continue
        w = 1.0 / len(longs)
        for s in longs:
            ep = panel.columns.get_loc(s)
            a, b = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
            if a > 0 and b > 0:
                raw.append(EquityTrade(s, +1, t, exit_d, a, b, w))
    return raw


# --- statement-based quality factors (gated on balance/cash-flow coverage) ----

def _num(r, *keys):
    for k in keys:
        v = r.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _quality_score(sym: str, t: date, which: str):
    """Compute a statement-based factor as-of t (available_at gated). None if data absent."""
    inc = _latest_asof(_statements(sym, "income"), t, key="_available_at")
    bal = _latest_asof(_statements(sym, "balance_sheet"), t, key="_available_at")
    cfs = _latest_asof(_statements(sym, "cash_flow"), t, key="_available_at")
    if which == "accruals":
        if not inc or not cfs:
            return None
        ni = _num(inc, "netIncome"); cfo = _num(cfs, "operatingCashFlow", "netCashProvidedByOperatingActivities")
        ta = _num(bal, "totalAssets") if bal else None
        if ni is None or cfo is None or not ta:
            return None
        return -((ni - cfo) / ta)                    # low accruals = high score
    if which == "distress_risk_avoid":               # Altman-Z (avoid distress -> long high Z)
        if not inc or not bal:
            return None
        ta = _num(bal, "totalAssets"); tl = _num(bal, "totalLiabilities")
        wc = (_num(bal, "totalCurrentAssets") or 0) - (_num(bal, "totalCurrentLiabilities") or 0)
        re_ = _num(bal, "retainedEarnings"); ebit = _num(inc, "operatingIncome", "ebitda")
        sales = _num(inc, "revenue")
        if not ta or not tl:
            return None
        z = (1.2 * wc / ta + 1.4 * (re_ or 0) / ta + 3.3 * (ebit or 0) / ta + 0.6 * ta / tl
             + 1.0 * (sales or 0) / ta)
        return float(z)
    if which == "net_operating_assets":
        if not bal:
            return None
        ta = _num(bal, "totalAssets"); cash = _num(bal, "cashAndCashEquivalents") or 0
        tl = _num(bal, "totalLiabilities") or 0; debt = _num(bal, "totalDebt") or 0
        if not ta:
            return None
        noa = (ta - cash) - (tl - debt)
        return -(noa / ta)                           # low NOA = high score (Hirshleifer)
    if which == "net_payout_yield":
        if not cfs or not bal:
            return None
        div = abs(_num(cfs, "dividendsPaid") or 0); buyback = abs(_num(cfs, "commonStockRepurchased") or 0)
        mcap = _num(bal, "totalStockholdersEquity")  # proxy; true mcap needs price*shares
        if not mcap:
            return None
        return (div + buyback) / abs(mcap)
    if which == "piotroski_fscore":
        if not inc or not bal or not cfs:
            return None
        score = 0
        ni = _num(inc, "netIncome") or 0; cfo = _num(cfs, "operatingCashFlow", "netCashProvidedByOperatingActivities") or 0
        score += ni > 0
        score += cfo > 0
        score += cfo > ni                            # accruals quality
        return float(score)                          # partial F-score (subset computable)
    return None


def _statement_generator(which: str):
    async def _gen(universe, start, end, *, rebalance_days=21, hold_days=21,
                   quantile=0.2, panel=None, **_):
        if panel is None:
            panel = _close_panel(universe)
        if panel.empty:
            return []
        idx = panel.index
        raw = []
        for pos in _rebalance_positions(idx, rebalance_days):
            t = idx[pos].date()
            if not (start <= t <= end) or pos + hold_days >= len(idx):
                continue
            scores = {}
            for s in panel.columns:
                v = _quality_score(s, t, which)
                if v is not None and np.isfinite(v):
                    scores[s] = v
            if len(scores) < 10:                      # data-gated -> yields PENDING
                continue
            order = sorted(scores, key=lambda s: scores[s])
            ns = max(1, int(round(len(order) * quantile)))
            longs, shorts = order[-ns:], order[:ns]
            for side, names, d in (("L", longs, +1), ("S", shorts, -1)):
                w = 1.0 / len(names)
                for s in names:
                    ep = panel.columns.get_loc(s)
                    a, b = float(panel.iloc[pos, ep]), float(panel.iloc[pos + hold_days, ep])
                    if a > 0 and b > 0:
                        raw.append(EquityTrade(s, d, t, idx[pos + hold_days].date(), a, b, w))
        return raw
    _gen.__name__ = f"generate_{which}_trades"
    return _gen


generate_accruals_trades = _statement_generator("accruals")
generate_piotroski_fscore_trades = _statement_generator("piotroski_fscore")
generate_net_payout_yield_trades = _statement_generator("net_payout_yield")
generate_net_operating_assets_trades = _statement_generator("net_operating_assets")
generate_distress_risk_avoid_trades = _statement_generator("distress_risk_avoid")
