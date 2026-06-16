-- Migration 015: Markov regime forecasts (Phase G.2)
-- Run after 014_phase_f_ops.sql

CREATE TABLE IF NOT EXISTS regime_forecasts (
    scope          TEXT NOT NULL,                -- 'market' or symbol
    as_of_date     DATE NOT NULL,
    current_state  TEXT NOT NULL,
    forecast_5d    JSONB NOT NULL DEFAULT '{}',  -- {bull_trend: 0.42, ...}
    forecast_21d   JSONB NOT NULL DEFAULT '{}',
    forecast_63d   JSONB NOT NULL DEFAULT '{}',
    stationary     JSONB NOT NULL DEFAULT '{}',  -- long-run regime mix
    sample_size    INTEGER NOT NULL,
    PRIMARY KEY (scope, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_regime_forecasts_scope
    ON regime_forecasts(scope, as_of_date DESC);
