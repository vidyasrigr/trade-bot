# PC Opus journal — 0620.3 SESSION 3 (Safety stack + PIT + extended-history regime re-test)

Owner: PC Opus. Decision-maker: V. Scope: 0620.3 (replaces 0620.2 Session 3). STOP at checkpoint.
Standing rules honored: nothing promoted, signal_registry untouched, research isolated, causal regime
only, SANDBOX/survivorship-cap, verify-before-fix, no emojis, pytest green (104).

Sequencing note (owner call): ran S -> 4 -> 5b -> 5c -> 5d, with 5a (PIT/delisted) time-boxed last,
to protect 5d (the payoff) per V's instruction.

---

## PHASE S — daemon supervisor
`scripts/daemon_supervisor.sh` — flock-guarded watchdog (setsid-detached), restarts FMP + chain-bank
daemons within ~60s of death. VERIFIED: killed fmp, watchdog restored it in ~30s. systemd --user
units documented in `deploy/README_daemons.md` as the production answer. (The harness cleans up
tool-spawned processes on call-exit, so the watchdog runs via the harness background mechanism here;
systemd is the real cross-session fix.)

## PHASE 4 — pre-paper safety stack (all verify-before-fix; P0 regression suite added)
- 4.1 `scoring/validation_ledger.py` — conviction now needs registry AND ledger AND mode. The ledger
  is the EARNED list (currently EMPTY); legacy `live_full` labels no longer suffice -> in paper/live
  nothing drives conviction until V promotes. Backtest bypasses.
- 4.2 confirmation count + tail-alignment now EXCLUDE mode/ledger-blocked signals (was reading raw_score,
  so a blocked signal still counted toward the 3-independent gate).
- 4.3 Kelly 0.50 -> 0.10, hard cap 0.25, conviction-stack LIFT DISABLED (KELLY_LIFT_ENABLED=False).
- 4.4 PaperFillModel wired into `/trades/paper/open`: simulates fills from live quotes, rejects no-fill
  (422), stores model fill + expected-vs-actual slippage, IGNORES user entry_price.
- 4.5 promotion gate grades on true_account_dd (Phase 2.0) when present, else cohort DD.
- 4.6 `tests/test_p0_safety.py` (11 tests): ledger gate, blocked-signal-excluded-from-confirmation,
  Kelly lift disabled+capped, PaperFillModel rejects (no_quote/wide_spread/low_oi/any-leg-fail) +
  fills worse than touch, recommendation_id required. pytest 104 passed.

## PHASE 5b/5c/5d — extended history + substrate rebuild + the make-or-break regime test
- 5b: discovered MarketData's 5y cap applies to EQUITIES too (AAPL was an outlier; MSFT/JPM capped at
  2021). Path to 2010 = yfinance per-Ticker `.history(period=max)` (bulk yf.download throttles; the
  Ticker API is deep + reliable). Backfilled 399 names; 226/300 top names have <=2012 history.
- 5c: rebuilt fingerprint + causal regime_state (k=6, fit train 2010-2018, forward-filter) + themes on
  2010-2026. no-look-ahead test still green.
- 5d (`scripts/regime_sweep_ext.py`, train 2010-19 / wf 2020-26, equity-only): regime occurrences now
  **3-5 per signal** (vs exactly 1 in 2021-26) -> leave-one-instance-out finally possible. This was the
  whole point and it worked.

### MAKE-OR-BREAK VERDICT: no signal clears the regime-conditional bar, even with 16 years.
35 signals: 16 NO_EDGE, 11 INSUFFICIENT_REGIME_INSTANCES, 2 REGIME_SUSPECT, 1 SMALL_N, 5 DATA_GATED.
**Zero UNCONDITIONAL_CANDIDATE, zero REGIME_CONDITIONAL_CANDIDATE.** The recent-window leads
(momentum/skew/2025-26 standouts) were recent-window NOISE — they do not recur as robust low-DD
multi-instance regime edges.
- Closest: **earnings_announcement_premium** (train 0.98 / wf 0.67 / 30% DD / 5 occurrences) — but one
  episode >50% of gated trades -> INSUFFICIENT_REGIME_INSTANCES. The one lead worth dedicated study.
- adx_dir, long_term_reversal -> REGIME_SUSPECT (recur, not theme bets, but 64% / 37% account DD = undeployable).
- Tightened `_label`: REGIME_CONDITIONAL_CANDIDATE now requires DD<25% + wf>=0.30 (positive gated
  return alone was too generous; re-derived labels from the existing JSON, no re-sweep).

## PHASE 5a — PIT / delisted universe: DEFERRED (with decisive reasoning)
Free anon delisted-history sources rate-limit (Stooq 404 on anon; yfinance returns empty for delisted).
A clean delisted ingest is a large separate effort. CRUCIAL: it does NOT change the make-or-break
verdict. Survivorship bias makes results BETTER than reality (dead losers removed); nothing cleared
even on the survivor-FAVORABLE data, so PIT can only make signals look worse, never rescue one. 5a is
needed for promotion-grade magnitudes, which is moot while there are zero candidates. Recommend a
proper survivorship-free dataset (Stooq bulk bundle or paid CRSP-style) when a candidate ever emerges.

## SESSION 3 CHECKPOINT
- [x] Phase S: daemons supervised + auto-restart verified
- [x] Phase 4: all 5 safety bugs fixed; P0 regression suite passes; paper-open simulates fills + rejects
      user price; Kelly tiny + lift disabled; ledger gates conviction; promotion DD uses daily-MTM
- [x] Phase 5b/5c/5d: extended 2010-2026 equity history; causal substrate rebuilt; regime sweep re-run
- [~] Phase 5a: PIT/delisted DEFERRED (reasoned; does not change the verdict)
- [x] Headline: NO signal clears the regime-conditional bar with real multi-instance proof; recent-window
      leads were noise; earnings_announcement_premium the lone lead (fails instance-independence)
- [x] pytest 104; nothing promoted; signal_registry untouched
- Nothing is paper-ready: zero candidates. Validation ledger stays empty until V promotes.

THEN STOP. Backlog closed. V decides promotions (none earned) + whether to fund a survivorship-free
dataset to chase earnings_announcement_premium.
