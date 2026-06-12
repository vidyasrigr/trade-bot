-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ============================================================
-- CORE STOCK UNIVERSE
-- ============================================================

CREATE TABLE IF NOT EXISTS stocks (
    symbol          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    sector          TEXT,
    subsector       TEXT,
    market_cap      BIGINT,
    exchange        TEXT,
    tier            INTEGER DEFAULT 2,  -- 1=SP500/NDX, 2=theme, 3=catalyst, 4=ipo-halo
    theme_tags      TEXT[],             -- ['ai_infra', 'nuclear', 'space', ...]
    is_active       BOOLEAN DEFAULT TRUE,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_stocks_sector ON stocks(sector);
CREATE INDEX idx_stocks_tier ON stocks(tier);
CREATE INDEX idx_stocks_theme_tags ON stocks USING GIN(theme_tags);

-- ============================================================
-- TIME-SERIES PRICE DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS ohlcv_daily (
    symbol          TEXT NOT NULL,
    date            DATE NOT NULL,
    open            NUMERIC(12,4),
    high            NUMERIC(12,4),
    low             NUMERIC(12,4),
    close           NUMERIC(12,4),
    volume          BIGINT,
    adj_close       NUMERIC(12,4),
    PRIMARY KEY (symbol, date)
);

SELECT create_hypertable('ohlcv_daily', 'date', if_not_exists => TRUE);
CREATE INDEX idx_ohlcv_symbol ON ohlcv_daily(symbol, date DESC);

-- ============================================================
-- OPTIONS CHAINS
-- ============================================================

CREATE TABLE IF NOT EXISTS options_chains (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expiry          DATE NOT NULL,
    strike          NUMERIC(10,2) NOT NULL,
    option_type     CHAR(1) NOT NULL,  -- 'C' or 'P'
    bid             NUMERIC(10,4),
    ask             NUMERIC(10,4),
    last            NUMERIC(10,4),
    volume          INTEGER,
    open_interest   INTEGER,
    iv              NUMERIC(8,6),      -- implied vol as decimal
    delta           NUMERIC(8,6),
    gamma           NUMERIC(8,6),
    theta           NUMERIC(8,6),
    vega            NUMERIC(8,6),
    rho             NUMERIC(8,6)
);

SELECT create_hypertable('options_chains', 'fetched_at', if_not_exists => TRUE);
CREATE INDEX idx_options_symbol_expiry ON options_chains(symbol, expiry, strike);
CREATE INDEX idx_options_fetched ON options_chains(fetched_at DESC);

-- ============================================================
-- ANALYSIS RESULTS
-- ============================================================

CREATE TABLE IF NOT EXISTS analysis_results (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    analyzed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_score     NUMERIC(5,2),
    direction       TEXT,               -- 'bullish', 'bearish', 'neutral'
    vol_regime      TEXT,               -- 'bull_trend', 'bear_trend', 'chop', 'high_vol'
    iv_percentile   NUMERIC(5,2),
    category_scores JSONB NOT NULL,     -- {category: {score, weight, signals: []}}
    trade_thesis    TEXT,               -- Claude's narrative
    catalyst_flags  TEXT[],
    data_quality    JSONB,              -- freshness, completeness scores
    raw_signals     JSONB,              -- full sub-indicator values for audit
    stage           INTEGER DEFAULT 4  -- which funnel stage produced this
);

SELECT create_hypertable('analysis_results', 'analyzed_at', if_not_exists => TRUE);
CREATE INDEX idx_analysis_symbol ON analysis_results(symbol, analyzed_at DESC);
CREATE INDEX idx_analysis_score ON analysis_results(total_score DESC);

-- ============================================================
-- PAPER TRADES
-- ============================================================

CREATE TABLE IF NOT EXISTS paper_trades (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    analysis_id     BIGINT REFERENCES analysis_results(id),
    direction       TEXT NOT NULL,      -- 'long', 'short'
    strategy        TEXT NOT NULL,      -- 'long_call', 'bull_call_spread', 'iron_condor', etc.
    expiry          DATE NOT NULL,
    short_strike    NUMERIC(10,2),
    long_strike     NUMERIC(10,2),
    contracts       INTEGER NOT NULL DEFAULT 1,
    entry_price     NUMERIC(10,4),      -- debit paid or credit received per contract
    entry_iv        NUMERIC(8,6),
    entry_delta     NUMERIC(8,6),
    entry_theta     NUMERIC(8,6),
    target_price    NUMERIC(10,4),      -- profit target (50% of max for premium-sell)
    stop_price      NUMERIC(10,4),      -- max loss level
    max_profit      NUMERIC(10,4),
    max_loss        NUMERIC(10,4),
    exit_price      NUMERIC(10,4),
    exit_reason     TEXT,               -- 'target_hit', 'stop_hit', 'expiry', 'manual'
    realized_pnl    NUMERIC(10,4),
    r_multiple      NUMERIC(8,4),       -- realized_pnl / initial_risk
    status          TEXT DEFAULT 'open', -- 'open', 'closed', 'expired'
    opened_at       TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    tradier_order_id TEXT,
    notes           TEXT
);

CREATE INDEX idx_trades_symbol ON paper_trades(symbol);
CREATE INDEX idx_trades_status ON paper_trades(status);
CREATE INDEX idx_trades_opened ON paper_trades(opened_at DESC);

-- ============================================================
-- TRADE FACTORS (which signals were active at entry)
-- ============================================================

CREATE TABLE IF NOT EXISTS trade_factors (
    id              BIGSERIAL PRIMARY KEY,
    trade_id        BIGINT NOT NULL REFERENCES paper_trades(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,
    signal_name     TEXT NOT NULL,
    signal_value    NUMERIC,
    signal_direction TEXT,
    weight_at_entry NUMERIC(5,4),
    regime_at_entry TEXT
);

CREATE INDEX idx_trade_factors_trade ON trade_factors(trade_id);
CREATE INDEX idx_trade_factors_category ON trade_factors(category);

-- ============================================================
-- INFORMATION COEFFICIENT TRACKING
-- ============================================================

CREATE TABLE IF NOT EXISTS factor_ic_scores (
    id              BIGSERIAL PRIMARY KEY,
    category        TEXT NOT NULL,
    regime          TEXT NOT NULL,      -- 'bull_trend', 'bear_trend', 'chop', 'high_vol', 'all'
    ic_score        NUMERIC(8,6),
    sample_count    INTEGER DEFAULT 0,
    current_weight_multiplier NUMERIC(6,4) DEFAULT 1.0,
    last_halved_at  TIMESTAMPTZ,
    history         JSONB DEFAULT '[]', -- rolling IC history
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (category, regime)
);

-- ============================================================
-- MEMORY / LEARNING JOURNAL
-- ============================================================

CREATE TABLE IF NOT EXISTS memory_entries (
    id              BIGSERIAL PRIMARY KEY,
    trade_id        BIGINT REFERENCES paper_trades(id),
    symbol          TEXT,
    sector          TEXT,
    regime          TEXT,
    lesson          TEXT NOT NULL,      -- Claude's distilled lesson
    r_multiple      NUMERIC(8,4),
    factors_that_worked  TEXT[],
    factors_that_failed  TEXT[],
    embedding       vector(768),        -- Ollama nomic-embed-text dims
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    compacted       BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_memory_embedding ON memory_entries USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_memory_regime ON memory_entries(regime);
CREATE INDEX idx_memory_sector ON memory_entries(sector);
CREATE INDEX idx_memory_trade ON memory_entries(trade_id);

-- ============================================================
-- WEIGHT ADJUSTMENTS LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS weight_adjustments (
    id              BIGSERIAL PRIMARY KEY,
    category        TEXT NOT NULL,
    regime          TEXT NOT NULL,
    old_multiplier  NUMERIC(6,4),
    new_multiplier  NUMERIC(6,4),
    reason          TEXT,
    adjusted_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ANALYST PRICE TARGETS
-- ============================================================

CREATE TABLE IF NOT EXISTS analyst_targets (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    source          TEXT,               -- 'fmp', 'benzinga', 'tipranks'
    analyst_name    TEXT,
    firm            TEXT,
    rating          TEXT,               -- 'Buy', 'Sell', 'Hold', 'Overweight', etc.
    price_target    NUMERIC(10,2),
    prev_target     NUMERIC(10,2),
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('analyst_targets', 'fetched_at', if_not_exists => TRUE);
CREATE INDEX idx_analyst_symbol ON analyst_targets(symbol, fetched_at DESC);

-- ============================================================
-- YOUTUBE INFLUENCER SIGNALS
-- ============================================================

CREATE TABLE IF NOT EXISTS youtube_channels (
    channel_id      TEXT PRIMARY KEY,
    channel_name    TEXT NOT NULL,
    subscriber_count BIGINT,
    total_calls     INTEGER DEFAULT 0,
    accurate_calls  INTEGER DEFAULT 0,
    credibility_score NUMERIC(5,4) DEFAULT 0.5,
    last_video_at   TIMESTAMPTZ,
    added_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS youtube_calls (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      TEXT REFERENCES youtube_channels(channel_id),
    video_id        TEXT NOT NULL,
    video_title     TEXT,
    published_at    TIMESTAMPTZ,
    symbol          TEXT NOT NULL,
    direction       TEXT NOT NULL,      -- 'bullish', 'bearish'
    entry_level     NUMERIC(10,2),
    target_level    NUMERIC(10,2),
    reasoning_type  TEXT,               -- 'quantitative', 'fundamental', 'hype', 'narrative'
    reasoning_quality NUMERIC(5,4),     -- Claude quality score 0-1
    price_at_publish  NUMERIC(10,4),
    price_t1        NUMERIC(10,4),      -- T+1 day
    price_t5        NUMERIC(10,4),      -- T+5 days
    price_t20       NUMERIC(10,4),      -- T+20 days
    outcome         TEXT,               -- 'win', 'loss', 'pending'
    pre_video_call_volume_ratio NUMERIC(8,4),  -- unusual call OI 1-3 days before vs avg
    pump_signal     BOOLEAN DEFAULT FALSE,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_yt_calls_symbol ON youtube_calls(symbol);
CREATE INDEX idx_yt_calls_channel ON youtube_calls(channel_id);
CREATE INDEX idx_yt_calls_outcome ON youtube_calls(outcome);

-- ============================================================
-- POLITICAL / OGE DISCLOSURES
-- ============================================================

CREATE TABLE IF NOT EXISTS political_disclosures (
    id              BIGSERIAL PRIMARY KEY,
    official_name   TEXT NOT NULL,
    official_role   TEXT,
    symbol          TEXT NOT NULL,
    transaction_type TEXT,              -- 'purchase', 'sale'
    amount_range    TEXT,               -- OGE reports ranges, not exact
    transaction_date DATE,
    disclosure_date  DATE,
    asset_name      TEXT,
    subsequent_govt_event TEXT,         -- linked contract/deal if found
    price_at_disclosure NUMERIC(10,4),
    price_30d_later  NUMERIC(10,4),
    source_url      TEXT,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_political_symbol ON political_disclosures(symbol);
CREATE INDEX idx_political_date ON political_disclosures(transaction_date DESC);

-- ============================================================
-- IPO PIPELINE
-- ============================================================

CREATE TABLE IF NOT EXISTS ipo_pipeline (
    id              BIGSERIAL PRIMARY KEY,
    company_name    TEXT NOT NULL,
    expected_symbol TEXT,
    s1_filed_date   DATE,
    expected_ipo_date DATE,
    estimated_valuation NUMERIC(15,2),
    sector          TEXT,
    notes           TEXT,
    status          TEXT DEFAULT 'filed', -- 'rumored', 'filed', 'roadshow', 'priced', 'trading'
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ipo_halo_mappings (
    id              BIGSERIAL PRIMARY KEY,
    ipo_id          INTEGER REFERENCES ipo_pipeline(id),
    symbol          TEXT NOT NULL,
    relationship    TEXT,               -- 'supplier', 'customer', 'sector_peer', 'etf'
    halo_score      INTEGER,            -- 1-10
    reasoning       TEXT
);

-- ============================================================
-- CATALYST EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS catalyst_events (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    event_type      TEXT NOT NULL,      -- 'unusual_options', 'earnings', 'govt_contract', 'sec_8k', 'oge_disclosure', 'ipo_filing'
    event_summary   TEXT,
    signal_strength NUMERIC(5,2),       -- 0-100
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    triggered_analysis BIGINT REFERENCES analysis_results(id),
    resolved        BOOLEAN DEFAULT FALSE
);

SELECT create_hypertable('catalyst_events', 'detected_at', if_not_exists => TRUE);
CREATE INDEX idx_catalyst_symbol ON catalyst_events(symbol, detected_at DESC);
CREATE INDEX idx_catalyst_unresolved ON catalyst_events(resolved) WHERE resolved = FALSE;

-- ============================================================
-- AUDIT TRAIL
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    analysis_id     BIGINT REFERENCES analysis_results(id),
    trade_id        BIGINT REFERENCES paper_trades(id),
    event_type      TEXT NOT NULL,      -- 'analysis', 'trade_open', 'trade_close', 'alert', 'postmortem'
    claude_prompt   TEXT,
    claude_response TEXT,
    memory_entries_used JSONB,
    data_sources    JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('audit_log', 'created_at', if_not_exists => TRUE);

-- ============================================================
-- NEWS / CATALYST FEED CACHE
-- ============================================================

CREATE TABLE IF NOT EXISTS news_items (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT,
    headline        TEXT NOT NULL,
    source          TEXT,
    url             TEXT,
    published_at    TIMESTAMPTZ,
    sentiment       TEXT,               -- 'positive', 'negative', 'neutral'
    relevance_score NUMERIC(5,4),       -- Ollama relevance 0-1
    category        TEXT,               -- sector tag
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('news_items', 'fetched_at', if_not_exists => TRUE);
CREATE INDEX idx_news_symbol ON news_items(symbol, fetched_at DESC);

-- ============================================================
-- PORTFOLIO STATE (open positions aggregate)
-- ============================================================

CREATE TABLE IF NOT EXISTS portfolio_state (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_at     TIMESTAMPTZ DEFAULT NOW(),
    total_deployed  NUMERIC(10,4),      -- % of capital deployed
    net_delta       NUMERIC(8,4),
    sector_exposure JSONB,              -- {sector: pct}
    open_trade_ids  INTEGER[],
    notes           TEXT
);

-- ============================================================
-- INITIAL SEED DATA — IC priors from published research
-- ============================================================

INSERT INTO factor_ic_scores (category, regime, ic_score, sample_count, current_weight_multiplier)
VALUES
    ('iv_analysis',        'all',        0.07, 0,   1.0),
    ('iv_analysis',        'bull_trend', 0.07, 0,   1.0),
    ('iv_analysis',        'bear_trend', 0.08, 0,   1.1),
    ('iv_analysis',        'chop',       0.09, 0,   1.2),
    ('iv_analysis',        'high_vol',   0.10, 0,   1.3),
    ('trend',              'all',        0.06, 0,   1.0),
    ('trend',              'bull_trend', 0.08, 0,   1.2),
    ('trend',              'bear_trend', 0.07, 0,   1.1),
    ('trend',              'chop',       0.02, 0,   0.6),
    ('momentum',           'all',        0.05, 0,   1.0),
    ('momentum',           'bull_trend', 0.07, 0,   1.1),
    ('momentum',           'chop',       0.01, 0,   0.5),
    ('options_chain',      'all',        0.06, 0,   1.0),
    ('options_flow',       'all',        0.08, 0,   1.0),
    ('fundamental',        'all',        0.04, 0,   0.9),
    ('support_resistance', 'all',        0.05, 0,   1.0),
    ('gex_dex',            'all',        0.07, 0,   1.0),
    ('volatility_regime',  'all',        0.06, 0,   1.0),
    ('sentiment',          'all',        0.04, 0,   0.9),
    ('macro',              'all',        0.03, 0,   0.8)
ON CONFLICT (category, regime) DO NOTHING;

-- ============================================================
-- INITIAL IPO PIPELINE SEED
-- ============================================================

INSERT INTO ipo_pipeline (company_name, expected_symbol, s1_filed_date, expected_ipo_date, estimated_valuation, sector, notes, status)
VALUES
    ('SpaceX', 'SPCE2', '2026-05-20', NULL, 1500000000000, 'Space economy', 'Starlink spin-off or full SpaceX S-1 filed May 20 2026', 'filed'),
    ('OpenAI',  NULL,   NULL,          '2026-09-01', 1000000000000, 'AI software', 'Targeting September 2026 IPO at ~$1T+ valuation', 'rumored')
ON CONFLICT DO NOTHING;

-- ============================================================
-- INITIAL HALO MAPPINGS
-- ============================================================

INSERT INTO ipo_halo_mappings (ipo_id, symbol, relationship, halo_score, reasoning)
SELECT p.id, unnest(ARRAY['RDW','RKLB','ASTS','VORB']), 'sector_peer', unnest(ARRAY[9,8,7,6]),
       'SpaceX halo — direct sector comp or launch services overlap'
FROM ipo_pipeline p WHERE p.company_name = 'SpaceX'
ON CONFLICT DO NOTHING;
