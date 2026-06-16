-- Migration 007: Real backtest run results
-- Run after 006_users_auth.sql

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    strategy        TEXT NOT NULL,            -- e.g. 'short_strangle_45dte', 'pead_call_spread'
    symbol          TEXT NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    num_trades      INTEGER NOT NULL DEFAULT 0,
    win_rate        NUMERIC(6,4),
    total_pnl       NUMERIC(14,2),
    sharpe          NUMERIC(8,4),
    deflated_sharpe NUMERIC(8,4),             -- Bailey & López de Prado (2014)
    max_drawdown    NUMERIC(8,4),
    params          JSONB DEFAULT '{}',       -- slippage, commissions, num_trials, signal config
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs(strategy);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_symbol ON backtest_runs(symbol);
