# PC Opus journal — 0620.2 SESSION 2 (Results: daily MTM + GPT-18 + full regime re-test)

Owner: PC Opus. Decision-maker: V. Scope: Session 2 (Phases 2.0-3), STOP at checkpoint.
Standing rules honored: nothing promoted, signal_registry untouched, research isolated in
backend/research/, SANDBOX/survivorship-cap, causal regime only, pre-registered regime selection
(train_select/train_validate, never WF), no emojis, pytest green.

---

## PHASE 2.0 — true daily-portfolio MTM simulator (`backtest/portfolio_mtm.py`)
Daily account over OVERLAPPING cohorts: daily marks, equal-capital across open cohorts, round-trip
costs, turnover, max concurrent cohorts, gross exposure, sector concentration, drawdown by actual
account day. Immediately proved GPT amendment B: momentum-126 true account DD = 61% (hold-overlap
dependent) vs the old cohort DD ~15% — the daily path reveals the real risk. Phase 3 grades all DD
on this simulator.

## PHASE 2 — GPT-18 adapters (research namespace, ISOLATED; signal_registry untouched)
- `research/signals/gpt18_equity.py` — 10 equity adapters (residual_momentum, high_52w_proximity,
  time_series_momentum, short/long_term_reversal, idiosyncratic_vol, max_lottery_avoid,
  vol_contraction_breakout, betting_against_beta, volume_confirmed_momentum) with the runbook cautions
  (PIT rolling betas, min-price filters on reversals, 2-condition+volume on breakout, inverse-vol TSMOM,
  solvency proxy on LT reversal). All validated (residual_momentum strongest pre-battery).
- `research/signals/gpt18_fmp.py` — 7 FMP adapters with the **available_at <= trade_date** look-ahead
  guard (GPT amendment F): earnings signals use announcement date; statements use filingDate
  (fallback period_end+90d). earnings 2 testable; statement 5 (accruals, piotroski, net_payout_yield,
  net_operating_assets, distress_risk) DATA_GATED until balance/cash-flow bank.
- `rv_minus_iv` (Goyal-Saretto) added to options_xs (CACHE_LIMITED).
- `research/signals/research_registry.py` — 18 research signals. De-dup: rvol + iv_term_slope skipped
  (already NO_EDGE). Skipped statement factors return [] -> FUNDAMENTALS_PENDING (verified).

## PHASE 3 — full regime re-test (`scripts/regime_sweep.py`) — 39 signals, ONE comparable harness
Per signal: cohort train/wf DSR + TRUE account DD (Phase 2.0) + win/expectancy/profit_factor/turnover
+ D2 regime-stratified + D3 live-gate (allowed regimes chosen on train_select, verified on
train_validate, never WF) + THEME_BET + benchmark excess vs SPY/QQQ + multiple-testing deflation
(num_trials=117 program-wide). Full label taxonomy. Output REGIME_SWEEP_2026-06-20 .md/.json/.csv with
git_sha + per-row schema (tracker reads the JSON, never markdown).

### HEADLINE: ZERO signals clear either bar
31 NO_EDGE, 2 INSUFFICIENT_REGIME_INSTANCES, 1 SMALL_N, 5 DATA_GATED. No UNCONDITIONAL_CANDIDATE,
no REGIME_CONDITIONAL_CANDIDATE.
- Two closest, FLAGGED not candidates: **earnings_announcement_premium** (wf DSR 0.56 @ 12% acct DD but
  train-dead 0.22 -> fails unconditional; D3 only 1 WF regime occurrence -> INSUFFICIENT_REGIME_INSTANCES)
  and **beat_and_raise_pead** (same shape). Real leads to re-test on a longer/PIT sample.

### KEY STRUCTURAL FINDING (for V)
The WF window (2025-01..2026-06) is ~ONE regime episode — every D3 test returns wf_occurrences=1. So a
regime-conditional edge is **unprovable on this WF by construction** (GPT's regime-instance integrity
correctly refuses one-episode proof). Producing a REGIME_CONDITIONAL_CANDIDATE needs a longer WF or the
PIT rebuild (Session 3) that surfaces more regime variety.

### Momentum cross-check (highest priority) — RESOLVED
momentum_12_1: wf DSR 0.256, true acct DD 19%, **theme_bet=FALSE (top-cluster share 0.27<0.40)**, excess
vs SPY +17pts. NOT the AI-beta artifact GPT feared (broad-based, not one cluster) — so the "momentum
thriving in 2025-26" is real broad outperformance, BUT still doesn't clear the gate (train-dead, deflated
wf<0.30, 19% DD) and is regime-dependent. Resolved: not fake, but not a promotable edge.

## SESSION 2 CHECKPOINT
- [x] Phase 2.0 daily-portfolio MTM simulator built; Phase 3 used it for ALL equity DD verdicts
- [x] Phase 2 all GPT-18 adapters wired w/ cautions; FMP gated on available_at<=trade_date; statement
      factors DATA_GATED (balance/cash-flow still banking), earnings + equity tested
- [x] Phase 3 REGIME_SWEEP .md+.json+.csv complete — 39 signals, both bars, D1/D2/D3, multiple-testing
      deflation, full label taxonomy, win_rate+expectancy, benchmark-relative, git_sha schema
- [x] Momentum survivorship/theme cross-check RESOLVED (broad outperformance, NOT theme bet, not promotable)
- [x] Candidates flagged for V: NONE clear; closest = earnings_announcement_premium + pead (blocked by
      single-WF-regime-episode) -> re-test after PIT / longer WF
- [x] pytest 96/96; nothing promoted; daemons running
- Stopping point: end of Phase 3. Session 3 (Phases 4-5: pre-paper safety stack + PIT universe) NOT
  started, per the hard stop. Awaiting V verification.

DAEMONS: FMP (banking balance/cash-flow + analyst overnight; had died once, relaunched), chain-bank
(ADV work-list, poison-safe). NOTE: daemons have died between sessions a few times (process-group
cleanup); worth a systemd/supervisor wrapper — flagged for V, not blocking.
