-- 019 — Recommendation lifecycle + calibration/regime/benchmark capture (P0 Stage 2.3/2.4/2.5)
-- Additive only. status is already free text (default 'open'); the lifecycle values
-- (recommended | guarded_warn | rejected | ignored_by_user | stale | paper_opened |
--  paper_closed) are app-enforced, so no enum migration / CHECK is added (would break
-- existing 'open'/'paper_filled' rows). `conviction` already serves as predicted_conviction.

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS predicted_win_prob          NUMERIC;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS actual_outcome              NUMERIC;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS market_regime               TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS stock_regime                TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS spy_return_holding_period   NUMERIC;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS qqq_return_holding_period   NUMERIC;

COMMENT ON COLUMN recommendations.predicted_win_prob IS 'implied success probability at recommendation time (0-1)';
COMMENT ON COLUMN recommendations.actual_outcome IS 'populated at close: realized PnL or +1/-1';
COMMENT ON COLUMN recommendations.market_regime IS 'bull|bear|high_vol|low_vol|trend|range at rec time';
COMMENT ON COLUMN recommendations.stock_regime IS 'per-symbol regime from stock_climate at rec time';

-- 2.5 Calibration view: predicted win-prob decile vs realized win rate.
-- Briefing warns when a decile is >15pp off after >=30 closed trades.
CREATE OR REPLACE VIEW v_calibration_buckets AS
SELECT
    width_bucket(predicted_win_prob, 0, 1, 10)                              AS prob_decile,
    count(*)                                                               AS n,
    round(avg(predicted_win_prob)::numeric, 4)                            AS avg_predicted_prob,
    round(avg(CASE WHEN actual_outcome > 0 THEN 1.0 ELSE 0.0 END)::numeric, 4) AS realized_win_rate,
    round((avg(predicted_win_prob)
           - avg(CASE WHEN actual_outcome > 0 THEN 1.0 ELSE 0.0 END))::numeric, 4) AS calibration_gap
FROM recommendations
WHERE predicted_win_prob IS NOT NULL AND actual_outcome IS NOT NULL
GROUP BY 1
ORDER BY 1;
