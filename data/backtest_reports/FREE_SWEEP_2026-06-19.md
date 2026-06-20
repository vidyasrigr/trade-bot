# FREE SWEEP — liquid_264 (2026-06-19, Track 3)

Universe: 264 curated liquid names (chain-bank CORE_200 + get_full_universe), read from the persistent equity cache. MTM equity.
Windows: train 2021-07-01..2024-12-31 | wf 2025-01-01..2026-06-30. num_trials=5.

**SURVIVORSHIP-BIASED**: currently-listed names only. All DSRs are upper bounds; every result is capped at SANDBOX (never PASS) until re-tested on a point-in-time universe with delisted names.

| variant | n_tr | n_wf | train DSR | wf DSR | train MTM-DD | wf MTM-DD | verdict |
|---|---|---|---|---|---|---|---|
| momentum lookback=252 | 1612 | 832 | 0.277 | 0.751 | 35% | 8% | SANDBOX (partial) |
| momentum lookback=189 | 1768 | 832 | 0.083 | 0.746 | 58% | 5% | SANDBOX (partial) |
| momentum lookback=126 | 1924 | 832 | 0.678 | 0.332 | 20% | 15% | SANDBOX (survivorship-capped) |
| momentum lookback=63 | 2080 | 832 | 0.485 | 0.202 | 31% | 35% | NO_EDGE |
| lead_lag (top120) | 292 | 232 | 0.026 | 0.040 | 16% | 26% | NO_EDGE |

## Notes
- Only the pure-free generators (momentum, lead_lag) run here; they need no FMP/MarketData.
- pead/insider/short_squeeze run as the FMP bank + disk-readers land; skew is options-bound.
- trend/candles/chart_patterns/support_resistance/risk/volatility_regime have no backtest adapter yet (the ~15-adapter primitive-decomposition build is a later night).
- True 500/1000/2000 breadth needs an ADV-ranked universe (volume ranking); the alphabetical directory head is illiquid junk, so liquid_264 is the honest scale tonight.
