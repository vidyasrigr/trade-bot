"""
Regime fingerprint (0620.2 Phase 1.1) — Layer 1, theme-agnostic per-day structural features.

Computed from the cached equity panel (close + volume) over 2021-2026, plus FRED VIX.
Every feature at date T uses ONLY data <= T (causal; the regime model that consumes this
must stay causal too). Persisted to data/feature_store/regime/fingerprint.parquet.

NOTE (survivorship): built on today's listed names (the equity cache). The regime LABELS
are therefore survivorship-biased and get REBUILT on the PIT universe in Session 3
(GPT amendment E). Value/quality factor leadership is data-gated (fundamentals still
banking) -> only price-based factors (momentum, low-vol) are computed here.

Features per day:
  breadth_above_200dma, advance_decline, new_high_low_net,
  concentration_top10_share, dispersion_xs, realized_vol_xs, vix, vix_term,
  factor_mom_rs, factor_lowvol_rs, avg_pairwise_corr
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

OUT_DIR = Path(__file__).resolve().parents[2].parent / "data" / "feature_store" / "regime"
OUT_FILE = OUT_DIR / "fingerprint.parquet"


def _panels(min_len: int = 260):
    """Close + volume panels (dates x symbols) from the equity cache."""
    from backtest import equity_cache
    closes, vols = {}, {}
    for p in equity_cache.EQUITY_DIR.glob("*.parquet"):
        try:
            df = pd.read_parquet(p)
            if len(df) < min_len:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            closes[p.stem] = df["close"]
            if "volume" in df:
                vols[p.stem] = df["volume"]
        except Exception:
            continue
    close = pd.DataFrame(closes).sort_index()
    vol = pd.DataFrame(vols)
    # Reindex onto a common business-day calendar and ffill small gaps. The raw union
    # index interleaves slightly-different per-symbol calendars, so every column carries
    # scattered NaNs that break rolling windows (all-NaN rolling features). A clean
    # bday grid + short ffill makes rolling contiguous without inventing real history.
    if not close.empty:
        cal = pd.bdate_range(close.index.min(), close.index.max())
        close = close.reindex(cal).ffill(limit=3)
        vol = vol.reindex(cal).ffill(limit=3)
    return close, vol


def _factor_leadership(rets: pd.DataFrame, signal: pd.DataFrame, q: float = 0.2) -> pd.Series:
    """Daily long-short factor return: long top-q by `signal`, short bottom-q. signal is
    PIT (already shifted). Returned series is the factor's daily return."""
    out = pd.Series(index=rets.index, dtype=float)
    for t in rets.index:
        s = signal.loc[t].dropna()
        r = rets.loc[t]
        common = s.index.intersection(r.dropna().index)
        if len(common) < 20:
            continue
        s = s[common]
        ns = max(1, int(len(s) * q))
        order = s.sort_values()
        lo, hi = order.index[:ns], order.index[-ns:]
        out[t] = r[hi].mean() - r[lo].mean()
    return out


def compute(as_of_min: str = "2021-01-01") -> pd.DataFrame:
    close, vol = _panels()
    if close.empty:
        raise SystemExit("fingerprint: empty equity panel — backfill first")
    close = close[close.index >= pd.Timestamp(as_of_min) - pd.Timedelta(days=400)]
    rets = close.pct_change()
    n = close.shape[1]

    feat = pd.DataFrame(index=close.index)

    # breadth
    ma200 = close.rolling(200, min_periods=120).mean()
    feat["breadth_above_200dma"] = (close > ma200).sum(axis=1) / close.notna().sum(axis=1)
    adv = (rets > 0).sum(axis=1)
    dec = (rets < 0).sum(axis=1)
    feat["advance_decline"] = (adv - dec) / (adv + dec).replace(0, np.nan)
    hi252 = close.rolling(252, min_periods=120).max()
    lo252 = close.rolling(252, min_periods=120).min()
    feat["new_high_low_net"] = ((close >= hi252).sum(axis=1) - (close <= lo252).sum(axis=1)) / n

    # concentration: top-10 share of total positive daily return (computed fresh)
    def _top10_share(row):
        pos = row[row > 0]
        if pos.sum() <= 0 or len(pos) < 10:
            return np.nan
        return float(pos.nlargest(10).sum() / pos.sum())
    feat["concentration_top10_share"] = rets.apply(_top10_share, axis=1)

    # cross-sectional dispersion + realized vol
    feat["dispersion_xs"] = rets.std(axis=1)
    feat["realized_vol_xs"] = rets.rolling(21, min_periods=15).std().mean(axis=1) * np.sqrt(252)

    # avg pairwise correlation via the implied-correlation identity (no n^2 matrix):
    # rho ~ (var(eqw_index) - mean_i var_i / N) / (mean_i sigma_i)^2  (rolling 63d)
    eqw = rets.mean(axis=1)
    var_idx = eqw.rolling(63, min_periods=40).var()
    var_i = rets.rolling(63, min_periods=40).var()
    mean_var = var_i.mean(axis=1)
    mean_sig = rets.rolling(63, min_periods=40).std().mean(axis=1)
    denom = (mean_sig ** 2) - mean_var / n
    feat["avg_pairwise_corr"] = ((var_idx - mean_var / n) / denom.replace(0, np.nan)).clip(-1, 1)

    # VIX + term structure (FRED, banked)
    try:
        from analysis.macro_ingest import load_series
        vix = load_series("VIXCLS").reindex(close.index).ffill()
        vix3m = load_series("VXVCLS").reindex(close.index).ffill()
        feat["vix"] = vix
        feat["vix_term"] = (vix3m - vix)            # contango>0 normal, <0 stress
    except Exception as e:
        logger.warning(f"fingerprint VIX load failed: {e}")
        feat["vix"] = np.nan
        feat["vix_term"] = np.nan

    # factor leadership (price-based; value/quality gated on fundamentals). PIT-shifted.
    mom = close.pct_change(126).shift(1)                       # 6m momentum, lagged
    lowvol = (-rets.rolling(21).std()).shift(1)                # low-vol = high score
    feat["factor_mom_rs"] = _factor_leadership(rets, mom).rolling(63, min_periods=40).sum()
    feat["factor_lowvol_rs"] = _factor_leadership(rets, lowvol).rolling(63, min_periods=40).sum()

    feat = feat[feat.index >= pd.Timestamp(as_of_min)].dropna(how="all")
    return feat


def build_and_persist(as_of_min: str = "2021-01-01") -> dict:
    feat = compute(as_of_min)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    feat.reset_index().rename(columns={"index": "date"}).to_parquet(OUT_FILE, index=False)
    return {"rows": len(feat), "features": list(feat.columns),
            "range": (str(feat.index.min().date()), str(feat.index.max().date()))}


def load() -> pd.DataFrame:
    if not OUT_FILE.exists():
        return pd.DataFrame()
    df = pd.read_parquet(OUT_FILE)
    return df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])


if __name__ == "__main__":
    print(build_and_persist())
