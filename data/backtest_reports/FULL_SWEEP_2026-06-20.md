# FULL SWEEP — 2026-06-20 (0619.3 Track B)

Identical methodology across all signals (MTM equity, costs, train/WF, SANDBOX-cap) so verdicts are comparable — the incumbent baseline for the GPT-18 research sweep.
Windows: train 2021-07-01..2024-12-31 | wf 2025-01-01..2026-06-30.
**SURVIVORSHIP-BIASED** (currently-listed names) -> all capped at SANDBOX, DSRs are upper bounds, until a point-in-time universe exists. Labels: CACHE_LIMITED (169-name chain cache), CHAINS_LIMITED (term structure), FUNDAMENTALS_PENDING, *_PENDING = data-gated, NOT no-edge.

| signal | variant | n_tr | n_wf | train DSR | wf DSR | train DD | wf DD | verdict |
|---|---|---|---|---|---|---|---|---|
| momentum_12_1 | mom lb=105 top100 | 692 | 320 | 0.060 | 0.224 | 43% | 24% | NO_EDGE [top100] |
| momentum_12_1 | mom lb=126 top100 | 672 | 320 | 0.209 | 0.175 | 48% | 25% | NO_EDGE [top100] |
| momentum_12_1 | mom lb=147 top100 | 652 | 320 | 0.140 | 0.286 | 54% | 19% | NO_EDGE [top100] |
| momentum_12_1 | mom lb=168 top100 | 632 | 320 | 0.065 | 0.531 | 60% | 14% | SANDBOX(partial) [top100] |
| momentum_12_1 | mom lb=105 top250 | 1136 | 244 | 0.012 | 0.126 | 48% | 0% | NO_EDGE [top250] |
| momentum_12_1 | mom lb=126 top250 | 1136 | 344 | 0.023 | 0.604 | 49% | 8% | SANDBOX(partial) [top250] |
| momentum_12_1 | mom lb=147 top250 | 1040 | 294 | 0.135 | 0.083 | 21% | 7% | NO_EDGE [top250] |
| momentum_12_1 | mom lb=168 top250 | 994 | 342 | 0.105 | 0.024 | 28% | 22% | NO_EDGE [top250] |
| momentum_12_1 | mom lb=105 top500 | 2154 | 652 | 0.023 | 0.120 | 52% | 23% | NO_EDGE [top500] |
| momentum_12_1 | mom lb=126 top500 | 2226 | 770 | 0.024 | 0.336 | 51% | 22% | SANDBOX(partial) [top500] |
| momentum_12_1 | mom lb=147 top500 | 1992 | 672 | 0.206 | 0.067 | 18% | 27% | NO_EDGE [top500] |
| momentum_12_1 | mom lb=168 top500 | 1930 | 770 | 0.099 | 0.010 | 40% | 30% | NO_EDGE [top500] |
| skew_25d | skew hold=21 | 362 | 86 | 0.096 | 0.671 | 36% | 10% | SANDBOX(partial) [CACHE_LIMITED] |
| vrp_z | vrp_z | 362 | 86 | 0.903 | 0.013 | 14% | 63% | SANDBOX(partial) [CACHE_LIMITED] |
| vrp_level | vrp_level | 362 | 86 | 0.903 | 0.013 | 14% | 63% | SANDBOX(partial) [CACHE_LIMITED] |
| iv_call_put_spread | iv_cp_spread | 362 | 86 | 0.114 | 0.654 | 39% | 1% | SANDBOX(partial) [CACHE_LIMITED] |
| iv_term_slope | iv_term_slope | 0 | 12 | - | 0.009 | - | 8% | NO_EDGE [CACHE_LIMITED] |
| rsi_14 | rsi_14 | 3130 | 1189 | 0.504 | 0.011 | 23% | 18% | SANDBOX(partial) [primitive] |
| macd | macd | 3122 | 1189 | 0.014 | 0.009 | 38% | 29% | NO_EDGE [primitive] |
| stoch | stoch | 3129 | 1192 | 0.269 | 0.070 | 22% | 20% | NO_EDGE [primitive] |
| roc_63 | roc_63 | 3115 | 1190 | 0.001 | 0.220 | 46% | 32% | NO_EDGE [primitive] |
| ema_align | ema_align | 2383 | 1183 | 0.000 | 0.052 | 41% | 11% | NO_EDGE [primitive] |
| slope | slope | 3110 | 1188 | 0.000 | 0.286 | 50% | 28% | NO_EDGE [primitive] |
| adx_dir | adx_dir | 3128 | 1188 | 0.000 | 0.171 | 51% | 8% | NO_EDGE [primitive] |
| bb_width | bb_width | 3122 | 1193 | 0.007 | 0.001 | 59% | 70% | NO_EDGE [primitive] |
| atr_pct | atr_pct | 3120 | 1189 | 0.004 | 0.000 | 71% | 77% | NO_EDGE [primitive] |
| rvol | rvol | 3118 | 1187 | 0.004 | 0.000 | 71% | 76% | NO_EDGE [primitive] |
| support_res | support_res | 3119 | 1184 | 0.007 | 0.036 | 52% | 34% | NO_EDGE [primitive] |
| trend | trend(rollup) | 2383 | 1179 | 0.001 | 0.401 | 49% | 21% | SANDBOX(partial) [rollup] |
| risk | risk(rollup) | 3122 | 1189 | 0.012 | 0.002 | 70% | 77% | NO_EDGE [rollup] |
| beat_and_raise_pead | pead hold=10 | 1454 | 620 | 0.542 | 0.378 | 77% | 79% | SANDBOX(DD>25%) [FMP] |
| beat_and_raise_pead | pead hold=5 | 1349 | 596 | 0.061 | 0.244 | 75% | 45% | NO_EDGE [FMP] |
| insider_cluster | insider hold=60 | 6 | 12 | 0.454 | 0.846 | 4% | 37% | SANDBOX(DD>25%) [FMP] |

