"""
Macro regime classifier (NEXT_RUNBOOK Phase 2).

Deterministic, point-in-time regime tags from the banked FRED series
(analysis/macro_ingest). Two dimensions, research-aligned:
  - vol_regime  : VIX level (low_vol < 15, high_vol >= 25, else normal_vol)
  - market_regime: risk-on/off from VIX + HY credit OAS + yield-curve slope
                   (crisis/bear when VIX>=30 OR HY OAS>=5% OR curve inverted)

classify(as_of) reads each series AS OF that date (last obs <= as_of), so it is
correct for both live tagging and historical replay. No network — reads parquet.
"""

from __future__ import annotations

from datetime import date

from analysis.macro_ingest import load_series


def _asof(series_id: str, as_of: date) -> float | None:
    s = load_series(series_id)
    if s.empty:
        return None
    import pandas as pd
    s = s[s.index <= pd.Timestamp(as_of)]
    return float(s.iloc[-1]) if len(s) else None


def classify(as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    vix = _asof("VIXCLS", as_of)
    hy_oas = _asof("BAMLH0A0HYM2", as_of)
    curve = _asof("T10Y2Y", as_of)

    if vix is None:
        return {"as_of": as_of.isoformat(), "vol_regime": "unknown",
                "market_regime": "unknown", "vix": None}

    if vix >= 25:
        vol_regime = "high_vol"
    elif vix < 15:
        vol_regime = "low_vol"
    else:
        vol_regime = "normal_vol"

    if vix >= 30 or (hy_oas is not None and hy_oas >= 5.0):
        market_regime = "bear"            # crisis / risk-off
    elif curve is not None and curve < 0:
        market_regime = "bear"            # inverted curve — late-cycle/risk-off
    elif vix < 18:
        market_regime = "bull"            # calm — risk-on
    else:
        market_regime = "range"

    return {
        "as_of": as_of.isoformat(),
        "vol_regime": vol_regime,
        "market_regime": market_regime,
        "vix": round(vix, 2),
        "hy_credit_oas": round(hy_oas, 2) if hy_oas is not None else None,
        "yield_curve_10y2y": round(curve, 2) if curve is not None else None,
    }


def regime_tag(as_of: date | None = None) -> str:
    """Compact 'vol|market' tag for the recommendations.market_regime column."""
    r = classify(as_of)
    return f"{r['vol_regime']}|{r['market_regime']}"
