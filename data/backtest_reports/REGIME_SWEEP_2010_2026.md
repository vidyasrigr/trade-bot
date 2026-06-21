# REGIME SWEEP — 2026-06-20 (0620.2 Phase 3)

git_sha 53d1caf. num_trials=105 (program-wide multiple-testing deflation). True account DD via Phase 2.0 daily-MTM simulator. SPY wf CAGR 15%, QQQ 22%.
Both bars; D2 regime-stratified + D3 live-gate (allowed regimes chosen on train_select, verified on train_validate, never on WF). SANDBOX/SURVIVORSHIP-capped until PIT.

| signal | class | train DSR | wf DSR | acct DD | n_wf | win% | excess_SPY | theme | D3 gated_n/occ | label |
|---|---|---|---|---|---|---|---|---|---|---|
| momentum_12_1 | EQUITY | 0.004 | 0.003 | 76% | 2754 | 50% | -28% | YES | 330/0 | INSUFFICIENT_REGIME_INSTANCES |
| rsi_14 | EQUITY | 0.006 | 0.002 | 35% | 6700 | 49% | -14% | YES | 4181/2 | INSUFFICIENT_REGIME_INSTANCES |
| macd | EQUITY | 0.000 | 0.029 | 59% | 6697 | 49% | -21% | - | 0/None | NO_EDGE |
| stoch | EQUITY | 0.001 | 0.011 | 41% | 6692 | 50% | -11% | YES | 3320/2 | INSUFFICIENT_REGIME_INSTANCES |
| roc_63 | EQUITY | 0.003 | 0.004 | 74% | 6699 | 50% | -25% | YES | 1137/0 | INSUFFICIENT_REGIME_INSTANCES |
| ema_align | EQUITY | 0.000 | 0.000 | 56% | 6594 | 50% | -24% | YES | 0/None | NO_EDGE |
| slope | EQUITY | 0.003 | 0.002 | 74% | 6697 | 49% | -27% | - | 1138/0 | INSUFFICIENT_REGIME_INSTANCES |
| adx_dir | EQUITY | 0.000 | 0.008 | 64% | 6700 | 50% | -21% | - | 2065/3 | REGIME_SUSPECT |
| bb_width | EQUITY | 0.000 | 0.000 | 94% | 6693 | 50% | -44% | YES | 0/None | NO_EDGE |
| atr_pct | EQUITY | 0.000 | 0.000 | 96% | 6692 | 50% | -50% | YES | 460/0 | INSUFFICIENT_REGIME_INSTANCES |
| rvol | EQUITY | 0.000 | 0.000 | 96% | 6695 | 50% | -49% | YES | 460/0 | INSUFFICIENT_REGIME_INSTANCES |
| support_res | EQUITY | 0.000 | 0.002 | 71% | 6700 | 52% | -22% | YES | 0/None | NO_EDGE |
| trend | EQUITY | 0.003 | 0.004 | 74% | 6599 | 50% | -24% | - | 0/None | NO_EDGE |
| risk | EQUITY | 0.000 | 0.000 | 96% | 6692 | 50% | -49% | YES | 0/None | NO_EDGE |
| beat_and_raise_pead | FMP | 0.338 | 0.119 | 46% | 3715 | 54% | -12% | YES | 2006/2 | INSUFFICIENT_REGIME_INSTANCES |
| insider_cluster | FMP | - | 0.017 | 47% | 14 | 36% | -39% | YES | 0/None | SMALL_N |
| short_squeeze_bearish | SI | - | 0.044 | 29% | 8292 | 51% | -14% | YES | 0/None | NO_EDGE |
| squeeze_candidate | SI | - | 0.000 | 65% | 2286 | 50% | -35% | YES | 0/None | NO_EDGE |
| residual_momentum | RESEARCH:EQUITY | 0.047 | 0.110 | 45% | 6390 | 51% | -8% | YES | 3982/2 | INSUFFICIENT_REGIME_INSTANCES |
| high_52w_proximity | RESEARCH:EQUITY | 0.000 | 0.000 | 79% | 6378 | 52% | -32% | YES | 0/None | NO_EDGE |
| time_series_momentum | RESEARCH:EQUITY | 0.009 | 0.018 | 58% | 6567 | 51% | -14% | - | 854/0 | INSUFFICIENT_REGIME_INSTANCES |
| short_term_reversal | RESEARCH:EQUITY | 0.076 | 0.000 | 36% | 6501 | 50% | -17% | YES | 4036/2 | NO_EDGE |
| long_term_reversal | RESEARCH:EQUITY | 0.000 | 0.085 | 37% | 6085 | 50% | -5% | - | 1486/3 | REGIME_SUSPECT |
| idiosyncratic_vol | RESEARCH:EQUITY | 0.000 | 0.000 | 96% | 6590 | 51% | -51% | YES | 0/None | NO_EDGE |
| max_lottery_avoid | RESEARCH:EQUITY | 0.000 | 0.000 | 88% | 6498 | 50% | -39% | YES | 0/None | NO_EDGE |
| vol_contraction_breakout | RESEARCH:EQUITY | 0.000 | 0.000 | 56% | 6678 | 48% | -26% | YES | 0/None | NO_EDGE |
| betting_against_beta | RESEARCH:EQUITY | 0.000 | 0.000 | 96% | 6556 | 49% | -51% | YES | 0/None | NO_EDGE |
| volume_confirmed_momentum | RESEARCH:EQUITY | 0.003 | 0.020 | 49% | 6454 | 50% | -17% | - | 821/0 | NO_EDGE |
| revenue_surprise_drift | RESEARCH:FMP_EARNINGS | 0.033 | 0.000 | 43% | 4499 | 51% | -19% | - | 576/0 | NO_EDGE |
| earnings_announcement_premium | RESEARCH:FMP_EARNINGS | 0.979 | 0.665 | 30% | 4943 | 58% | 15% | YES | 4764/5 | INSUFFICIENT_REGIME_INSTANCES |
| accruals | RESEARCH:FMP_STATEMENT | - | 0.000 | 78% | 3199 | 49% | -49% | YES | 0/None | DATA_GATED |
| piotroski_fscore | RESEARCH:FMP_STATEMENT | - | 0.000 | 87% | 3230 | 50% | -56% | YES | 0/None | DATA_GATED |
| net_payout_yield | RESEARCH:FMP_STATEMENT | 0.010 | 0.000 | 80% | 5254 | 52% | -39% | YES | 0/None | DATA_GATED |
| net_operating_assets | RESEARCH:FMP_STATEMENT | 0.000 | 0.000 | 45% | 6539 | 51% | -22% | YES | 0/None | DATA_GATED |
| distress_risk_avoid | RESEARCH:FMP_STATEMENT | - | 0.000 | 51% | 4145 | 48% | -25% | YES | 0/None | DATA_GATED |

