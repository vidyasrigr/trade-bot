-- 020 — signal promotion/demotion audit log (P0 Stage 3.3)
-- Every automated state transition (esp. demotions) is recorded so V can trace
-- why a signal's weight changed, and so the edge-decay dashboard (Stage 7) has history.

CREATE TABLE IF NOT EXISTS signal_registry_changes (
    id            BIGSERIAL PRIMARY KEY,
    category      TEXT NOT NULL,
    regime        TEXT NOT NULL DEFAULT 'all',
    from_state    TEXT,
    to_state      TEXT NOT NULL,
    reason        TEXT,
    metric_value  NUMERIC,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sig_changes_cat ON signal_registry_changes (category, changed_at DESC);
