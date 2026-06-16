-- Migration 016: Phase I signal tables (whale flow, short squeeze, reddit sentiment)
-- Run after 015_regime_forecasts.sql

CREATE TABLE IF NOT EXISTS whale_flow_signals (
    symbol                 TEXT NOT NULL,
    as_of_date             DATE NOT NULL,
    sweep_score            DOUBLE PRECISION NOT NULL,
    call_sweep_usd         DOUBLE PRECISION NOT NULL,
    put_sweep_usd          DOUBLE PRECISION NOT NULL,
    directional_imbalance  DOUBLE PRECISION NOT NULL,
    whale_signal           DOUBLE PRECISION NOT NULL,
    sample_contracts       INTEGER NOT NULL,
    PRIMARY KEY (symbol, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_whale_flow_date ON whale_flow_signals(as_of_date);
CREATE INDEX IF NOT EXISTS idx_whale_flow_signal
    ON whale_flow_signals(whale_signal DESC, as_of_date DESC);


CREATE TABLE IF NOT EXISTS short_squeeze_signals (
    symbol                 TEXT NOT NULL,
    as_of_date             DATE NOT NULL,
    si_pct_float           NUMERIC(6,4) NOT NULL,
    days_to_cover          NUMERIC(8,4),
    price_above_sma20      BOOLEAN NOT NULL,
    ret_5d                 NUMERIC(8,6) NOT NULL,
    ret_20d                NUMERIC(8,6) NOT NULL,
    catalyst_within_5d     BOOLEAN NOT NULL,
    confidence             NUMERIC(6,2) NOT NULL,
    PRIMARY KEY (symbol, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_squeeze_date ON short_squeeze_signals(as_of_date);
CREATE INDEX IF NOT EXISTS idx_squeeze_confidence
    ON short_squeeze_signals(confidence DESC, as_of_date DESC);


CREATE TABLE IF NOT EXISTS reddit_signals (
    symbol                 TEXT NOT NULL,
    as_of_date             DATE NOT NULL,
    total_mentions         INTEGER NOT NULL DEFAULT 0,
    bullish_mentions       INTEGER NOT NULL DEFAULT 0,
    bearish_mentions       INTEGER NOT NULL DEFAULT 0,
    sources                TEXT[] DEFAULT '{}',
    PRIMARY KEY (symbol, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_reddit_signals_date ON reddit_signals(as_of_date);
CREATE INDEX IF NOT EXISTS idx_reddit_signals_mentions
    ON reddit_signals(total_mentions DESC, as_of_date DESC);
