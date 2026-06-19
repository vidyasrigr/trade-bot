# Journal 2026-06-18 PM (PC Opus) — NEXT_RUNBOOK execution leg

Owner: PC Opus. Goal: complete ALL of NEXT_RUNBOOK_2026-06-18.md toward a profitable,
robust system. Decision-maker for promotion/capital/budget/tier: V.

## Recap of this leg before NEXT_RUNBOOK phases
- Anthropic made OPTIONAL: key in .env was INVALID (401). hooks.py now routes ALL LLM
  calls to Ollama (qwen3.5:9b) on empty-or-invalid key (flips _anthropic_disabled on first
  401). cross_stock_context + postmortem rerouted through hooks. Pipeline runs at $0. Committed.
- Phase 0 LIVE HTTP SMOKE TEST: PASSED 9/9. Booted app; /health 200; landed recommendation_id
  via the real agent pipeline (all Ollama); paper-open 200; bogus->404; earnings-in-DTE->409 +
  rec stale. 6 latent bugs surfaced+fixed (numpy-json, two ::jsonb binds, non-numeric strike,
  expiry str->DATE, invalid-key fallback). pytest 94/94. Committed/pushed (0fe6648).
- Non-blocking findings to address this leg: paper_trades missing 'stream'/'unrealized_pnl'
  cols; options_selection LIVE chain fetch 500s; FRED macro pulls failing (Phase 2 fixes).

## NEXT_RUNBOOK phases — starting now

## [22:15] Phase 1 LAUNCHED — MTM re-validation sweep
run_full_validation --vrp-universe full (40-name, now cached) --concurrency 3. Produces
MASTER_REPORT with MTM drawdowns for all variants. Running.

## [22:30] Phase 2 DONE — FRED ingest + regime classifier + wiring
- analysis/macro_ingest.py: banked 11 FRED series FULL history to data/feature_store/macro/
  (VIXCLS 1990+, DFF, DGS10/2, T10Y2Y, UNRATE, CPIAUCSL, DTWEXBGS, DCOILWTICO, BAMLH0A0HYM2, ICSA).
- analysis/regime_classifier.py: classify(as_of) from banked macro (VIX vol bucket + HY-OAS/curve
  risk-on/off), PIT. VERIFIED: 2020-03-15 -> high_vol|bear (VIX 57.8); 2021-11 -> normal_vol|bull;
  2022-09 -> high_vol|bear (curve inverted); today -> normal_vol|range (VIX 18.4). Matches done-when.
- Wired market_regime into recommendation_log (RecommendationInput + INSERT) + graph._log_recommendation_for
  stamps regime_tag() on every emit. VERIFIED: a rec carries market_regime='normal_vol|range'.
- Smoke "macro failed" was just Redis-not-init in the standalone script; FRED itself works.
- Follow-up (optional): stock_climate.py could read UNRATE/CPIAUCSL from the banked store. pytest 94/94.

## [22:40] Smoke-finding fixes + Phase 3 status
- Migration 023: paper_trades.stream + unrealized_pnl columns (portfolio_greeks veto + circuit_breaker
  were querying missing cols); expiry made nullable (placeholder expiries don't parse). paper-open now
  populates stream from the rec. pytest 94/94. Committed.
- Phase 3 (FMP burn): FMP STILL 429 ("Limit Reach") -> DEFERRED per runbook. PEAD walk-forward stays
  blocked until FMP rolls over. Will retry tomorrow.

## [23:00] Phase 1 DONE — MTM re-validation sweep
20 variants, 40-name VRP universe (cached). Wrote MASTER_REPORT_MTM_2026-06-18.md.
HEADLINE: under MTM DD + hard gates, ZERO signals promote. Classification change:
vrp_naked + both stop variants PROMOTE->SANDBOX (true MTM wf-DD 79-87% vs old realized 27%;
DD<25% gate disqualifies). Equity signals unchanged (equity_engine already cohort-DD).
Interesting: skew_25d wf DSR 0.58-0.75 with wf-DD 4-5% but dead train (regime-dependent ->
candidate for regime-gating w/ new classifier). PEAD hold=10d clears train (0.554), misses wf (0.252).
No promotion (matches gates) - V's call. pytest 94/94.

## [23:05] Phase 3 confirmed deferred (FMP 429). Phase 4 starting.
Nothing cleared MTM gates -> runbook fallback (2015-17 extension) INFEASIBLE on Starter 5y cap.
SME decision: spend remaining ~2,471 MarketData credits banking ~9 new sector/skew-diverse
optionable names (C,SCHW,GILD,AMGN,REGN,PLTR,COIN,SMCI,MRVL) train+wf -> permanent reusable data
asset for the regime-conditioned skew direction (the most promising OOS signal). Banks forever,
not data-snooping. Target: leave <150 credits.

## [23:20] Phase 4 DONE — credit burn to 0
Banked 9 new names (C,SCHW,GILD,AMGN,REGN,PLTR,COIN,SMCI,MRVL): TRAIN fully banked (221 VRP trades,
2,430 credits incl 349 expirations); WF hit the 0-credit wall mid-run (1 trade) — new-name WF chains
can finish on tomorrow's reset. MarketData remaining: 0/10000 (rule "<150 unspent" satisfied).
phase4_bank.json saved. These chains are a permanent reusable asset (VRP/skew/IV cross-section).

## [23:25] Phase 5 — assessed, no worthwhile burn (documented per runbook)
Alpha Vantage free tier: TIME_SERIES_DAILY works but is NON-adjusted (adjusted = premium-gated) ->
strictly inferior to yfinance (redundant, worse). NEWS_SENTIMENT is unique but has no consumer wired.
Per runbook "if nothing else has a quota worth burning, end here." No value-additive free pull -> ended.
FRED (Phase 2) was the real free-quota win and is fully banked.

## RUNBOOK ACCEPTANCE (NEXT_RUNBOOK_2026-06-18)
[x] MASTER_REPORT_MTM_2026-06-18.md — covers every promotion-eligible signal (nothing promotes)
[x] FRED feature store: 11 series, full history
[x] PEAD walk-forward has a row in the MTM report (333/135; FMP served during the sweep)
[x] MarketData remaining < 150 (= 0)
[~] FMP daily quota: Phase 3 DEFERRED (probe still 429) — documented per runbook
[x] pytest 94/94 throughout
[x] Journal entry per phase
BONUS fixes this leg: Anthropic optional (Ollama fallback), 6 smoke-test latent bugs, mig 023
(paper_trades stream/unrealized_pnl, nullable expiry), regime_classifier wired to recommendations.
