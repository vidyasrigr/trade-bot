-- Migration 013: LightGBM ranker training runs
-- Run after 012_phase_d_signals.sql

CREATE TABLE IF NOT EXISTS model_runs (
    id                  BIGSERIAL PRIMARY KEY,
    model_name          TEXT NOT NULL,            -- 'lightgbm_cross_section'
    forward_horizon_d   INTEGER NOT NULL,         -- 5, 21, or 63
    train_start         DATE NOT NULL,
    train_end           DATE NOT NULL,
    n_samples           INTEGER NOT NULL,
    n_features          INTEGER NOT NULL,
    cv_mean_ic          DOUBLE PRECISION,         -- cross-fold mean information coefficient
    cv_ic_t_stat        DOUBLE PRECISION,
    walk_forward_dsr    DOUBLE PRECISION,         -- deflated Sharpe of next-fold predictions
    feature_importance  JSONB DEFAULT '{}',
    artifact_path       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_runs_horizon ON model_runs(forward_horizon_d, created_at DESC);
