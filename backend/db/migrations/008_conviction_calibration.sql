-- Migration 008: Conviction calibration
-- Run after 007_backtest_runs.sql
--
-- Stores the system's stated conviction (0-100) at trade entry so realized
-- outcomes can be compared against it (Brier score / calibration buckets).
-- Without this, "conviction 85" is a vibe, not a probability.

ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS conviction NUMERIC(5,2);

CREATE INDEX IF NOT EXISTS idx_trades_conviction
    ON paper_trades(conviction) WHERE conviction IS NOT NULL;
