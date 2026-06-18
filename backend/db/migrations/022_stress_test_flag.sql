-- 022 — synthetic-2020 stress test result (P0 Stage 3.4)
-- A short-vol signal may not advance sandbox -> paper until it survives the
-- synthetic COVID path (backtest/stress_test.py). This stores the verdict.

ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS stress_test_passed BOOLEAN;
COMMENT ON COLUMN backtest_runs.stress_test_passed IS
    'synthetic Feb-Mar 2020 (SPY -34%, VIX 12->82) survival: max DD < 40% of margin AND no margin call';
