DATA INVENTORY  -  generated 2026-06-19 20:30
===============================================================================================
MarketData chains: 70 symbols banked   |   FMP calls cached: 13210   |   FRED series: 33
MarketData credits today: see phase4_bank.json
===============================================================================================

SOURCE      DATASET               SYMBOLS   COVERAGE(core-200)    NOTE
-----------------------------------------------------------------------------------------------
MarketData  option chains         70        ████░░░░░░   35%      5y rolling, no hist greeks
yfinance    daily OHLCV (feat)    264       (live, keyless)       backfill daemon
FRED        macro series          33        ██████████  100%      target 30+
FMP         earnings              5835      (no daily cap, 300/min)
FMP         grades                2         (no daily cap, 300/min)
FMP         income                3         (no daily cap, 300/min)
FMP         insider               5888      (no daily cap, 300/min)
FMP         profile               1482      (no daily cap, 300/min)

NOTES
- FMP ratios/key_metrics/analyst_est are ANNUAL on Starter (quarterly is premium).
  Fine for slow-moving fundamental scoring; granularity flagged if a signal underperforms.
- FMP short-interest = 404 on Starter; squeeze sourced from free exchange CSV (Track 4a).
- ETFs excluded from the listed-universe parse; options core-200 lists ETFs explicitly.