---

## Incumbent benchmark for the GPT-18 comparison (0619.2)

Across **33 existing-signal variants** tested with identical methodology (MTM, costs, train/WF,
SANDBOX-cap), **ZERO clear the promotion gates** (train DSR>=0.50 AND wf DSR>=0.30 AND wf MTM-DD<25%
AND adequate n). The dominant signature is **regime-dependence / non-stationarity**: signals are
strong in one window and dead in the other, almost never both.

**Strongest incumbents (the bar GPT-18 must beat) — all SANDBOX, with the catch noted:**
| signal | train | wf | wf DD | catch |
|---|---|---|---|---|
| skew_25d | 0.10 | **0.67** | 10% | train-dead (regime); n_wf=86 small |
| iv_call_put_spread | 0.11 | **0.65** | 1% | train-dead; n_wf=86 small |
| momentum_12_1 (126, top250) | 0.02 | 0.60 | 8% | train-dead; not stable across slices |
| trend (rollup) | 0.00 | 0.40 | 21% | train-dead |
| pead hold=10 | **0.54** | 0.38 | 79% | clears both DSR gates but DD disqualifying |
| insider_cluster | 0.45 | **0.85** | 37% | only 6 train / 12 wf trades — too small to trust |

**Reading for the GPT decision:** the incumbents' best honest OOS is ~0.65 wf DSR at low DD from the
options-implied family (skew, iv_call_put_spread) — but train-dead, so regime-gated at best. The only
signals clearing the *train* gate (pead 0.54, insider 0.45, rsi 0.50) all fail on DD, sample, or wf.
So **a GPT-18 signal is "worth incorporating" if it beats ~0.65 wf DSR at <25% DD with a non-dead
train and n>=100** — none of the incumbents do all four. The bar is low because the incumbents are
weak; the value is a *stable* edge, which none here is.

## Honest corrections + labels
- **Momentum reversal:** last night's "lookback=126 clears all gates on liquid_264" does NOT replicate
  on the ADV-ranked slices or across the neighborhood {105,126,147,168} x {100,250,500}. Train DSR is
  dead (~0.02-0.21) everywhere; it was a universe-composition artifact. Why the runbook mandates the
  whole neighborhood.
- **Primitive decomposition:** no single primitive (RSI/MACD/Stoch/ROC/EMA/slope/ADX/BB/ATR/RVol)
  carries robust edge; best is slope/roc (wf ~0.22-0.29, train-dead). The momentum "edge" is fragile.
- **vrp_z/vrp_level:** train 0.90 / wf 0.01 / 63% DD — classic overfit, not an edge.
- **CACHE_LIMITED:** options signals on the 169-name chain cache (n_wf~86). iv_term_slope CHAINS_LIMITED
  (n_tr=0 — term structure needs 2 expiries/date, only dense for original names).
- **FUNDAMENTALS_PENDING:** `fundamental` + quality factors not run — income/balance/cashflow only just
  prioritized in the FMP daemon (banking overnight). Adapter wiring is next; NOT no-edge.
- **short_squeeze:** PENDING — free exchange short-interest CSV ingester not built tonight (the one
  genuine remaining data gap; FMP short-interest is 404 on Starter).
- Everything SANDBOX-capped (survivorship) until a PIT universe exists.