---

## MAKE-OR-BREAK VERDICT (extended history 2010-2026, equity + research + FMP + SI)

**The extended history did its job:** regime occurrences now reach **3-5 per signal** (vs exactly 1 in
the 2021-2026 window), so leave-one-instance-out regime validation is finally *possible*. This was the
whole point of Phase 5b/5c — and it worked. Train 2010-2019, WF 2020-2026 (spanning COVID-2020,
2021 mania, 2022 bear, 2023-26 bull = multiple distinct regime episodes).

**The answer the test gives: NO signal clears the regime-conditional bar.**
Labels (35 signals): 16 NO_EDGE, 11 INSUFFICIENT_REGIME_INSTANCES, 2 REGIME_SUSPECT, 1 SMALL_N,
5 DATA_GATED. **Zero UNCONDITIONAL_CANDIDATE, zero REGIME_CONDITIONAL_CANDIDATE.**

What this means: the recent-window "leads" (momentum, skew, the 2025-26 standouts) were **recent-window
noise** — they do NOT recur as robust, low-DD, multi-instance regime edges across 16 years.

### The closest, and why each fails
- **earnings_announcement_premium** — the standout: train DSR 0.98, wf 0.67, 30% DD, and **5 regime
  occurrences**. BUT flagged INSUFFICIENT_REGIME_INSTANCES because one episode contributes >50% of the
  gated trades — the integrity gate correctly refuses to call it proven across independent instances.
  This is the single most interesting lead for deeper, dedicated study.
- **adx_dir, long_term_reversal** — REGIME_SUSPECT: they recur across 3 instances and aren't theme bets,
  but carry 64% / 37% true account DD — undeployable. Positive gated return, but not an investable edge.
- **momentum_12_1** — NO_EDGE / theme bet over 2010-2026: train 0.004, wf 0.003, 76% account DD. The
  2025-26 strength does not generalize; over 16 years momentum long-short is a high-DD non-edge here.

### Methodology that made this honest
- True daily-account DD (Phase 2.0) — most signals show 40-96% account DD once overlapping positions
  are marked daily; cohort DD badly understated this.
- Multiple-testing deflation (num_trials=105) + train_select/train_validate regime selection (no WF peek).
- Regime-instance integrity (>=3 occurrences, no episode >50%) — the gate that separates a real
  regime edge from one lucky episode.
- Causal regime_state rebuilt on 2010-2026 (fit train-only, forward-filtered, no-look-ahead test green).

### Honest caveats
- SURVIVORSHIP: this runs on today's survivors back-extended to 2010 (PIT/delisted = Phase 5a, deferred);
  survivorship inflates results, so the true picture is if anything WORSE, not better — it does not
  rescue any signal. All results stay capped pending PIT.
- FMP statement factors DATA_GATED (deep fundamentals not banked); options signals excluded (5y chain cap).
