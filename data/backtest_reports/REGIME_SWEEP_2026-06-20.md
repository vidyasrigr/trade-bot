# REGIME SWEEP — 2026-06-20 (0620.2 Phase 3)

git_sha d6c9dbf. num_trials=117 (program-wide multiple-testing deflation). True account DD via Phase 2.0 daily-MTM simulator. SPY wf CAGR 19%, QQQ 30%.
Both bars; D2 regime-stratified + D3 live-gate (allowed regimes chosen on train_select, verified on train_validate, never on WF). SANDBOX/SURVIVORSHIP-capped until PIT.

| signal | class | train DSR | wf DSR | acct DD | n_wf | win% | excess_SPY | theme | D3 gated_n/occ | label |
|---|---|---|---|---|---|---|---|---|---|---|
| momentum_12_1 | EQUITY | 0.002 | 0.256 | 19% | 344 | 52% | 17% | - | 0/None | NO_EDGE |
| rsi_14 | EQUITY | 0.170 | 0.001 | 18% | 1189 | 49% | -21% | - | 799/1 | NO_EDGE |
| macd | EQUITY | 0.001 | 0.000 | 25% | 1189 | 50% | -28% | - | 0/None | NO_EDGE |
| stoch | EQUITY | 0.057 | 0.007 | 22% | 1192 | 48% | -23% | - | 799/1 | NO_EDGE |
| roc_63 | EQUITY | 0.000 | 0.041 | 23% | 1190 | 51% | -14% | YES | 0/None | NO_EDGE |
| ema_align | EQUITY | 0.000 | 0.005 | 13% | 1183 | 48% | -26% | - | 0/None | NO_EDGE |
| slope | EQUITY | 0.000 | 0.063 | 21% | 1188 | 51% | -10% | YES | 0/None | NO_EDGE |
| adx_dir | EQUITY | 0.000 | 0.028 | 16% | 1188 | 51% | -20% | YES | 0/None | NO_EDGE |
| bb_width | EQUITY | 0.000 | 0.000 | 43% | 1193 | 47% | -48% | YES | 0/None | NO_EDGE |
| atr_pct | EQUITY | 0.000 | 0.000 | 53% | 1189 | 45% | -56% | YES | 0/None | NO_EDGE |
| rvol | EQUITY | 0.000 | 0.000 | 51% | 1187 | 46% | -57% | YES | 0/None | NO_EDGE |
| support_res | EQUITY | 0.000 | 0.003 | 24% | 1184 | 50% | -24% | - | 0/None | NO_EDGE |
| trend | EQUITY | 0.000 | 0.050 | 20% | 1179 | 49% | -21% | - | 0/None | NO_EDGE |
| risk | EQUITY | 0.000 | 0.000 | 49% | 1189 | 47% | -53% | YES | 0/None | NO_EDGE |
| skew_25d | OPTIONS | 0.008 | 0.247 | 13% | 86 | 47% | 119% | YES | 0/None | NO_EDGE |
| vrp_z | OPTIONS | 0.570 | 0.000 | 45% | 86 | 58% | -58% | YES | 48/1 | NO_EDGE |
| iv_call_put_spread | OPTIONS | 0.010 | 0.233 | 15% | 86 | 49% | 30% | - | 48/1 | NO_EDGE |
| beat_and_raise_pead | FMP | 0.077 | 0.033 | 15% | 620 | 55% | -6% | - | 450/1 | INSUFFICIENT_REGIME_INSTANCES |
| insider_cluster | FMP | 0.050 | 0.303 | 33% | 12 | 67% | 35% | YES | 9/1 | SMALL_N |
| short_squeeze_bearish | SI | 0.001 | 0.048 | 8% | 1792 | 51% | -13% | - | 0/None | NO_EDGE |
| squeeze_candidate | SI | 0.000 | 0.016 | 15% | 341 | 53% | -6% | YES | 0/None | NO_EDGE |
| residual_momentum | RESEARCH:EQUITY | 0.030 | 0.096 | 14% | 1165 | 51% | -18% | - | 0/None | NO_EDGE |
| high_52w_proximity | RESEARCH:EQUITY | 0.000 | 0.001 | 24% | 1162 | 50% | -33% | - | 0/None | NO_EDGE |
| time_series_momentum | RESEARCH:EQUITY | 0.001 | 0.050 | 18% | 1177 | 51% | -18% | - | 0/None | NO_EDGE |
| short_term_reversal | RESEARCH:EQUITY | 0.073 | 0.000 | 22% | 1177 | 47% | -20% | - | 0/None | NO_EDGE |
| long_term_reversal | RESEARCH:EQUITY | 0.174 | 0.016 | 10% | 1134 | 51% | -12% | - | 0/None | NO_EDGE |
| idiosyncratic_vol | RESEARCH:EQUITY | 0.000 | 0.000 | 49% | 1179 | 47% | -52% | YES | 0/None | NO_EDGE |
| max_lottery_avoid | RESEARCH:EQUITY | 0.012 | 0.000 | 42% | 1174 | 46% | -49% | YES | 0/None | NO_EDGE |
| vol_contraction_breakout | RESEARCH:EQUITY | 0.000 | 0.000 | 21% | 1189 | 47% | -33% | - | 0/None | NO_EDGE |
| betting_against_beta | RESEARCH:EQUITY | 0.000 | 0.000 | 43% | 1177 | 49% | -45% | YES | 0/None | NO_EDGE |
| volume_confirmed_momentum | RESEARCH:EQUITY | 0.156 | 0.008 | 22% | 1179 | 49% | -23% | - | 0/None | NO_EDGE |
| revenue_surprise_drift | RESEARCH:FMP_EARNINGS | 0.000 | 0.001 | 20% | 785 | 48% | -22% | YES | 0/None | NO_EDGE |
| earnings_announcement_premium | RESEARCH:FMP_EARNINGS | 0.222 | 0.560 | 12% | 835 | 51% | 13% | - | 619/1 | INSUFFICIENT_REGIME_INSTANCES |
| accruals | RESEARCH:FMP_STATEMENT | - | - | - | 0 | - | - | - | 0/None | DATA_GATED |
| piotroski_fscore | RESEARCH:FMP_STATEMENT | - | - | - | 0 | - | - | - | 0/None | DATA_GATED |
| net_payout_yield | RESEARCH:FMP_STATEMENT | - | - | - | 0 | - | - | - | 0/None | DATA_GATED |
| net_operating_assets | RESEARCH:FMP_STATEMENT | - | - | - | 0 | - | - | - | 0/None | DATA_GATED |
| distress_risk_avoid | RESEARCH:FMP_STATEMENT | - | - | - | 0 | - | - | - | 0/None | DATA_GATED |
| rv_minus_iv | RESEARCH:OPTIONS | 0.570 | 0.000 | 45% | 86 | 58% | -58% | YES | 48/1 | NO_EDGE |

