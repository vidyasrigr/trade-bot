-- Migration 014: Phase F operational maturity
-- Run after 013_ranker_runs.sql

-- ============================================================
-- Promotion ladder: each (category, regime) is in exactly one lifecycle state.
-- ============================================================

ALTER TABLE factor_ic_scores
    ADD COLUMN IF NOT EXISTS signal_status TEXT NOT NULL DEFAULT 'live_full';
ALTER TABLE factor_ic_scores
    ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ DEFAULT NOW();

-- Permitted states: proposed → paper → live_small → live_full → demoted
CREATE INDEX IF NOT EXISTS idx_factor_ic_status ON factor_ic_scores(signal_status);
