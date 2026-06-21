"""
No-look-ahead guard for the causal regime classifier (0620.2 Phase 1.2).

The whole regime program is p-hacking if a past day's regime label can change once
future data arrives. These tests fail if that ever happens — i.e. if someone refits
the model on full data or uses smoothing that peeks ahead.

Uses a synthetic fingerprint so the test is deterministic and needs no banked data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.regime.regime_state import fit_on_train, _FEATURES


def _synthetic_fingerprint(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-01", periods=n)
    # two latent regimes with different feature means so clustering is well-defined
    half = n // 2
    block = np.r_[np.zeros(half), np.ones(n - half)]
    data = {}
    for i, f in enumerate(_FEATURES):
        base = rng.normal(0, 1, n)
        data[f] = base + block * (1.5 + 0.1 * i)
    return pd.DataFrame(data, index=idx)


def test_regime_label_is_causal_under_appended_future():
    """A label for date T must not change when future rows are appended."""
    feat = _synthetic_fingerprint()
    train_end = feat.index[400]

    model = fit_on_train(feat, train_end=train_end, k_range=range(2, 4))

    full = model.assign(feat)
    # truncate to a date inside the WF region and re-assign
    cutoff = feat.index[600]
    truncated = model.assign(feat[feat.index <= cutoff])

    common = full.index.intersection(truncated.index)
    assert len(common) > 100
    # the SAME train-fit model must give identical labels for the shared dates
    assert (full.loc[common, "regime_state"].values
            == truncated.loc[common, "regime_state"].values).all()


def test_fit_uses_train_only():
    """Fitting must ignore post-train rows: a fit on train == fit on train+future."""
    feat = _synthetic_fingerprint()
    train_end = feat.index[400]

    m1 = fit_on_train(feat, train_end=train_end, k_range=range(2, 4))
    # append wildly different future rows; fit_on_train must produce the same model
    future = feat.copy()
    future.loc[future.index > train_end] = future.loc[future.index > train_end] * 10 + 50
    m2 = fit_on_train(future, train_end=train_end, k_range=range(2, 4))

    # identical scaler params (means/scales) prove future rows did not enter the fit
    assert np.allclose(m1.scaler.mean_, m2.scaler.mean_)
    assert np.allclose(m1.scaler.scale_, m2.scaler.scale_)
    assert m1.k == m2.k
