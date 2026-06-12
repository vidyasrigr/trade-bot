-- Migration 004: Per-stock behavioral DNA, LT investment pipeline, portfolio holdings
-- Run after init.sql

-- ============================================================
-- PER-STOCK BEHAVIORAL DNA
-- ============================================================
-- Stores computed behavioral profiles per stock, updated nightly.
-- Each stock gets its own model trained on 3-5 years of history.

CREATE TABLE IF NOT EXISTS stock_dna (
    symbol                          TEXT PRIMARY KEY,

    -- Earnings behavior metrics
    earnings_realized_implied_ratio NUMERIC(8,4),   -- avg (actual move) / (straddle-implied). <1 = IV overpriced
    earnings_direction_bias_on_beat NUMERIC(8,4),   -- % of beats where stock went UP next day (0.0-1.0)
    iv_crush_avg_pct                NUMERIC(8,4),   -- average IV% drop in first trading day post-earnings
    beat_and_raise_pead_rate        NUMERIC(8,4),   -- % of beat+raise events followed by 30d positive drift
    earnings_events_count           INTEGER DEFAULT 0,

    -- Sell-the-news conditions (JSONB: maps condition-set → empirical hit rate)
    -- e.g. {"high_ivr_pre_run_eps_only_beat": 0.72}
    sell_news_conditions            JSONB DEFAULT '{}',

    -- Post-ATH behavior
    post_ath_5d_median_return       NUMERIC(8,4),   -- median 5-day return after hitting 52wk ATH
    post_ath_20d_median_return      NUMERIC(8,4),   -- median 20-day return after hitting ATH
    ath_continuation_rate           NUMERIC(8,4),   -- % of ATH events where stock was higher 20d later

    -- Momentum characteristics
    momentum_persistence_days       INTEGER,        -- typical days a momentum move lasts before mean reversion
    volume_leads_price_days         INTEGER,        -- days unusual volume precedes price move

    -- Per-stock technical indicator efficacy (information coefficient)
    -- e.g. {"rsi": 0.08, "macd": -0.02, "ema21_crossover": 0.11}
    best_indicator_ic               JSONB DEFAULT '{}',

    -- Sector / cascade membership
    semis_cascade_member            BOOLEAN DEFAULT FALSE,
    hyperscaler_lag_days            INTEGER DEFAULT 0,  -- days after MSFT/GOOGL/META earnings that this stock moves

    -- Data quality flags
    uses_behavioral_twins           BOOLEAN DEFAULT FALSE,  -- true if <8 earnings events → pooled similar stocks
    twin_symbols                    TEXT[],                  -- symbols used as behavioral twins
    data_quality_score              NUMERIC(5,2),            -- 0-100: confidence in the DNA

    computed_at                     TIMESTAMPTZ DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dna_semis_cascade ON stock_dna(semis_cascade_member) WHERE semis_cascade_member = TRUE;
CREATE INDEX idx_dna_updated ON stock_dna(updated_at DESC);

-- ============================================================
-- FUNDAMENTAL HISTORY (daily snapshots for LT percentile calcs)
-- ============================================================
-- Stores daily snapshots of key fundamentals for percentile computation.
-- Enables "P/E vs own 5-year mean" and "gross margin trend" calculations.

CREATE TABLE IF NOT EXISTS fundamental_history (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    snapshot_date       DATE NOT NULL,

    -- Valuation
    pe_ratio            NUMERIC(10,2),
    forward_pe          NUMERIC(10,2),
    ps_ratio            NUMERIC(10,2),
    ev_ebitda           NUMERIC(10,2),
    peg_ratio           NUMERIC(10,2),
    fcf_yield           NUMERIC(8,4),       -- FCF / market cap (decimal)

    -- Growth
    revenue_qoq         NUMERIC(8,4),       -- revenue QoQ growth (decimal)
    revenue_yoy         NUMERIC(8,4),       -- revenue YoY growth (decimal)
    eps_qoq             NUMERIC(8,4),
    eps_yoy             NUMERIC(8,4),
    gross_margin        NUMERIC(8,4),       -- gross profit / revenue (decimal)
    operating_margin    NUMERIC(8,4),

    -- Quality
    piotroski_fscore    INTEGER,            -- 0-9 Piotroski F-score
    roic                NUMERIC(8,4),       -- return on invested capital (decimal)
    fcf_to_earnings     NUMERIC(8,4),       -- FCF / net income ratio (quality measure)
    accruals_ratio      NUMERIC(8,4),       -- (net income - OCF) / total assets (Sloan 1996)

    -- Moat
    rule_of_40          NUMERIC(8,2),       -- revenue_growth% + EBITDA_margin% (for SaaS)
    insider_ownership   NUMERIC(8,4),       -- insider ownership fraction (decimal)

    -- Analyst signals
    eps_estimate_revision_pct NUMERIC(8,4), -- % change in consensus EPS estimate vs 4 weeks ago
    analyst_count       INTEGER,

    source              TEXT DEFAULT 'fmp',
    fetched_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (symbol, snapshot_date)
);

SELECT create_hypertable('fundamental_history', 'snapshot_date', if_not_exists => TRUE);
CREATE INDEX idx_fh_symbol ON fundamental_history(symbol, snapshot_date DESC);

-- ============================================================
-- PORTFOLIO HOLDINGS (seeded from Robinhood CSV exports)
-- ============================================================

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    asset_type          TEXT DEFAULT 'stock',   -- 'stock', 'etf', 'option'
    shares              NUMERIC(12,4),
    avg_cost_basis      NUMERIC(10,4),
    total_cost          NUMERIC(12,4),

    -- Live-computed fields (updated by watchlist agent)
    current_price       NUMERIC(10,4),
    market_value        NUMERIC(12,4),
    unrealized_pnl      NUMERIC(12,4),
    unrealized_pnl_pct  NUMERIC(8,4),

    -- LT scoring (updated nightly)
    lt_score            NUMERIC(5,1),           -- 0-100 LT composite score
    lt_tier             TEXT,                   -- 'leaps_candidate', 'long', 'neutral', 'blocked'
    covered_call_flag   BOOLEAN DEFAULT FALSE,  -- true when IVR > 60 + LT score > 65

    -- Sell trigger status (updated after each earnings cycle)
    sell_trigger_active BOOLEAN DEFAULT FALSE,
    sell_trigger_reason TEXT,
    sell_trigger_fired_at TIMESTAMPTZ,

    -- Tranche levels (JSON: {t1, t2, t3, t4, stop})
    tranche_levels      JSONB,

    -- Metadata
    import_source       TEXT DEFAULT 'robinhood_csv',
    imported_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (symbol, import_source)
);

