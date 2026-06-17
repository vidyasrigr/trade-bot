-- Migration 018: Recommendation log + signal performance + outcomes
-- Run after 017_stock_climate.sql
--
-- Goal: make every prediction the system has ever made queryable later, with
-- a clear "this is what we said would happen / this is what did happen" trail.
-- A future LLM / model can pull this history to do a real postmortem.

-- ============================================================
-- recommendations: every pipeline output across all 3 streams
-- ============================================================

CREATE TABLE IF NOT EXISTS recommendations (
    id                   BIGSERIAL PRIMARY KEY,
    recommended_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stream               TEXT NOT NULL,            -- 'options' | 'swing' | 'mid_term' | 'long_term'
    symbol               TEXT NOT NULL,
    strategy             TEXT,                     -- 'long_call', 'iron_condor', 'long_equity', etc.
    direction            TEXT,                     -- 'bullish' | 'bearish' | 'neutral'
    conviction           NUMERIC(5,2),             -- 0-100
    -- What we PREDICTED at recommendation time
    entry_price          NUMERIC(12,4),            -- expected entry mid for options, share price for equity
    target_price         NUMERIC(12,4),            -- predicted profit target
    stop_price           NUMERIC(12,4),            -- predicted stop
    predicted_max_profit_usd NUMERIC(12,2),
    predicted_max_loss_usd   NUMERIC(12,2),
    expected_value_pct   NUMERIC(8,2),             -- from return_projection
    prob_profit          NUMERIC(6,4),             -- IV-implied or LT model
    -- Time horizon
    target_resolution_date DATE NOT NULL,          -- when we EXPECT this to resolve
    actual_resolution_date DATE,                   -- when we ACTUALLY observed resolution
    -- Reasoning
    thesis               TEXT,
    signals_fired        TEXT[] DEFAULT '{}',      -- which signals contributed (whale_flow, vrp_z, etc.)
    market_climate       TEXT,                     -- what was the market doing at rec time
    stock_climate        TEXT,                     -- what was THE stock doing
    -- Lineage
    model_version        TEXT,                     -- e.g. 'claude-opus-4-7-2026-06-16'
    pipeline_version     TEXT,                     -- git short SHA
    raw_ticket           JSONB DEFAULT '{}',       -- the entire order ticket for forensic replay
    -- Status
    status               TEXT NOT NULL DEFAULT 'open',
                                                    -- 'open' | 'paper_filled' | 'live_filled'
                                                    -- 'resolved_win' | 'resolved_loss' | 'expired_unfilled'
    paper_trade_id       BIGINT REFERENCES paper_trades(id),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rec_stream_status ON recommendations(stream, status);
CREATE INDEX IF NOT EXISTS idx_rec_symbol ON recommendations(symbol);
CREATE INDEX IF NOT EXISTS idx_rec_target_date ON recommendations(target_resolution_date)
    WHERE status IN ('open', 'paper_filled', 'live_filled');

-- ============================================================
-- recommendation_outcomes: scheduled checkpoints during the holding period
-- ============================================================

CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    id                   BIGSERIAL PRIMARY KEY,
    recommendation_id    BIGINT NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    checkpoint_date      DATE NOT NULL,
    days_elapsed         INTEGER NOT NULL,
    -- What actually happened by this checkpoint
    actual_price         NUMERIC(12,4),
    actual_pnl_usd       NUMERIC(12,2),
    actual_pnl_pct       NUMERIC(8,4),
    target_hit           BOOLEAN NOT NULL DEFAULT FALSE,
    stop_hit             BOOLEAN NOT NULL DEFAULT FALSE,
    drawdown_max         NUMERIC(8,4),             -- worst MTM during the hold
    -- Comparison
    expected_vs_actual   NUMERIC(8,4),             -- (actual - predicted) / predicted
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (recommendation_id, checkpoint_date)
);

CREATE INDEX IF NOT EXISTS idx_rec_outcomes_rec_id ON recommendation_outcomes(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_rec_outcomes_date ON recommendation_outcomes(checkpoint_date);

-- ============================================================
-- signal_performance_daily: nightly snapshot per signal
-- ============================================================

CREATE TABLE IF NOT EXISTS signal_performance_daily (
    signal_name          TEXT NOT NULL,
    as_of_date           DATE NOT NULL,
    -- Counts
    fires_today          INTEGER NOT NULL DEFAULT 0,
    fires_trailing_30d   INTEGER NOT NULL DEFAULT 0,
    fires_total          INTEGER NOT NULL DEFAULT 0,
    -- Realized outcomes (only filled in when recommendations resolve)
    hit_rate_30d         NUMERIC(6,4),             -- % of resolved recs in last 30d that hit target
    hit_rate_total       NUMERIC(6,4),
    mean_excess_return_30d NUMERIC(8,4),
    mean_excess_return_total NUMERIC(8,4),
    -- Rolling stats from factor_ic_scores (current snapshot)
    ic_score             NUMERIC(8,6),
    weight_multiplier    NUMERIC(6,4),
    promotion_status     TEXT,
    -- Backtest reference (most recent backtest_runs row for this signal)
    last_dsr             NUMERIC(8,4),
    last_dsr_at          TIMESTAMPTZ,
    PRIMARY KEY (signal_name, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_sig_perf_signal ON signal_performance_daily(signal_name, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_sig_perf_date ON signal_performance_daily(as_of_date);

-- ============================================================
-- model_decisions: lineage trail for every LLM-driven decision
-- ============================================================

CREATE TABLE IF NOT EXISTS model_decisions (
    id                   BIGSERIAL PRIMARY KEY,
    recommendation_id    BIGINT REFERENCES recommendations(id),
    decided_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_role           TEXT NOT NULL,            -- 'trader', 'adversary', 'risk_manager', 'analyst'
    model_id             TEXT NOT NULL,            -- 'claude-opus-4-7', 'qwq:32b-q3_k_m', etc.
    prompt_hash          TEXT,                     -- hash of the prompt (privacy-safe)
    raw_response         TEXT,                     -- what the model actually said
    structured_output    JSONB DEFAULT '{}',       -- parsed Pydantic output
    latency_ms           INTEGER,
    cost_usd             NUMERIC(10,4)
);

CREATE INDEX IF NOT EXISTS idx_model_decisions_rec ON model_decisions(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_model_decisions_model ON model_decisions(model_id, decided_at);
