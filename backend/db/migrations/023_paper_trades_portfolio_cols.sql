-- 023 — paper_trades columns the portfolio risk + circuit breaker need (smoke-test findings)
-- portfolio_greeks queries pt.stream; circuit_breaker sums unrealized_pnl; both were missing
-- and degraded to empty. Also make expiry nullable so placeholder expiries (e.g. "~21-45 DTE"
-- that don't parse to a date) don't violate NOT NULL on insert.

ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS stream         TEXT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS unrealized_pnl NUMERIC;
ALTER TABLE paper_trades ALTER COLUMN expiry DROP NOT NULL;

COMMENT ON COLUMN paper_trades.stream IS 'options|swing|long_term — drives per-stream capital/greeks limits';
COMMENT ON COLUMN paper_trades.unrealized_pnl IS 'daily mark-to-market unrealized PnL for open positions (circuit breaker)';