CREATE INDEX idx_holdings_lt_score ON portfolio_holdings(lt_score DESC);
CREATE INDEX idx_holdings_sell_trigger ON portfolio_holdings(sell_trigger_active) WHERE sell_trigger_active = TRUE;
CREATE INDEX idx_holdings_covered_call ON portfolio_holdings(covered_call_flag) WHERE covered_call_flag = TRUE;

-- ============================================================
-- LT SCORE HISTORY (for tracking score drift over time)
-- ============================================================

CREATE TABLE IF NOT EXISTS lt_score_history (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    scored_at   TIMESTAMPTZ DEFAULT NOW(),
    lt_score    NUMERIC(5,1),
    valuation_score     NUMERIC(5,1),
    growth_score        NUMERIC(5,1),
    quality_score       NUMERIC(5,1),
    moat_score          NUMERIC(5,1),
    tier                TEXT,
    notes               TEXT
);

SELECT create_hypertable('lt_score_history', 'scored_at', if_not_exists => TRUE);
CREATE INDEX idx_lt_history_symbol ON lt_score_history(symbol, scored_at DESC);

-- ============================================================
-- COMPOUND SIGNAL EVENTS (semiconductor cascade, VIX spike, etc.)
-- ============================================================

CREATE TABLE IF NOT EXISTS compound_signal_events (
    id              BIGSERIAL PRIMARY KEY,
    signal_type     TEXT NOT NULL,          -- 'semis_cascade', 'vix_spike_buy', 'beat_raise_pead',
                                             --  'hyperscaler_lead', 'analyst_revision_cascade', 'sector_dispersion'
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    symbols         TEXT[],                 -- stocks involved
    trigger_details JSONB,                  -- raw data that triggered the signal
    confidence      NUMERIC(5,2),           -- 0-100
    action_taken    TEXT,                   -- 'discord_alert', 'watchlist_add', etc.
    resolved        BOOLEAN DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    outcome         TEXT                    -- 'confirmed', 'false_positive', 'pending'
);

SELECT create_hypertable('compound_signal_events', 'detected_at', if_not_exists => TRUE);
CREATE INDEX idx_compound_type ON compound_signal_events(signal_type, detected_at DESC);
CREATE INDEX idx_compound_unresolved ON compound_signal_events(resolved) WHERE resolved = FALSE;

-- ============================================================
-- BEHAVIORAL TWIN REGISTRY
-- ============================================================
-- Maps sparse-data stocks to their behavioral twins for DNA computation.

CREATE TABLE IF NOT EXISTS behavioral_twins (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    twin_symbol     TEXT NOT NULL,
    similarity_score NUMERIC(8,4),  -- 0.0-1.0 (FAISS cosine similarity)
    basis           TEXT,           -- 'sector+marketcap+iv_structure', etc.
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, twin_symbol)
);

CREATE INDEX idx_twins_symbol ON behavioral_twins(symbol);

-- ============================================================
-- INITIAL SEED: semis cascade members
-- ============================================================

INSERT INTO stock_dna (symbol, semis_cascade_member, hyperscaler_lag_days, data_quality_score)
VALUES
    ('NVDA', TRUE, 14, 0),
    ('AMD',  TRUE, 7,  0),
    ('INTC', TRUE, 7,  0),
    ('AVGO', TRUE, 7,  0),
    ('QCOM', TRUE, 7,  0),
    ('MU',   TRUE, 10, 0),
    ('TSM',  TRUE, 10, 0),
    ('AMAT', TRUE, 7,  0),
    ('LRCX', TRUE, 7,  0),
    ('KLAC', TRUE, 7,  0)
ON CONFLICT (symbol) DO UPDATE
    SET semis_cascade_member = EXCLUDED.semis_cascade_member,
        hyperscaler_lag_days = EXCLUDED.hyperscaler_lag_days;
