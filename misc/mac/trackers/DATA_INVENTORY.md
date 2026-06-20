DATA INVENTORY  -  generated 2026-06-19 19:32
===============================================================================================
MarketData chains: 51 symbols banked   |   FMP calls cached: 1069   |   FRED series: 11
MarketData credits today: see phase4_bank.json
===============================================================================================

SOURCE      DATASET               SYMBOLS   COVERAGE(core-200)    NOTE
-----------------------------------------------------------------------------------------------
MarketData  option chains         51        ███░░░░░░░   26%      5y rolling, no hist greeks
yfinance    daily OHLCV (feat)    0         (live, keyless)       backfill daemon
FRED        macro series          11        ████░░░░░░   37%      target 30+
FMP         earnings              1061      (no daily cap, 300/min)
FMP         grades                2         (no daily cap, 300/min)
FMP         income                3         (no daily cap, 300/min)
FMP         profile               3         (no daily cap, 300/min)

NOTES
- FMP ratios/key_metrics/analyst_est are ANNUAL on Starter (quarterly is premium).
  Fine for slow-moving fundamental scoring; granularity flagged if a signal underperforms.
- FMP short-interest = 404 on Starter; squeeze sourced from free exchange CSV (Track 4a).
- ETFs excluded from the listed-universe parse; options core-200 lists ETFs explicitly.
