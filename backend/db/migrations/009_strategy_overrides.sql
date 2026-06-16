-- Migration 009: Strategy guardrail overrides + applied_at tracking
-- Run after 008_conviction_calibration.sql
--
-- strategy_overrides: human PATCH edits to risk guardrails surfaced on the
-- Strategy page. One row per key (max_position_size_pct, etc.).
-- strategy_journal.applied_at: marks when a proposed change has been adopted
-- so the Pending Review tab only shows truly pending items.

CREATE TABLE IF NOT EXISTS strategy_overrides (
    key         TEXT PRIMARY KEY,           -- e.g. 'max_position_size_pct'
    value       NUMERIC(14,4) NOT NULL,
    note        TEXT,
    author      TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE strategy_journal ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ;
