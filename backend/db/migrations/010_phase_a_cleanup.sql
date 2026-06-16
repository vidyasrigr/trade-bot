-- Migration 010: Phase A cleanup (2026-06-14)
-- Run after 009_strategy_overrides.sql
--
-- Removes hardcoded sector lookup fields from stock_dna, creates the seed_lessons
-- table for canonical playbook examples, and purges synthetic priors that were
-- previously inserted into memory_entries (which the trader's RAG retrieval queries).

-- ============================================================
-- stock_dna: drop columns that encoded hand-coded sector beliefs
-- ============================================================

ALTER TABLE stock_dna DROP COLUMN IF EXISTS iv_crush_avg_pct;
ALTER TABLE stock_dna DROP COLUMN IF EXISTS semis_cascade_member;
ALTER TABLE stock_dna DROP COLUMN IF EXISTS hyperscaler_lag_days;
DROP INDEX IF EXISTS idx_dna_semis_cascade;

-- ============================================================
-- seed_lessons: canonical playbook examples, NOT queried by _retrieve_memory
-- ============================================================

CREATE TABLE IF NOT EXISTS seed_lessons (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    strategy            TEXT NOT NULL,
    direction           TEXT NOT NULL,
    regime              TEXT NOT NULL,
    iv_percentile       NUMERIC(5,2),
    r_multiple          NUMERIC(6,2),               -- illustrative, not a real trade
    lesson              TEXT NOT NULL,
    factors_that_worked TEXT[] DEFAULT '{}',
    factors_that_failed TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, strategy, regime)
);

CREATE INDEX IF NOT EXISTS idx_seed_lessons_regime ON seed_lessons(regime);

-- ============================================================
-- memory_entries: purge synthetic priors that were seeded as if they were real
-- ============================================================

DELETE FROM memory_entries
WHERE trade_id IS NULL
  AND (lesson LIKE '[SYNTHETIC PRIOR%' OR r_multiple IS NULL);
