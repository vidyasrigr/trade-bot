"""
Causal regime-state assignment (0620.2 Phase 1.2).

Clusters the regime fingerprint into unnamed states. CAUSAL BY CONSTRUCTION:
  - StandardScaler + GaussianMixture are fit on the TRAIN window ONLY.
  - k chosen by BIC on TRAIN only.
  - regime_state for date T = predict(scaler.transform(features[T])) — depends only on
    date T's (already-causal) features + the train-fit model. Appending future rows
    cannot change a past label (this is what tests/test_regime_causal.py asserts).
  - No Viterbi smoothing (that would peek at the future). No fitting on full 2021-2026.
  - States are NUMBERED, never named. Any AI/GLP-1/etc. label is post-hoc human annotation.

Allowed-regime selection for a signal (Phase 3) must use TRAIN only and validate on WF —
this module just produces the labels; it never sees returns.

Persists data/feature_store/regime/regime_state.parquet (date, regime_state, prob_*).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from research.regime import fingerprint

TRAIN_END = pd.Timestamp("2024-12-31")
OUT_FILE = fingerprint.OUT_DIR / "regime_state.parquet"
_FEATURES = ["breadth_above_200dma", "advance_decline", "new_high_low_net",
             "concentration_top10_share", "dispersion_xs", "realized_vol_xs",
             "avg_pairwise_corr", "vix", "vix_term", "factor_mom_rs", "factor_lowvol_rs"]


@dataclass
class RegimeModel:
    scaler: StandardScaler
    gmm: GaussianMixture
    features: list
    k: int
    train_end: pd.Timestamp

    def assign(self, feat: pd.DataFrame) -> pd.DataFrame:
        """Per-row causal assignment: each date's label uses only that date's features."""
        X = feat[self.features].copy()
        X = X.ffill().dropna()
        Z = self.scaler.transform(X.values)
        states = self.gmm.predict(Z)
        probs = self.gmm.predict_proba(Z)
        out = pd.DataFrame({"regime_state": states}, index=X.index)
        for j in range(self.k):
            out[f"prob_{j}"] = probs[:, j]
        return out


def fit_on_train(feat: pd.DataFrame, train_end: pd.Timestamp = TRAIN_END,
                 k_range=range(2, 7)) -> RegimeModel:
    """Fit scaler + GMM on TRAIN ONLY; pick k by BIC on train."""
    tr = feat[feat.index <= train_end][_FEATURES].ffill().dropna()
    if len(tr) < 100:
        raise SystemExit("regime_state: too few train rows")
    scaler = StandardScaler().fit(tr.values)
    Z = scaler.transform(tr.values)
    best, best_bic = None, np.inf
    for k in k_range:
        gmm = GaussianMixture(n_components=k, covariance_type="full",
                              random_state=42, n_init=4, max_iter=300).fit(Z)
        bic = gmm.bic(Z)
        if bic < best_bic:
            best, best_bic, best_k = gmm, bic, k
    logger.info(f"regime_state: chose k={best_k} (BIC={best_bic:.0f}) on {len(tr)} train days")
    return RegimeModel(scaler=scaler, gmm=best, features=_FEATURES, k=best_k, train_end=train_end)


def build_and_persist(train_end: pd.Timestamp = TRAIN_END) -> dict:
    feat = fingerprint.load()
    if feat.empty:
        feat = fingerprint.compute()
    model = fit_on_train(feat, train_end)
    labels = model.assign(feat)
    fingerprint.OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels.reset_index().rename(columns={"index": "date"}).to_parquet(OUT_FILE, index=False)
    # post-hoc descriptive summary (NUMBERED states; human reads centroids later)
    summ = {}
    for s in sorted(labels["regime_state"].unique()):
        days = labels[labels.regime_state == s]
        f = feat.loc[days.index]
        summ[int(s)] = {"n_days": int(len(days)),
                        "vix": round(float(f["vix"].mean()), 1),
                        "breadth": round(float(f["breadth_above_200dma"].mean()), 2),
                        "corr": round(float(f["avg_pairwise_corr"].mean()), 2)}
    return {"rows": len(labels), "k": model.k,
            "train_days": int((feat.index <= train_end).sum()),
            "wf_days": int((feat.index > train_end).sum()), "state_summary": summ}


def load() -> pd.DataFrame:
    if not OUT_FILE.exists():
        return pd.DataFrame()
    df = pd.read_parquet(OUT_FILE)
    return df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])


if __name__ == "__main__":
    import json
    print(json.dumps(build_and_persist(), indent=2, default=str))
