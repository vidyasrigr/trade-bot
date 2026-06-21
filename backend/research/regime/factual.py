"""
Factual / oracle regime + trend labels (0621.2 Part A2a) — EX-POST ground truth.

Causality is NOT required here: these are the "what actually happened" labels used to
(a) AUDIT the live GMM classifier (A2b) and (b) provide an ORACLE regime arm for signal
testing (A3) — a diagnostic CEILING (perfect ex-post regime knowledge), never deployable.

Daily 2010-2026 from SPY (cached) + VIX (FRED) + breadth/concentration (fingerprint):
  - spy_drawdown from running peak -> bull / correction(-10%) / bear(-20%)
  - vix + vix_percentile (full-sample, ex-post ok)
  - trend_200dma (SPY above/below)
  - breadth_above_200dma, concentration_top10 (from fingerprint)
  - nber_recession (hardcoded: the only NBER recession in range is COVID 2020-02..2020-04)
  - oracle_regime: discrete {crisis, bear, correction, bull_narrow, bull_broad, chop}
Persisted to data/feature_store/regime/factual.parquet.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[2].parent / "data" / "feature_store" / "regime"
OUT_FILE = OUT_DIR / "factual.parquet"

# NBER-dated US recessions overlapping 2010-2026 (ex-post fact). Only COVID falls in range.
NBER_RECESSIONS = [("2020-02-01", "2020-04-30")]


def compute(start: str = "2010-01-01") -> pd.DataFrame:
    from backtest import equity_cache
    from analysis.macro_ingest import load_series
    from research.regime import fingerprint

    spy = equity_cache.load_close("SPY")
    if spy is None or spy.empty:
        raise SystemExit("factual: SPY not cached")
    spy = spy[spy.index >= pd.Timestamp(start) - pd.Timedelta(days=300)]
    df = pd.DataFrame(index=spy.index)
    df["spy"] = spy
    df["spy_peak"] = spy.cummax()
    df["spy_drawdown"] = spy / df["spy_peak"] - 1.0
    df["ma200"] = spy.rolling(200, min_periods=120).mean()
    df["trend_200dma"] = (spy > df["ma200"]).astype(int)

    vix = load_series("VIXCLS").reindex(df.index).ffill()
    df["vix"] = vix
    df["vix_percentile"] = vix.rank(pct=True)

    # breadth + concentration from the (rebuilt 2010-2026) fingerprint
    fp = fingerprint.load()
    if not fp.empty:
        df["breadth_above_200dma"] = fp["breadth_above_200dma"].reindex(df.index).ffill()
        df["concentration_top10"] = fp["concentration_top10_share"].reindex(df.index).ffill()
    else:
        df["breadth_above_200dma"] = np.nan
        df["concentration_top10"] = np.nan

    # NBER recession flag
    df["nber_recession"] = 0
    for a, b in NBER_RECESSIONS:
        df.loc[(df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b)), "nber_recession"] = 1

    # market_weather (drawdown-based, the headline factual state)
    def _weather(row):
        dd = row["spy_drawdown"]
        if dd <= -0.20:
            return "crisis" if (row["vix"] or 0) >= 35 else "bear"
        if dd <= -0.10:
            return "correction"
        return "bull"
    df["market_weather"] = df.apply(_weather, axis=1)

    # oracle_regime: refine bull into narrow vs broad by breadth/concentration
    br_lo = df["breadth_above_200dma"].quantile(0.40)
    conc_hi = df["concentration_top10"].quantile(0.60)

    def _oracle(row):
        w = row["market_weather"]
        if w in ("crisis", "bear", "correction"):
            return w
        # bull: split by breadth
        b, c = row.get("breadth_above_200dma"), row.get("concentration_top10")
        if b is not None and not np.isnan(b) and b < br_lo and (c is None or np.isnan(c) or c >= conc_hi):
            return "bull_narrow"
        if b is not None and not np.isnan(b) and b >= br_lo:
            return "bull_broad"
        return "chop"
    df["oracle_regime"] = df.apply(_oracle, axis=1)

    df = df[df.index >= pd.Timestamp(start)]
    return df


def build_and_persist(start: str = "2010-01-01") -> dict:
    df = compute(start)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.reset_index().rename(columns={"index": "date"}).to_parquet(OUT_FILE, index=False)
    from collections import Counter
    return {"rows": len(df), "range": (str(df.index.min().date()), str(df.index.max().date())),
            "oracle_regime_dist": dict(Counter(df["oracle_regime"])),
            "weather_dist": dict(Counter(df["market_weather"]))}


def load() -> pd.DataFrame:
    if not OUT_FILE.exists():
        return pd.DataFrame()
    d = pd.read_parquet(OUT_FILE)
    return d.set_index(pd.to_datetime(d["date"])).drop(columns=["date"])


def oracle_series() -> pd.Series:
    d = load()
    return d["oracle_regime"] if not d.empty else pd.Series(dtype=object)


if __name__ == "__main__":
    import json
    print(json.dumps(build_and_persist(), indent=2, default=str))
