"""0620.3 Phase 5d — extended-history (2010-2026) regime sweep. Reuses the full Phase 3
battery (regime_sweep) with deep windows so each regime type recurs (multiple instances),
enabling real leave-one-instance-out. Equity-only (no deep option chains). THE make-or-break
test: do signals recur as regime edges across 2010-2026, or were they recent-window noise?"""
import asyncio
from datetime import date
import scripts.regime_sweep as rs

rs.TRAIN = (date(2010, 1, 1), date(2019, 12, 31))
rs.WF = (date(2020, 1, 1), date(2026, 6, 18))
rs.TRAIN_SELECT = (date(2010, 1, 1), date(2016, 12, 31))
rs.TRAIN_VALIDATE = (date(2017, 1, 1), date(2019, 12, 31))
rs.OUT_BASE = "REGIME_SWEEP_2010_2026"
rs.EQUITY_ONLY = True

if __name__ == "__main__":
    asyncio.run(rs.run())
