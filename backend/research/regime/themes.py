"""
Theme layer (0620.2 Phase 1.3) — Layer 2, emergent, DIAGNOSTIC ONLY.

Clusters the universe by trailing return co-movement so dominant emergent groups
(AI, GLP-1 incl. its shorts, quantum, energy) surface WITHOUT being named or hardcoded.
Self-updates as leadership rotates. Causal: clusters at date T use returns <= T only.

Three uses — NONE of them a validation gate:
  - emergent_clusters(as_of): {symbol: cluster_id} from trailing co-movement (unnamed).
  - theme_concentration(pnl_by_symbol, clusters): % of winning PnL from a single cluster;
    > THEME_BET_THRESHOLD (0.40) -> THEME_BET flag (a signal's edge is one theme, not breadth).
  - cluster_decay(as_of): leading cluster's relative strength rising vs rolling over -> the
    live flip signal (would have caught AI breaking down in 2025). Feeds the deploy kill-switch.

Theme is a check + kill-signal, never a gate, never named in the model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

OUT_DIR = Path(__file__).resolve().parents[2].parent / "data" / "feature_store" / "regime"
OUT_FILE = OUT_DIR / "themes.parquet"
THEME_BET_THRESHOLD = 0.40


def _close_panel() -> pd.DataFrame:
    from research.regime.fingerprint import _panels
    close, _ = _panels()
    return close


def emergent_clusters(close: pd.DataFrame, as_of: pd.Timestamp,
                      lookback: int = 126, k: int = 8, min_names: int = 40) -> dict[str, int]:
    """Cluster names by their trailing-`lookback` daily-return shape as of `as_of`
    (causal). Returns {symbol: cluster_id}. Clusters are unnamed integers."""
    window = close[close.index <= as_of].tail(lookback)
    rets = window.pct_change().dropna(how="all")
    rets = rets.dropna(axis=1, thresh=int(len(rets) * 0.8))   # names with enough history
    if rets.shape[1] < min_names:
        return {}
    X = StandardScaler().fit_transform(rets.T.fillna(0.0).values)   # one row per symbol
    kk = min(k, max(2, rets.shape[1] // 10))
    km = KMeans(n_clusters=kk, random_state=42, n_init=4).fit(X)
    return dict(zip(rets.columns, km.labels_.astype(int)))


def theme_concentration(pnl_by_symbol: dict[str, float], clusters: dict[str, int]) -> dict:
    """Share of POSITIVE PnL from the single largest emergent cluster. >40% -> THEME_BET."""
    pos = {s: v for s, v in pnl_by_symbol.items() if v and v > 0}
    total = sum(pos.values())
    if total <= 0:
        return {"theme_bet": False, "top_cluster_share": 0.0, "top_cluster": None}
    by_cluster: dict[int, float] = {}
    for s, v in pos.items():
        c = clusters.get(s)
        if c is None:
            continue
        by_cluster[c] = by_cluster.get(c, 0.0) + v
    if not by_cluster:
        return {"theme_bet": False, "top_cluster_share": 0.0, "top_cluster": None}
    top_c = max(by_cluster, key=by_cluster.get)
    share = by_cluster[top_c] / total
    return {"theme_bet": share > THEME_BET_THRESHOLD,
            "top_cluster_share": round(float(share), 3), "top_cluster": int(top_c)}


def build_and_persist(rebalance_days: int = 21, lookback: int = 126) -> dict:
    """Snapshot emergent clusters monthly + track the leading cluster's RS (decay monitor)."""
    close = _close_panel()
    if close.empty:
        raise SystemExit("themes: empty panel — backfill first")
    rets = close.pct_change()
    dates = close.index[lookback::rebalance_days]
    rows = []
    for t in dates:
        clusters = emergent_clusters(close, t, lookback=lookback)
        if not clusters:
            continue
        # leading cluster = highest trailing-lookback mean return (causal)
        win = rets[rets.index <= t].tail(lookback)
        cl_ret: dict[int, list] = {}
        for s, c in clusters.items():
            if s in win:
                cl_ret.setdefault(c, []).append(win[s].mean())
        cl_mean = {c: float(np.nanmean(v)) for c, v in cl_ret.items() if v}
        if not cl_mean:
            continue
        lead = max(cl_mean, key=cl_mean.get)
        rows.append({"date": t, "n_clusters": len(set(clusters.values())),
                     "lead_cluster": int(lead), "lead_cluster_rs": round(cl_mean[lead], 4),
                     "n_names": len(clusters)})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"snapshots": 0}
    # decay monitor: is the leading cluster's RS rising or rolling over?
    df["lead_rs_chg"] = df["lead_cluster_rs"].diff()
    df["decay_flag"] = df["lead_rs_chg"] < 0      # leading theme weakening = flip risk
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)
    return {"snapshots": len(df),
            "range": (str(df.date.min().date()), str(df.date.max().date())),
            "decay_flagged_snapshots": int(df["decay_flag"].sum())}


def load() -> pd.DataFrame:
    if not OUT_FILE.exists():
        return pd.DataFrame()
    return pd.read_parquet(OUT_FILE)


if __name__ == "__main__":
    import json
    print(json.dumps(build_and_persist(), indent=2, default=str))
