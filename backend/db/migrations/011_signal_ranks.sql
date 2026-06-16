-- Migration 011: Cross-sectional signal ranks
-- Run after 010_phase_a_cleanup.sql
--
-- Stores nightly-computed cross-sectional ranks for Tier-1 signals.
-- Replaces absolute thresholds (iv_hv_ratio > 1.3, skew_25d > 0.08) with
-- universe-relative percentiles — Fable's #1 architectural call.

CREATE TABLE IF NOT EXISTS signal_ranks (
    symbol        TEXT NOT NULL,
    signal_type   TEXT NOT NULL,             -- e.g. 'vrp_z', 'skew_slope', 'momentum_12_1'
    value         DOUBLE PRECISION NOT NULL, -- raw signal value
    z_score       DOUBLE PRECISION,          -- standardized across the universe
    percentile    DOUBLE PRECISION NOT NULL, -- 0.0-1.0
    decile        SMALLINT NOT NULL,         -- 0-9
    as_of_date    DATE NOT NULL,
    PRIMARY KEY (symbol, signal_type, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_signal_ranks_signal_date
    ON signal_ranks(signal_type, as_of_date);
CREATE INDEX IF NOT EXISTS idx_signal_ranks_symbol_date
    ON signal_ranks(symbol, as_of_date);
