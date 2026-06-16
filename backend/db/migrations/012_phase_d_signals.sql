-- Migration 012: Phase D signal tables
-- Run after 011_signal_ranks.sql

-- ============================================================
-- Insider opportunistic-buy clusters (Cohen-Malloy-Pomorski 2012)
-- ============================================================

CREATE TABLE IF NOT EXISTS insider_signals (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    cluster_date    DATE NOT NULL,             -- last opportunistic buy in the cluster
    n_opportunistic INTEGER NOT NULL,          -- buys classified as non-routine
    n_distinct      INTEGER NOT NULL,          -- distinct insiders within the cluster
    total_value     NUMERIC(16,2),             -- approx dollar value of cluster
    insiders        TEXT[] DEFAULT '{}',       -- names
    confidence      NUMERIC(5,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, cluster_date)
);

CREATE INDEX IF NOT EXISTS idx_insider_signals_symbol ON insider_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_insider_signals_date ON insider_signals(cluster_date);

-- ============================================================
-- Supply-chain lead-lag graph (data-driven replacement for HYPERSCALER_LAG)
-- ============================================================

CREATE TABLE IF NOT EXISTS lead_lag_edges (
    leader          TEXT NOT NULL,             -- when this stock moves...
    follower        TEXT NOT NULL,             -- ...this one tends to follow
    lag_days        SMALLINT NOT NULL,         -- median lag from regression
    correlation     NUMERIC(6,4) NOT NULL,     -- lagged Pearson at lag_days
    sample_size     INTEGER NOT NULL,          -- bars used in fit
    computed_on     DATE NOT NULL,
    PRIMARY KEY (leader, follower, computed_on)
);

CREATE INDEX IF NOT EXISTS idx_lead_lag_leader ON lead_lag_edges(leader, computed_on);
CREATE INDEX IF NOT EXISTS idx_lead_lag_follower ON lead_lag_edges(follower, computed_on);
