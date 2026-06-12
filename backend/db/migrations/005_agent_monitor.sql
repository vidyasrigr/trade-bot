-- Migration 005: Agent performance monitoring + meta-research proposals
-- Run after 004_stock_dna.sql

-- Weekly aggregated stats per agent (flushed from Redis every Sunday)
CREATE TABLE IF NOT EXISTS agent_performance_weekly (
    id                  BIGSERIAL PRIMARY KEY,
    agent_name          TEXT NOT NULL,
    week_start          DATE NOT NULL,
    total_calls         INTEGER DEFAULT 0,
    avg_response_ms     NUMERIC(10,1),
    fallback_rate_pct   NUMERIC(5,2) DEFAULT 0,
    models_json         JSONB DEFAULT '{}',     -- {"claude-sonnet-4-6": 120, "deepseek-r1:7b": 45}
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (agent_name, week_start)
);

CREATE INDEX idx_apw_week ON agent_performance_weekly(week_start DESC);
CREATE INDEX idx_apw_agent ON agent_performance_weekly(agent_name);

-- Meta-research proposals (one row per weekly run)
CREATE TABLE IF NOT EXISTS meta_research_proposals (
    id              BIGSERIAL PRIMARY KEY,
    proposal_date   DATE NOT NULL UNIQUE,
    file_path       TEXT,
    high_priority   BOOLEAN DEFAULT FALSE,  -- true if 🔴 or HIGH PRIORITY found
    summary         TEXT,                   -- first 500 chars of proposal
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Adversary agent outcomes (one row per analysis where adversary challenged)
CREATE TABLE IF NOT EXISTS adversary_challenges (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    analyzed_at     TIMESTAMPTZ DEFAULT NOW(),
    verdict         TEXT NOT NULL,           -- PASS or CHALLENGE
    challenges      JSONB DEFAULT '[]',
    risk_override   INTEGER DEFAULT 0,
    conviction_before NUMERIC(5,1),
    conviction_after  NUMERIC(5,1)
);

CREATE INDEX idx_adv_symbol ON adversary_challenges(symbol);
CREATE INDEX idx_adv_verdict ON adversary_challenges(verdict);
