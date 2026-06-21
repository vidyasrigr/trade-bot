# PC Opus journal — 0620.2 SESSION 1 (Foundation: integrity fixes + regime/theme infra)

Owner: PC Opus. Decision-maker: V. Scope: Session 1 only (Phases 0-1), STOP at checkpoint.
Standing rules honored: nothing promoted, signal_registry untouched, research isolated in
backend/research/, SANDBOX-cap everything (no PIT yet), verify-before-fix, no emojis, pytest green.

---

## PHASE 0 — data integrity (all 4 GPT bugs verified against current code, then fixed)

- **0.1 chain cache poisoning (REAL):** `marketdata_source._load_chain` called `_write_empty()` on ANY
  exception (429/5xx/timeout/parse), poisoning the cache with false no-data. FIXED: transient exceptions
  now return None WITHOUT a sentinel; only true 204/empty-content persists an empty marker. Also made the
  chain-bank daemon's `_UNAVAILABLE` sentinel CREDIT-AWARE (only sentinels when a credit was actually
  consumed = real API "no expirations"; a 429 that consumed nothing no longer writes a false sentinel).
  AUDIT: only 3 empty parquets existed of 29,113 (NFLX/LRCX/BK — all optionable, i.e. transient
  poisoning) -> quarantined to _quarantine_0620/ for faithful refetch. 0 bad sentinels existed.
- **0.2 FMP transient-fail (REAL, my code):** daemon killed an endpoint on the FIRST non-200 regardless
  of status. FIXED: `_fetch` is status-aware — 401/402/403/404 raise+disable (tier-lock); 429/5xx/network
  retry w/ backoff (max 2) and KEEP the endpoint alive (leave the symbol stale for a later pass).
- **0.3 tracker truthfulness (REAL, my code):** build_trackers collapsed to the max-WF variant, hiding
  the canonical result (momentum showed a phantom 0.75). FIXED: latest sweep is authoritative (newest
  source wins, no cross-source max-WF); within a signal the headline is the GATE-CLEARING variant if one
  exists else the MEDIAN-wf variant; annotates n_variants + best_variant + gate_clearing_variant. Momentum
  now reads "NO_EDGE [12 variants; none clear; best wf=0.60]" — honest. (It already read JSON, not markdown.)
- **0.4 small-sample labels (REAL):** added SMALL_N hard pre-filter (n_tr<100 OR n_wf<50) ahead of any
  candidate verdict in both build_trackers and full_sweep. insider_cluster (6/12) now -> SMALL_N, not a
  phantom 0.85 SANDBOX.
- Daemons restarted to pick up 0.1/0.2. Trackers regenerated truthfully (13/49 tested; SMALL_N=2).

## PHASE 1 — regime + theme substrate (causal, point-in-time)

- **1.1 fingerprint** (`research/regime/fingerprint.py`): per-day breadth (%>200dma, adv/decline,
  new-high/low), concentration (top-10 share computed fresh), dispersion, realized vol, avg pairwise
  correlation (implied-corr identity, no n^2 matrix), VIX + term, price-based factor leadership
  (momentum, low-vol; value/quality DATA_GATED on fundamentals). 1,425 days x 11 features, 2021-2026.
  Bug found+fixed: the raw union index interleaved per-symbol calendars -> scattered NaNs broke every
  rolling feature; fixed by reindexing to a business-day grid + short ffill + min_periods.
- **1.2 causal regime_state** (`research/regime/regime_state.py`): StandardScaler + GaussianMixture
  (k by BIC) fit on TRAIN ONLY (<=2024-12-31); per-day assignment is causal by construction (a date's
  label uses only that date's causal features + the fixed train-fit model; no Viterbi smoothing, no
  full-data fit). k=6 unnamed states, sensible (e.g. state vix 25.8/breadth 0.43 = stress; vix
  16.3/breadth 0.67/696d = calm bull). 1,042 train days / 383 wf days.
- **NO-LOOK-AHEAD TEST** (`tests/test_regime_causal.py`, +2 tests -> 96 total): asserts (a) a past
  label is unchanged when future rows are appended, (b) fit ignores post-train rows (scaler params
  identical with/without wild future data). Both pass — the guard the runbook demanded.
- **1.3 theme layer** (`research/regime/themes.py`, DIAGNOSTIC ONLY): emergent clusters by trailing
  return co-movement (KMeans, unnamed integers, causal) — 8 clusters / 534 names at 2025-06-30;
  `theme_concentration` flags THEME_BET when >40% of positive PnL is one cluster (verified 0.975->True);
  `cluster_decay` tracks the leading cluster's RS (flip signal). 119 monthly snapshots, 59 decay-flagged.
  Theme is a check + kill-signal, never a gate, never named.

## Known limitations (carried, by design)
- Survivorship double-bind (GPT amendment E): the substrate is built on today's ~537 survivors, so the
  regime LABELS are survivorship-biased -> rebuilt on the PIT universe in Session 3. S2's regime sweep is
  therefore provisional twice (survivorship + pre-PIT-regime). Labeled accordingly.
- Factor leadership: value/quality gated on fundamentals (still banking); only price factors computed.
- Theme history runs to 2016 (equity cache is 10y) — harmless extra context; diagnostic only.

## SESSION 1 CHECKPOINT
- [x] Phase 0: all 4 integrity bugs verified + fixed; trackers regenerate truthfully (no max-WF, SMALL_N live)
- [x] Phase 1: fingerprint + causal regime_state persisted; theme clusters + concentration + decay live
- [x] no-look-ahead test passes (2 new tests)
- [x] pytest 96/96; nothing promoted; signal_registry untouched; daemons running; chain cache no longer
      poisons on transient failure
- Stopping point: end of Phase 1. Session 2 (Phases 2.0-3: daily MTM + GPT-18 + full regime re-test)
  NOT started, per the hard stop. Awaiting V verification.

DAEMONS LEFT RUNNING: FMP (banking statements/analyst, transient-safe), chain-bank (ADV work-list,
poison-safe + credit-aware sentinel, resumes at MarketData reset).
