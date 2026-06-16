"""
LightGBM cross-sectional ranker — Phase E.

Replaces hand-tuned `BASE_WEIGHTS × IC` (scoring/weighted.py) with a model that
learns which feature combinations predict forward returns. Training data is the
point-in-time feature store (Phase B) joined with forward 5d/21d/63d excess
returns from yfinance.

Key discipline:
  - Point-in-time only: every (symbol, date) row reads features `as_of_date <= date`
  - Purged k-fold CV (López de Prado 2018): the embargo between train and test
    folds equals the forward horizon, so labels can't leak across the boundary
  - Multiple-testing penalty: deflated Sharpe (Bailey-Lopez de Prado 2014) of
    the walk-forward predictions, persisted to model_runs (migration 013)
  - Weekly retrain on Sundays; predictions cached for the next scanner cycle

Inference:
  - At scan time, look up the latest model artifact for the requested horizon,
    apply to today's feature row, return a rank percentile that feeds the
    scanner's Stage 3 → 4 cutoff.
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from loguru import logger

MODEL_NAME = "lightgbm_cross_section"
MODELS_DIR = Path(os.environ.get("MODELS_DIR", "data/models"))
DEFAULT_HORIZONS = (5, 21, 63)
MIN_TRAINING_ROWS = 500


# ---------------------------------------------------------------------------
# Label construction
# ---------------------------------------------------------------------------

def _forward_excess_returns(
    prices: pd.DataFrame, horizon: int, benchmark: str = "SPY",
) -> pd.DataFrame:
    """
    Returns a long-frame (date, symbol, fwd_excess_ret).
    fwd_excess_ret = symbol forward log-return − benchmark forward log-return.
    """
    if prices is None or prices.empty or benchmark not in prices.columns:
        return pd.DataFrame()
    log_prices = np.log(prices.replace(0, np.nan))
    fwd = log_prices.shift(-horizon) - log_prices
    excess = fwd.sub(fwd[benchmark], axis=0)
    excess = excess.drop(columns=[benchmark], errors="ignore")
    long = excess.stack().reset_index()
    long.columns = ["as_of_date", "symbol", "fwd_excess_ret"]
    long["as_of_date"] = pd.to_datetime(long["as_of_date"]).dt.date
    return long.dropna()


# ---------------------------------------------------------------------------
# Cross-validation with purge + embargo
# ---------------------------------------------------------------------------

@dataclass
class FoldResult:
    train_size: int
    test_size: int
    test_ic: float
    test_corr_p_value: float


def _purged_kfold_indices(dates: pd.Series, n_splits: int, embargo: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Sort by date, split into n_splits consecutive blocks for test, remove
    `embargo`-day window around the test block from training.
    """
    sorted_idx = dates.sort_values(kind="mergesort").index.to_numpy()
    blocks = np.array_split(sorted_idx, n_splits)
    sorted_dates = dates.loc[sorted_idx].to_numpy()
    sorted_dates_index = dict(zip(sorted_idx, sorted_dates))

    out = []
    for k in range(n_splits):
        test_idx = blocks[k]
        test_dates = pd.to_datetime([sorted_dates_index[i] for i in test_idx])
        if len(test_dates) == 0:
            continue
        test_min = test_dates.min() - pd.Timedelta(days=embargo)
        test_max = test_dates.max() + pd.Timedelta(days=embargo)
        train_idx = [i for i in sorted_idx
                     if i not in set(test_idx)
                     and not (test_min <= pd.Timestamp(sorted_dates_index[i]) <= test_max)]
        out.append((np.asarray(train_idx), test_idx))
    return out


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def _spearman_ic(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    from scipy.stats import spearmanr
    if len(y_true) < 5:
        return 0.0, 1.0
    corr, p = spearmanr(y_true, y_pred)
    if np.isnan(corr):
        return 0.0, 1.0
    return float(corr), float(p)


def train_ranker(
    features_panel: pd.DataFrame,
    labels: pd.DataFrame,
    horizon: int,
    n_splits: int = 5,
) -> dict:
    """
    features_panel: wide with index (as_of_date, symbol), columns = features
    labels: long (as_of_date, symbol, fwd_excess_ret)

    Returns a dict with the trained model, fold-level IC, mean IC, t-stat,
    deflated Sharpe of the prediction series, and feature importances.
    """
    try:
        import lightgbm as lgb
    except ImportError as e:
        raise RuntimeError(
            "LightGBM not installed. Add lightgbm to requirements or pip install lightgbm."
        ) from e

    panel = features_panel.copy()
    if not isinstance(panel.index, pd.MultiIndex):
        panel = panel.set_index(["as_of_date", "symbol"])
    panel = panel.reset_index()
    panel["as_of_date"] = pd.to_datetime(panel["as_of_date"]).dt.date

    labels = labels.copy()
    labels["as_of_date"] = pd.to_datetime(labels["as_of_date"]).dt.date

    merged = panel.merge(labels, on=["as_of_date", "symbol"], how="inner")
    merged = merged.dropna(subset=["fwd_excess_ret"])
    if len(merged) < MIN_TRAINING_ROWS:
        raise RuntimeError(
            f"train_ranker: {len(merged)} samples < {MIN_TRAINING_ROWS} required"
        )

    feature_cols = [c for c in merged.columns
                    if c not in {"as_of_date", "symbol", "fwd_excess_ret"}]
    X = merged[feature_cols].fillna(0.0).to_numpy()
    y = merged["fwd_excess_ret"].to_numpy()
    dates = pd.to_datetime(merged["as_of_date"])

    folds = _purged_kfold_indices(dates, n_splits=n_splits, embargo=horizon)
    fold_results: list[FoldResult] = []
    test_preds = pd.Series(index=merged.index, dtype=float)

    last_model = None
    for train_idx, test_idx in folds:
        if len(train_idx) < 100 or len(test_idx) < 30:
            continue
        model = lgb.LGBMRegressor(
            n_estimators=400, learning_rate=0.04, num_leaves=31,
            min_child_samples=30, subsample=0.85, colsample_bytree=0.85,
            objective="regression", verbosity=-1,
        )
        model.fit(X[train_idx], y[train_idx])
        preds = model.predict(X[test_idx])
        test_preds.iloc[test_idx] = preds
        ic, p = _spearman_ic(y[test_idx], preds)
        fold_results.append(FoldResult(
            train_size=len(train_idx), test_size=len(test_idx),
            test_ic=ic, test_corr_p_value=p,
        ))
        last_model = model

    if not fold_results:
        raise RuntimeError("train_ranker: no usable folds (sample sizes too small)")

    ics = np.array([f.test_ic for f in fold_results])
    mean_ic = float(np.mean(ics))
    ic_std = float(np.std(ics, ddof=1)) if len(ics) > 1 else 0.0
    t_stat = mean_ic / (ic_std / np.sqrt(len(ics))) if ic_std > 0 else 0.0

    # Walk-forward deflated Sharpe of the prediction series → return spread.
    # Treat each (date) cross-sectional fold as one "observation" — top-decile
    # minus bottom-decile of predictions vs the same buckets of labels.
    pred_series = test_preds.dropna()
    valid = pred_series.index
    by_date_spreads: list[float] = []
    grouped = merged.loc[valid].assign(pred=pred_series.loc[valid]).groupby("as_of_date")
    for _, grp in grouped:
        if len(grp) < 10:
            continue
        top = grp.nlargest(max(1, len(grp) // 10), "pred")["fwd_excess_ret"].mean()
        bot = grp.nsmallest(max(1, len(grp) // 10), "pred")["fwd_excess_ret"].mean()
        by_date_spreads.append(float(top - bot))
    spreads = np.array(by_date_spreads, dtype=float)
    if len(spreads) >= 5 and spreads.std(ddof=1) > 0:
        from backtest.metrics import deflated_sharpe
        wf_dsr = float(deflated_sharpe(spreads, num_trials=len(folds)))
    else:
        wf_dsr = 0.0

    # Final model — retrain on everything.
    final_model = type(last_model)(
        n_estimators=last_model.n_estimators, learning_rate=last_model.learning_rate,
        num_leaves=last_model.num_leaves, min_child_samples=last_model.min_child_samples,
        subsample=last_model.subsample, colsample_bytree=last_model.colsample_bytree,
        objective="regression", verbosity=-1,
    )
    final_model.fit(X, y)

    importances = dict(zip(feature_cols, final_model.feature_importances_.tolist()))

    return {
        "model": final_model,
        "feature_columns": feature_cols,
        "horizon": horizon,
        "n_samples": int(len(merged)),
        "n_features": int(len(feature_cols)),
        "fold_ics": [r.test_ic for r in fold_results],
        "mean_ic": mean_ic,
        "ic_t_stat": float(t_stat),
        "walk_forward_dsr": wf_dsr,
        "feature_importance": importances,
        "train_dates": (merged["as_of_date"].min(), merged["as_of_date"].max()),
    }


# ---------------------------------------------------------------------------
# Artifact I/O + DB persistence
# ---------------------------------------------------------------------------

def _save_artifact(payload: dict, horizon: int, as_of: date) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / f"{MODEL_NAME}_h{horizon}_{as_of.isoformat()}.pkl"
    with path.open("wb") as f:
        pickle.dump({
            "model": payload["model"],
            "feature_columns": payload["feature_columns"],
            "horizon": horizon,
        }, f)
    return path


async def _persist_run(payload: dict, artifact_path: Path) -> None:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    import orjson

    async with AsyncSessionLocal() as session:
        await session.execute(text("""
            INSERT INTO model_runs
                (model_name, forward_horizon_d, train_start, train_end,
                 n_samples, n_features, cv_mean_ic, cv_ic_t_stat,
                 walk_forward_dsr, feature_importance, artifact_path)
            VALUES
                (:m, :h, :ts, :te, :ns, :nf, :mic, :ict, :dsr, :fi::jsonb, :ap)
        """), {
            "m": MODEL_NAME, "h": payload["horizon"],
            "ts": payload["train_dates"][0], "te": payload["train_dates"][1],
            "ns": payload["n_samples"], "nf": payload["n_features"],
            "mic": payload["mean_ic"], "ict": payload["ic_t_stat"],
            "dsr": payload["walk_forward_dsr"],
            "fi": orjson.dumps(payload["feature_importance"]).decode(),
            "ap": str(artifact_path),
        })
        await session.commit()


# ---------------------------------------------------------------------------
# Weekly orchestrator
# ---------------------------------------------------------------------------

async def retrain_ranker(horizons: Iterable[int] = DEFAULT_HORIZONS) -> dict:
    """
    Weekly retrain: pull features from store + forward returns from yfinance,
    train per-horizon LightGBM models, persist artifacts + model_runs row.
    """
    from store.feature_store import get_feature_store
    from data.scanner import get_scan_universe
    from data.market import get_multi_ohlcv_yfinance

    store = get_feature_store()
    available = store.available_dates()
    if not available:
        logger.warning("ranker retrain: feature store is empty; skipping")
        return {}

    universe = await get_scan_universe()
    panel = store.read_panel(
        features=[
            "total_score", "ret_20d", "vol_ratio", "price_pct_52range",
            "cat_iv_analysis", "cat_momentum", "cat_trend", "cat_options_flow",
            "cat_gex_dex", "cat_volatility_regime",
        ],
        start=available[0], end=available[-1], symbols=universe[:600],
    )
    if panel.empty:
        logger.warning("ranker retrain: feature panel empty after read; skipping")
        return {}

    # Forward-return universe is the set of symbols in the panel.
    symbols = sorted(panel["symbol"].unique().tolist())
    symbols_with_bench = list(set(symbols + ["SPY"]))
    prices_dict = get_multi_ohlcv_yfinance(symbols_with_bench, period="2y")
    closes = pd.DataFrame(
        {s: df["close"] for s, df in prices_dict.items()
         if df is not None and not df.empty}
    )
    if closes.empty or "SPY" not in closes.columns:
        logger.warning("ranker retrain: missing benchmark prices, skipping")
        return {}

    out: dict[int, dict] = {}
    for horizon in horizons:
        labels = _forward_excess_returns(closes, horizon=horizon)
        if labels.empty:
            continue
        try:
            payload = train_ranker(panel, labels, horizon=horizon)
        except RuntimeError as e:
            logger.warning(f"ranker retrain h={horizon} skipped: {e}")
            continue
        artifact = _save_artifact(payload, horizon, date.today())
        await _persist_run(payload, artifact)
        out[horizon] = {
            "mean_ic": payload["mean_ic"], "ic_t_stat": payload["ic_t_stat"],
            "dsr": payload["walk_forward_dsr"], "artifact": str(artifact),
        }
        logger.info(
            f"ranker retrain h={horizon}: IC={payload['mean_ic']:+.3f} "
            f"(t={payload['ic_t_stat']:+.2f}), DSR={payload['walk_forward_dsr']:.2f}, "
            f"artifact={artifact}"
        )
    return out


# ---------------------------------------------------------------------------
# Inference helper for the scanner
# ---------------------------------------------------------------------------

def latest_artifact(horizon: int) -> Path | None:
    if not MODELS_DIR.exists():
        return None
    candidates = sorted(MODELS_DIR.glob(f"{MODEL_NAME}_h{horizon}_*.pkl"))
    return candidates[-1] if candidates else None


def score_symbols(features_row: dict[str, dict[str, float]], horizon: int = 21) -> dict[str, float]:
    """
    features_row: {symbol: {feature_name: value}} for today.
    Returns {symbol: predicted_excess_return}. Empty dict if model unavailable.
    """
    artifact = latest_artifact(horizon)
    if artifact is None:
        return {}
    try:
        with artifact.open("rb") as f:
            payload = pickle.load(f)
    except Exception as e:
        logger.debug(f"score_symbols: failed to load {artifact}: {e}")
        return {}
    model = payload["model"]
    cols = payload["feature_columns"]

    rows, symbols = [], []
    for sym, feats in features_row.items():
        rows.append([float(feats.get(c, 0.0) or 0.0) for c in cols])
        symbols.append(sym)
    if not rows:
        return {}
    preds = model.predict(np.asarray(rows))
    return dict(zip(symbols, [float(p) for p in preds]))
