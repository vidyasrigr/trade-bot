DATA INVENTORY  -  generated 2026-06-20 17:27
===============================================================================================
MarketData chains: 170 symbols banked   |   FMP calls cached: 60461   |   FRED series: 33
MarketData credits today: see phase4_bank.json
===============================================================================================

SOURCE      DATASET               SYMBOLS   COVERAGE(core-200)    NOTE
-----------------------------------------------------------------------------------------------
MarketData  option chains         170       ████████░░   85%      5y rolling, no hist greeks
yfinance    daily OHLCV (feat)    541       (live, keyless)       backfill daemon
FRED        macro series          33        ██████████  100%      target 30+
FMP         earnings              5836      (no daily cap, 300/min)
FMP         float                 6800      (no daily cap, 300/min)
FMP         grades                5058      (no daily cap, 300/min)
FMP         income                6396      (no daily cap, 300/min)
FMP         insider               5888      (no daily cap, 300/min)
FMP         key_metrics           6458      (no daily cap, 300/min)annual-fundamentals
FMP         news                  6908      (no daily cap, 300/min)
FMP         price_target          3841      (no daily cap, 300/min)
FMP         profile               6818      (no daily cap, 300/min)
FMP         ratios                6458      (no daily cap, 300/min)annual-fundamentals

NOTES
- FMP ratios/key_metrics/analyst_est are ANNUAL on Starter (quarterly is premium).
  Fine for slow-moving fundamental scoring; granularity flagged if a signal underperforms.
- FMP short-interest = 404 on Starter; squeeze sourced from free exchange CSV (Track 4a).
- ETFs excluded from the listed-universe parse; options core-200 lists ETFs explicitly.