---

## Headline — nothing clears either bar (39 signals, full battery)

Under the complete Phase 3 battery — TRUE account DD (daily-MTM simulator), multiple-testing
deflation (num_trials=117 program-wide), both bars, and D1/D2/D3 — **ZERO signals clear the
unconditional OR the regime-conditional bar.** Distribution: 31 NO_EDGE, 2
INSUFFICIENT_REGIME_INSTANCES, 1 SMALL_N, 5 DATA_GATED (FMP quality factors — balance/cash-flow
still banking).

## The two closest (flagged, NOT candidates)
- **earnings_announcement_premium** — wf DSR 0.56 @ 12% true acct DD, but train-dead (0.22) so it
  FAILS the unconditional bar; and D3 found only **1 WF regime occurrence** -> INSUFFICIENT_REGIME_INSTANCES.
  A real lead to re-test on a longer/PIT sample, but not a candidate now.
- **beat_and_raise_pead** — same shape, INSUFFICIENT_REGIME_INSTANCES.

## KEY STRUCTURAL FINDING (for V)
The WF window (2025-01..2026-06, ~18mo) is essentially **one regime episode** — every D3 test
returns `wf_occurrences=1`. So a regime-conditional edge is **unprovable on this WF by construction**
(GPT's regime-instance integrity correctly blocks one-episode "proof"). Regime-conditional validation
needs either a longer WF or the PIT rebuild (Session 3) that surfaces more regime variety. This is the
single biggest limiter on producing a REGIME_CONDITIONAL_CANDIDATE right now.

## Momentum survivorship/theme cross-check (highest-priority test) — RESOLVED
momentum_12_1: wf DSR 0.256, true acct DD 19%, **theme_bet = FALSE (top-cluster share 0.27 < 0.40)**,
excess vs SPY +17pts. Resolution: the 2025-26 momentum performance is **NOT the AI-beta artifact**
GPT feared (only 27% of PnL from one emergent cluster, broad-based), so the earlier "momentum thriving"
is real broad outperformance — BUT it still does not clear the gate (train-dead 0.02, deflated wf 0.256
< 0.30) and carries a 19% account DD. Verdict: real-ish broad factor return, regime-dependent, not a
theme bet, not promotable. The contradiction is resolved: not fake (not theme), but not an edge either.

## Methodology notes
- True account DD (Phase 2.0) is materially higher than the old cohort DD (e.g. momentum 19-61%
  depending on hold overlap) — this is the honest number all DD verdicts now use.
- num_trials=117 deflation is program-wide (incumbents + GPT-18 + 0619.3 neighborhoods) — brutal but
  correct; it is why marginal WF DSRs collapse below the 0.30 gate.
- Everything SURVIVORSHIP-capped until the PIT universe (Session 3). FMP quality factors DATA_GATED.
- Machine-readable: REGIME_SWEEP_2026-06-20.json (+ .csv) carry the full per-row schema + git_sha.
