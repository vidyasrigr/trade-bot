# NEXT RUNBOOK — MTM Re-Validation + Full Quota Burn

**Date:** 2026-06-18
**Owner:** PC Opus
**Author:** V + OGO (Mac Opus)
**Prereq:** P0_RUNBOOK_2026-06-17 — COMPLETE at DB+logic level (per PCO 11:10 entry). HTTP path NOT smoke-tested — see Phase 0 below.

---

## Hard quota rule (V's directive)

> **Spend every available credit today. Leave nothing on the table before reset.**

- MarketData: ~4,800 credits remaining today. Target spend: **all of it**. Do not leave more than 150 credits unspent. Credits don't roll over — unspent = wasted.
- FMP: when the 429 clears, burn through the daily quota down to a safety margin of ~10 calls.
- FRED: free, no meaningful limit — pull everything we'll need for the next month of work in one pass.
- Alpha Vantage / any other free API key in `core/config.py`: same rule, pull what's useful, leave a small safety margin.

If you finish the planned phases below with credits still left, the fallback spend is **universe expansion** (Phase 4) — bank more symbol-chains forever. Never let the day end with >150 credits unspent.

---

## Why this runbook exists

The MTM equity fix from Stage 3.0 was only applied to the VRP re-run. Every other signal — sandboxed and blocked — still carries DD numbers computed on the buggy realized-PnL-only equity curve. VRP went 28→51 (train) and 74→82 (WF) under MTM. The same correction may flip other signals into or out of promotability.

**Re-running all signals through MTM on the existing 40-symbol cache costs near-zero MarketData credits** (chains are banked, re-reads are free). It is the single highest-leverage 2 hours we have today.

---

## Phase 0 — LIVE HTTP SMOKE TEST (BLOCKING, 0 credits, ~30-60 min)

**Status check:** Per journal_2026-06-18.md [10:55], the P0 acceptance test was passed at the DB+logic level only. The full HTTP path through a booted FastAPI app was NOT exercised. This MUST run before any phase below. If the wiring breaks under a real request, every subsequent validation is built on sand.

