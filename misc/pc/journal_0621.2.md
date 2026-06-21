# PC Opus journal — 0621.2 (Fix machinery + regime truth + new evidenced signals)

Owner: PC Opus (full ownership, decision-maker). One session, end-to-end. Standing rules honored:
research namespace isolated, nothing promoted, signal_registry untouched, daily-MTM account DD,
multiple-testing deflation, realistic costs, no-look-ahead, pytest green (104), no emojis.

---

## THE HEADLINE — first genuine candidate after ~90 prior null signal-variants

**`earnings_announcement_premium` -> CANDIDATE_DD_GATED.** It is the first signal to beat
buy-and-hold RISK-ADJUSTED in BOTH windows:
- train (2010-2019) sharpe **1.42** vs SPY 0.92, DD 23% (clears); wf (2020-2026) sharpe **1.27** vs
  SPY 0.81, +14.7% CAGR excess.
- Consistent sharpe 1.21-1.49 across EVERY sub-period (2010-19 / 2020 / 2021-26) -> NOT recent-window.
- Event-driven (Frazzini-Lamont announcement premium), not long beta; clean look-ahead (longs around
  KNOWN announcement dates; no surprise peeking).
- ONLY gate missed: wf account DD 30% (>25%) — ENTIRELY COVID-2020 (train DD 23% clears). A VIX<35
  entry filter trims to 27%; a mid-trade de-gross rule is needed for <25% (DD is from holding through
  the crash, not from entries). This is the deployment caveat, not an edge problem.
- VERDICT: first signal worth a paper allocation, pending a crisis de-gross overlay + PIT + V's call.

## PART A — machinery + regime TRUTH
- **A2a factual/oracle regime** (research/regime/factual.py): ex-post SPY-drawdown weather
  (bull/correction/bear/crisis) + VIX + breadth + the one NBER recession (COVID), 2010-2026. Also a
  discrete `oracle_regime` for the A3 oracle arm (diagnostic ceiling).
- **A2b REGIME_AUDIT (major finding):** the live GMM `regime_state` is REGIME-BLIND TO STRESS — 5 of 6
  states are dominantly bull; it labels the COVID bottom (SPY -34%, VIX 62), 2018Q4 (-19%), and the
  2022 bear (-24%) all as "state 2 = 80% bull." So earlier regime-conditional nulls (0620.2 S2/S3) were
  PARTLY a classifier artifact — you can't gate on regimes the classifier never identifies. The ORACLE
  arm rescuing signals the APP arm didn't (sector_rs oracle 0.65 vs app 0.30) confirms it.
  RECOMMENDATION (flagged for V): replace the GMM for gating with a CAUSAL drawdown+VIX+breadth
  classifier (online version of the factual labels) — highest-leverage fix to the regime program.
- **A1 machinery fixes:** REGIME_SWEEP_2010_2026 window metadata corrected; gated-D3 / benchmark gates
  built into the new sweep; tracker truthfulness already fixed in 0620.2 P0.3.
- **A3 oracle baseline:** every new signal tested in 3 arms {no-regime / oracle / app} so we can tell
  "signal is bad" from "classifier is wrong." This is what surfaced the classifier defect above.

## PART B — new evidenced signals (real mechanisms)
Built as research adapters: `etf_mean_reversion` (Connors IBS+RSI2), `sector_relative_strength`
(Moskowitz-Grinblatt), `pairs_statarb` (Gatev-Goetzmann market-neutral), plus the refined
`earnings_announcement_premium`. Output NEW_SIGNALS_SWEEP_2026-06-21.{md,json,csv}.
- Built `run_long_only_account` — equal-weight, cash-aware sizing — and ADDED A BENCHMARK-RELATIVE
  GATE (must beat buy-and-hold in both windows). This caught + KILLED a FALSE POSITIVE:
  etf_mean_reversion first labelled UNCONDITIONAL_CANDIDATE was actually long beta (invested ~100% of
  days, train sharpe 0.32 << SPY 0.92) — only "won" in 2020-26. Correctly downgraded.
- Results: earnings_announcement_premium CANDIDATE_DD_GATED (the find); etf_mr_narrow
  REGIME_CONDITIONAL but beta/recent-window; sector_rs WEAK_LEAD (oracle-rescued -> needs a working
  classifier); pairs_statarb NO_EDGE; etf_broad WEAK_LEAD.

## PART C — overlays
Tested the highest-value application: a crisis/VIX entry overlay on the candidate. VIX<35 trims DD
30%->27% (not <25%); VIX<30 hurts sharpe. Conclusion: the COVID DD needs a mid-trade de-gross rule,
not an entry filter. Broader VCP/failed_breakout overlays deferred (the candidate's DD fix is the
specific overlay that matters).

## HONEST DEFERRALS (time-boxed; the candidate + audit were the priority)
- Options signals B5-7 (index_credit_spread, earnings_iv_crush, earnings_drift): NOT built. Options are
  5y-capped/CACHE_LIMITED and prior sessions showed VRP-style edges are DD-prone; the equity event
  premium is the stronger, deeper-history lead. Queued.
- pead_confirmed (B3): deferred — FMP analyst-revision depth is thin; the related announcement premium
  is already the find.
- A2c single canonical regime object: components exist (factual + regime_state + audit); a one-object
  wrapper is a small follow-up.

## FINAL CHECKPOINT
- [x] Part A: machinery metadata fixed; REGIME_AUDIT done (classifier IS mislabeling stress — big
      finding); oracle/factual regime built; 3-arm oracle baseline in the sweep
- [x] Part B: 4 evidenced equity signals wired + BT + WF + 3 arms + realistic costs + benchmark gate;
      NEW_SIGNALS_SWEEP written. (Options B5-7 + pead_confirmed deferred, documented.)
- [x] Part C: crisis overlay tested on the candidate (doesn't fully fix DD; needs de-gross rule)
- [x] HEADLINE: earnings_announcement_premium beats buy-and-hold both windows = FIRST real candidate
      (DD-gated by COVID only). And the regime audit shows the app classifier was masking earlier results.
- [x] pytest 104; nothing promoted; signal_registry untouched; daemons supervised
- One paragraph for V: earnings_announcement_premium is real and the best result of the program —
  consistent sharpe ~1.3 beating SPY across 16 years, clean mechanism + look-ahead, only tripped by the
  COVID drawdown. Recommended next moves: (1) add a crisis de-gross overlay and re-test DD; (2) fix the
  regime classifier to a causal drawdown/VIX gate (the audit shows the GMM is stress-blind) and re-run
  the regime arms — sector_rs and others may clear under a WORKING classifier; (3) PIT-confirm the
  candidate. This is the first thing worth paper-trading, on your promotion call.
