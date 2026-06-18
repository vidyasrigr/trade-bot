-- 021 — per-leg paper trade representation (P0 Stage 4.2)
-- Single strike/price can't represent strangles/condors/spreads; PnL sign flips
-- for credit structures. Store the full leg array so multi-leg PnL is correct.

ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS legs JSONB;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS strategy_type TEXT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS recommendation_id BIGINT;

COMMENT ON COLUMN paper_trades.legs IS
    'array of {strike, expiry, right, qty, entry_fill, exit_fill} for multi-leg structures';
COMMENT ON COLUMN paper_trades.strategy_type IS
    'naked_strangle | iron_condor | vertical | single | ... — drives PnL sign/aggregation';
COMMENT ON COLUMN paper_trades.recommendation_id IS
    'FK-ish link to recommendations.id — every paper trade must originate from a logged rec';