### Procedure
1. Boot the FastAPI app (`uvicorn backend.main:app` or whatever the standard launch command is)
2. Confirm health endpoint returns green for postgres + redis (yellow OK for FMP if still 429)
3. Trigger a scanner run via the production endpoint (or `/api/scan` — whatever exists)
4. Confirm: at least one ticket emerges with a `recommendation_id`
5. Confirm: that `recommendation_id` appears in the `recommendation_log` table via direct DB query
6. Confirm: `market_regime` and `stock_regime` columns are populated (will be `unknown` until Phase 2 — that's OK for this test, just verify the column exists and is reachable)
7. POST to `/trades/paper/open` with the real `recommendation_id` → expect 200 + a paper trade row
8. POST to `/trades/paper/open` with a bogus UUID → expect 404
9. **Synthetic earnings-in-DTE acceptance test:** construct a ticket with an earnings event inside the DTE window (use `analysis/calendar.py` to find a real symbol with near-term earnings, or inject one via test fixture) → submit through the production path → confirm 409 with the guard reason in the response body, AND confirm `recommendation_log.status = 'rejected'` with the failing guard name

### Done-when
- [ ] All 9 steps above pass
- [ ] Journal entry confirming HTTP path end-to-end
- [ ] Any new latent bugs surfaced and fixed (expect at least one — this path has never been exercised)
- [ ] pytest 94/94 green

### If Phase 0 fails
- Stop. Do NOT proceed to Phase 1+ on credit-consuming work.
- Journal the failure mode, fix the underlying wiring bug, re-run Phase 0.
- If the fix takes >2h, ping V before continuing.

### Why this is Phase 0, not Phase 4
The MTM sweep + FRED ingest don't depend on the HTTP path working — but everything we do AFTER today does. If we discover a broken wiring bug tomorrow, the day of MTM/FRED work is still valid, but every "we have a working system" claim from today onward becomes suspect. Better to know now.

---

## Phase 1 — MTM RE-VALIDATION SWEEP (highest priority, ~0 credits, ~2h)

Goal: produce a corrected MASTER_REPORT_MTM with true drawdowns for every signal in `signal_registry`.

### What to run
For every signal in `scoring/signal_registry.py` (excluding `feature_only` category), execute `scripts/run_full_validation.py` with:
- `equity_curve_method='daily_mtm'`
- Train: 2018-01-01 → 2024-12-31
- Walk-forward: 2025-01-01 → 2026-06-18
- Universe: existing 40-symbol cache (same as VRP re-run, apples-to-apples)
- All variant grids preserved from yesterday's run

### Output
`data/backtest_reports/MASTER_REPORT_MTM_2026-06-18.md` with one row per signal × variant:
| Signal | Variant | Train DSR | WF DSR | Train MTM DD | WF MTM DD | Trades | Classification |
|---|---|---|---|---|---|---|---|

Classification per the (now MTM-aware) gates:
- `promote` = train DSR ≥ 0.5 AND WF DSR ≥ 0.3 AND WF MTM DD < 25% AND WF trades ≥ 100 AND no single ticker > 25% of PnL
- `sandbox` = train OR WF DSR ≥ 0.2 (everything else worth re-examining)
- `no_edge` = both DSR < 0.2 OR negative expectancy
- `blocked` = harness error or zero trades

### Hypothesis (don't anchor on it — let data speak)
- `vrp_naked_strangle` variants: stay rejected on DD (already confirmed)
- `momentum_12_1`: WF DSR was promising; MTM may push DD past the 25% gate
- `skew_xs`: sandboxed, may clear under MTM
- `iv_inversion`: unknown — could go either way
- `pead`/`insider`/`lead_lag`/`squeeze`: blocked-0-trades verdicts may stand or may reveal harness bug

### What NOT to do
- Do NOT change `promotion_status` in `signal_registry`. V decides after reviewing the report.
- Do NOT delete the old report — keep `MASTER_REPORT.md` for comparison.
- Do NOT modify any signal logic. We're re-running the same signals against a corrected equity curve.

### Done-when
- [ ] `MASTER_REPORT_MTM_2026-06-18.md` exists, covers every promotion-eligible signal in registry
- [ ] Side-by-side delta column showing realized-DD vs MTM-DD for every signal
- [ ] Journal entry summarizing which classifications changed and why
- [ ] pytest 94/94 stays green

---

## Phase 2 — FRED INGEST (parallel with Phase 1, 0 credits, ~30 min)

Goal: bank the macro history that the regime classifier and Stage 3.5 calibration need. FRED is free and entirely untapped — this is pure capability gain at zero cost.

### Pulls to make
Write to feature store partition `data/feature_store/macro/<series_id>.parquet`, daily frequency where applicable, full available history (most series go back to 1970+):

| Series | Use case |
|---|---|
| VIXCLS | regime classifier (low/high vol bucket) |
| DFF | fed funds — macro overlay |
| DGS10, DGS2 | yield curve slope |
| T10Y2Y | recession indicator |
| UNRATE | macro overlay for `stock_climate` |
| CPIAUCSL | inflation regime |
| DTWEXBGS | dollar index proxy |
| DCOILWTICO | oil — used by SPDR sector regime |
| BAMLH0A0HYM2 | high-yield credit spread (risk-on/off) |
| ICSA | initial jobless claims — recession lead indicator |

### Wiring after ingest
- `analysis/regime_classifier.py` reads from feature store (not live FRED)
- `recommendation_log.market_regime` gets populated on every emit using the classifier
- `stock_climate.py` reads UNRATE + CPIAUCSL from feature store

### Done-when
- [ ] All 10 series banked to feature store
- [ ] `regime_classifier.classify(date)` returns a non-`unknown` regime for any date 2018+
- [ ] Test: a synthetic 2020-03-15 timestamp classifies as `high_vol + bear`
- [ ] One row written to today's `recommendation_log` carries a real regime tag (not `unknown`)

---

## Phase 3 — FMP QUOTA BURN (when 429 clears, ~120-200 calls)

Goal: bank everything FMP-dependent so we never re-fetch and PEAD walk-forward unblocks.

### Pre-condition
FMP returns non-429 for a probe call. Test with one cheap call; if still 429, defer Phase 3 to tomorrow and proceed with Phase 4.

### Pulls to make (in this order — most critical first)
| Call | Symbols | Endpoint | Why |
|---|---|---|---|
| Historical earnings dates 2018-now | 40 | `v3/historical/earning_calendar/{symbol}` | UNBLOCKS PEAD walk-forward |
| Earnings calendar 2021-2026 | universe-wide | `v3/earning_calendar` (date-range) | guards need PIT earnings list |
| Insider transactions 2-year | 40 | `v4/insider-trading?symbol=X` | feeds `insider_flow.py` cluster signal |
| Short interest snapshots | 40 | `v4/short-interest` | feeds `short_squeeze.py` |
| Float, shares outstanding | 40 | `v3/profile/{symbol}` | needed for sizing + squeeze math |
| Estimates revisions history | 40 | `v3/analyst-estimates/{symbol}` | optional — only if quota allows |

### Cache discipline (CRITICAL — yesterday's bug)
- All FMP responses write to `data/cache/fmp/<endpoint>/<symbol>.json` (or per-date for calendar pulls)
- `_fmp_get()` MUST check disk cache before hitting API
- TTL: 24h for calendar/transactions, 7 days for fundamentals, forever for historical earnings dates older than today
- Yesterday's failure mode (re-fetch per fold) MUST NOT recur — log a hard error if a duplicate call is attempted within a session

### Done-when
- [ ] Every endpoint in the table above has cached responses on disk for 40 symbols
- [ ] PEAD walk-forward runs to completion and produces a row in MASTER_REPORT_MTM
- [ ] `insider_flow.compute_cluster_signal(symbol)` returns non-empty for at least one symbol in the cache
- [ ] FMP call counter at end of phase shows we used down to ~10-call safety margin

---

## Phase 4 — MARKETDATA UNIVERSE EXPANSION (after Phase 1 results, use ALL remaining credits)

Goal: spend every remaining MarketData credit on banking new chains for symbols that Phase 1 flagged as worth expanding.

### Picking the 20+ symbols
After Phase 1 completes, look at MASTER_REPORT_MTM:
- If `momentum_12_1` clears MTM gates → bank 20 mid-cap trend-clean names (not just mega-caps). Suggested: NVDA, AMD, AVGO, MU, ARM, MRVL, CRWD, PANW, NET, MELI, MNDY, DDOG, ANET, COIN, HOOD, AFRM, RBLX, U, SOFI, PLTR (already in 40? swap)
- If `skew_xs` clears → bank 20 high-skew-history names (financials, biotechs)
- If nothing new clears → bank the existing 40 universe's TRAIN window for the **2015-2017 extension** (more out-of-sample history)

### Credit math
- Yesterday's bank cost: ~228 cr/symbol for train window
- Walk-forward window: ~30 cr/symbol (shorter)
- Budget: ~4,800 cr remaining → ~20 train symbols OR ~160 WF symbols OR mix

### Spending rule (V's directive)
> **Do not leave the day with more than 150 credits unspent.**

Calculate per-symbol cost from the first 2-3 symbols banked, then pre-commit to the count that gets us to <150 leftover. If unsure, bank one fewer and use the remainder on chain refreshes for already-cached symbols (closes any stale gaps).

### Done-when
- [ ] 20+ new symbols (or equivalent in WF expansion) banked to chain cache
- [ ] MarketData credit tracker shows < 150 credits remaining for the day
- [ ] Journal entry lists every symbol banked and which Phase 1 signal motivated it

---

## Phase 5 — ALPHA VANTAGE + ANY OTHER FREE QUOTAS (if remaining time)

Goal: burn untapped free quotas. Check `core/config.py` for any API key we set but never use.

### Pulls to consider
- Alpha Vantage daily adjusted prices for 40 symbols (if AV key set) — backup/cross-check vs yfinance
- News sentiment archive if free tier supports it
- Anything else that's free and bankable

If nothing else has a quota worth burning, end here.

---

## Execution order (with parallelism)

```
TIME 0:
  Phase 0 — Live HTTP smoke test (BLOCKING, 30-60 min, 0 credits)
  If it fails, stop and fix before anything else.

TIME +30-60m (after Phase 0 green):
  ├── Phase 1 starts (MTM sweep, 2h compute, 0 credits)
  └── Phase 2 starts (FRED ingest, 30 min, 0 credits) — parallel

TIME +30m:
  Phase 2 complete → start FMP probe (Phase 3)

TIME +30m → +90m:
  ├── Phase 1 still running
  └── Phase 3 runs if FMP unblocked

TIME +2h:
  Phase 1 complete → V reviews MASTER_REPORT_MTM
  Pick Phase 4 symbols based on results

TIME +2h → end of day:
  Phase 4 burn — bank symbols until credit < 150
  Phase 5 if time + budget permits
```

---

## What to journal

- Per-phase start/end timestamps
- Credit count before/after each phase (MarketData + FMP)
- For Phase 1: which signals changed classification under MTM (table)
- For Phase 4: final credit count + symbol list + reasoning
- Any latent bugs surfaced (same as P0 — we WANT these to fall out)
- Anything where you escalated and waited for V

---

## Escalation criteria

Ping V immediately if:
- Phase 1 reveals a signal logic bug (not just bad DD) — V decides whether to fix or document
- MTM re-run reverses VRP verdict (it shouldn't, but if it does, V wants to look)
- Phase 4 symbol selection is ambiguous — multiple signals clear, unclear which universe to prioritize
- Any quota source returns an unexpected error pattern (auth, suspended, billing) — could indicate account issue not rate limit

## What NOT to do

- Do NOT promote anything in `signal_registry`. V's call only, after MASTER_REPORT_MTM review.
- Do NOT start Stage 5 briefing-replay. Still needs V's design + credit estimate session.
- Do NOT modify signal logic during the MTM sweep — re-validation only.
- Do NOT leave the day with >150 unused MarketData credits. Credits don't roll, unspent = wasted money.
- No emojis in code or commits.
- No new signals invented.

## Acceptance test for the whole runbook

- [ ] `MASTER_REPORT_MTM_2026-06-18.md` exists and covers every promotion-eligible signal
- [ ] FRED feature store partition populated with 10 series of full history
- [ ] PEAD walk-forward has a row in the MTM report (assumes Phase 3 ran)
- [ ] MarketData credits remaining today: < 150
- [ ] FMP daily quota remaining: < 10 calls (or documented why Phase 3 was deferred)
- [ ] pytest 94/94 green throughout
- [ ] Journal entry for every phase
