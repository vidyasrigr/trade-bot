# CONSTRAINT RUNBOOK — Saturate the Bottleneck, Parallelize Everything Else

**Date:** 2026-06-19
**Owner:** PC Opus
**Author:** V + OGO (Mac Opus)
**Goal:** Honest BT + WF verdicts on all 49 signals, ASAP, so we can pick winners and start paper trading.

---

## The operating principle (read first)

This is theory-of-constraints. There is exactly ONE bottleneck: **MarketData chains** (10k credits/day, ~258 cr/symbol, so ~38 new symbols/day max). Everything else — yfinance, FRED, FMP (300/min ≈ unlimited for us), EDGAR, CFTC, short-interest CSVs — has **no meaningful bottleneck**.

The rule for tonight and every night:
1. **Spend the bottleneck's full daily budget — every day.** MarketData's 10k/day is a hard cap; it's idle most of each day by necessity. The goal is that no day's 10k goes unspent (a daemon that auto-resumes at reset guarantees this), NOT that the API is hit continuously.
2. **Run every non-bottlenecked source flat-out in parallel.** Free/fast signals must be tested on the FULL universe immediately — there is zero reason to wait on them.
3. **No phase gates, no waiting on V mid-run.** All tracks run concurrently. Journal per track. V reviews in the morning. Escalate mid-run only on the criteria at the bottom.

We spent 4 days at this NOT done. Tonight it gets done. PCO has 8-12h of runway — fill it.

---

## What's bottlenecked vs not (the map I should have drawn on Day 1)

| Signal | Data need | Bottleneck? | Can fully test today? |
|---|---|---|---|
| trend, candles, chart_patterns, momentum, support_resistance, risk, volatility_regime | yfinance OHLCV | NO | YES — full universe |
| momentum_12_1 | yfinance | NO | YES — full universe |
| macro, regime_markov_market, regime_markov_per_symbol | FRED + yfinance | NO | YES |
| fundamental | FMP | NO (daemon) | YES as daemon fills (~hours) |
| beat_and_raise_pead, calendar (earnings) | FMP earnings dates | NO (daemon) | YES as daemon fills |
| insider_cluster, insider_analyst_combo | FMP insider (or EDGAR free) | NO (daemon) | YES as daemon fills |
| short_squeeze | FMP/CSV short interest | NO (daemon) | YES as daemon fills |
| analyst_revision_cascade | FMP analyst | NO (daemon) | YES as daemon fills |
| sector_dispersion | FMP sector + yfinance | NO | YES |
| reddit_mentions, reddit_polarity | pullpush.io free | NO | partial today |
| cot_extreme | CFTC CSV free | NO | YES |
| vrp_z, vrp_level, skew_25d, iv_call_put_spread, iv_term_slope | MarketData chains | **YES** | only on existing 49-name cache today; full universe over 5-7 days |
| iv_analysis, options_chain, greeks, trade_structure, earnings_adj_iv | MarketData chains | **YES** | same |
| gex_dex, options_flow, whale_flow | MarketData chains | **YES** | same |
| vrp_harvest, pre_fomc_straddle (strategy BT) | MarketData chains | **YES** | on existing cache today |

**~27 of 49 signals are NOT bottlenecked** and can get a full-universe BT+WF verdict today. The remaining ~22 are MarketData-bound; they get a verdict on the existing 49-name cache today and a full-universe verdict as the chain bank grows.

---

## FOUR PARALLEL TRACKS — all start at once, run all night

### TRACK 1 — Bottleneck saturation: MarketData chain banking (spend full 10k/day, daemon auto-resumes)

This is the ONLY hard bottleneck. 10k credits/day is a hard cap — you cannot spend past it,
so the API is necessarily idle most of each day. "Saturate" here means: **spend the full
10k every day and never let a day's allotment go unspent.** The *daemon process* stays alive
across days; the *spending* happens in a burst until the daily cap, then sleeps until reset.

- Build/confirm a **chain-banking daemon** (extend `backtest/marketdata_source.py` banking logic) that:
  - Pulls the target universe (start: 200 sector-diverse core names; list below)
  - For each un-banked symbol, fetches train-window + WF-window chains and persists parquet
  - Tracks credits; spends until the daily 10k cap, then **sleeps until next reset and auto-resumes** — so no day is ever wasted because we forgot to kick it off
  - Banks in priority order: names that the Track-3 free sweep flags as high-IC first
- Tonight: bank as many new names as 10k allows (~38). Target the 200-core list, minus the 49 already cached.
- Journal the credit counter hourly; end each day at <150 credits unspent (V's standing rule).
- Full 200-core universe completes in ~5-7 days at 38/day; this runs on autopilot — no new runbook needed per day.

**Re-test policy (important — don't waste cycles):** as the bank grows (49 -> 100 -> 200),
re-run options signals on the LARGER universe (new data = justified). Do NOT re-run an
identical test on an identical cache. VRP already has its honest MTM verdict on the 49-cache
-> do NOT re-run it. Only new universe size or new methodology (MTM/regime) justifies a re-run.

**Core-200 universe seed (sector-diverse, liquid, optionable):** mega-cap tech (NVDA AMD AVGO MU ARM MRVL INTC QCOM TXN), software (MSFT CRM ORCL ADBE NOW PANW CRWD NET DDOG SNOW PLTR), internet (GOOGL META AMZN NFLX UBER ABNB BKNG), consumer (AAPL TSLA COST WMT HD NKE SBUX MCD), financials (JPM BAC GS MS WFC C SCHW V MA AXP), health (LLY UNH JNJ ABBV MRK PFE TMO ISRG), energy (XOM CVX COP SLB), industrials (CAT DE BA HON GE), ETFs (SPY QQQ IWM XLF XLE XLK SMH), + extend toward 200 from the liquid options list. Final list is PCO's call — diversify across sectors, prioritize tight spreads + high OI.

### TRACK 2 — FMP daemon (24/7, ~$0 marginal, 0 LLM tokens)

Script is written: `backend/scripts/fmp_daemon.py`. Once V provides the FMP key:

- `export FMP_API_KEY=...` then `python -m scripts.fmp_daemon` (runs forever, paced 280/min)
- **First-run check:** the daemon logs the HTTP status of each distinct endpoint once (PROBE lines). FMP migrated to `stable/` paths in Aug-2025 — if any endpoint PROBEs FAIL, fix that one row in `ENDPOINTS` and restart. The others keep flowing.
- Priority order is already encoded: earnings -> insider -> short interest -> profile/float -> analyst -> fundamentals -> news.
- **FMP TIER REALITY (PCO is right):** Starter ($29, 300/min) covers fundamentals, price, profile, news, AND earnings dates — but insider-trading, short-interest, and analyst-estimates are Premium+. Expect those three endpoints to PROBE 402 on Starter. That is FINE and EXPECTED — the daemon skips failed endpoints without wasting quota, and those three signals are sourced from the FREE Track 4a feeds instead (EDGAR Form 4 for insider, exchange short-interest CSV for squeeze, FMP grades/price-target where available else skip). Do NOT upgrade FMP to chase them — EDGAR/exchange data is the authoritative source anyway. The $29 specifically buys: PEAD/earnings dates + fundamental + sector_dispersion + profile/float + news, rate-limit-free.
- It banks the FULL listed universe to `data/cache/fmp/<endpoint>/<symbol>.json`, idempotent, resumable.
- Wire `analysis/*.py` FMP readers to check this disk cache before any live call (the daemon and the app share the cache dir).
- Journal: quote the `_daemon_progress.log` throughput hourly.

Run as a background process (`nohup ... &` or a tmux pane) so it survives the session and keeps filling while everything else runs.

### TRACK 3 — Full-universe FREE signal sweep (0 credits, the big unblock)

This is the track we should have run on Day 1. It needs NOTHING bottlenecked.

**GATING DEPENDENCY (corrected per PCO):** the runner's `_resolve_universe()` is `get_full_universe()[:size]`, and `get_full_universe()` returns a hard-coded 107-name TIER1 list — so `universe_size=1000` silently caps at 107. The `liquid_1000`/`liquid_500` labels are nominal, NOT wired. Before any real 500/1000/2000 sweep:
   - Wire `data/universe.py::get_dynamic_universe` into the runner's universe resolver
   - Backfill the feature store for those names (Step 1 below)
   This wiring is the actual prerequisite for Track 3, not a config flag. Do it first.

1. **Backfill feature store** with yfinance OHLCV. NOTE (PCO is right): Yahoo throttles/IP-bans bulk pulls — do NOT attempt 5,000 names cold. Daemonize it, start with the liquid ~500-1000, expand outward over nights. Use/extend `scripts/backfill_feature_store.py`. Free, and the substrate for everything below.
2. **Run `run_full_validation.py`** for every `needs_marketdata=False` variant at the now-real **500, then 1000, then 2000** name slices (gated on the wiring + backfill above). Signals: trend, candles, chart_patterns, momentum, momentum_12_1, support_resistance, risk, volatility_regime, regime_markov (both), macro, sector_dispersion, cot_extreme.
3. **MTM equity** on every run (`equity_curve_method='daily_mtm'` — the Stage 3.0 fix).
4. **Per-primitive decomposition** (V's explicit ask): break the rollup categories into their components and IC each separately —
   - `momentum` -> RSI(14), MACD, Stochastic, ROC, OBV as 5 separate signals
   - `trend` -> EMA20/50/200 alignment, ADX, slope as separate
   - `candles` -> top engulfing/hammer/doji/star detectors separately
   - `risk` -> Bollinger width, ATR, realized-vol separately
   So we learn which primitive actually carries edge instead of burying it in a blended score.
   SCOPING (PCO is right): these primitives are NOT in `signal_registry`, so they can never be
   "promoted" — this is pure research / IC ranking to inform which rollups to trust. ~15 adapters
   of real work; do as time allows after the rollup sweep lands.

**Output:** `data/backtest_reports/FREE_SWEEP_2026-06-19.md` — every free signal AND every primitive, BT DSR + WF DSR + MTM DD, across 500/1000/2000 universe slices, classified PROMOTE/SANDBOX/NO_EDGE.

### TRACK 4 — Free auxiliary ingest + MarketData-cache signal tests (0 credits)

Two independent things, both free, run alongside:

**4a. Free auxiliary data daemons** (no FMP needed, pure capability gain):
- SEC EDGAR Form 4 historical ingest (full universe) — second source for insider, validates FMP
- NYSE/Nasdaq biweekly short-interest CSV history — second source for squeeze
- CFTC Commitments of Traders weekly CSV — unblocks `cot_extreme`
- FRED: expand from 11 to 30+ series, full history
- Treasury yield curve direct
All to feature store, daemonized if rate-limited.

**4b. MarketData-cache signal tests on the EXISTING 49-name cache** (0 new credits — re-reads are free):
- **Skew_25d regime-conditioning experiment** (the standout lead — WF DSR 0.58-0.75). PRE-REGISTER the hypothesis before looking: "skew_25d has positive WF DSR when `regime in {low_vol_bull, mid_vol_range}` and is flat/negative otherwise." Test using the regime classifier (now wired). If a DIFFERENT regime bucket wins, that's a hypothesis for a fresh sample, NOT a promotion — document it, don't promote it.
- Re-run vrp_z, vrp_level, iv_call_put_spread, iv_term_slope on the 49-cache with MTM + regime conditioning.
- Output appended to `MASTER_REPORT_MTM` for the cache universe.

---

### TRACK 5 — Trackers: single source of truth (build EARLY, regenerate continuously)

Full spec in `mac/TRACKERS_SPEC_2026-06-19.md`. Build `scripts/build_trackers.py` and the three
auto-generated dashboards:
- `SIGNAL_STATUS.md` — 49 signals: tested? which stream (O/S/M/L)? pass/fail/why? blocked-by?
- `DATA_INVENTORY.md` — what's pulled from where, # tickers, coverage bars, pending, credit ledger
- `VALIDATION_LEDGER.md` — BT/WF/paper status per signal, rolled up per stream + per category

Requirements:
- Add a `streams` field (O/S/M/L) to every `SignalSpec` so the trackers are data-driven.
- Regenerate at the end of every validation run AND hourly via APScheduler.
- Copies to `data/trackers/` and `mac/trackers/`.
- Build these EARLY in the night so every subsequent track's output shows up as it completes —
  they are how V (and you) verify the other 4 tracks actually landed.

---

## PRIORITY GAP — survivorship / point-in-time correctness (read before Track 3 runs)

The one thing that, if missed, **silently skews every free-signal result and could make us promote a
fake edge** — exactly the failure mode the trackers exist to prevent.

When Track 3 tests momentum/trend on "the full Nasdaq universe," the loader returns **today's listed
names**. Backtesting 2018-2026 on names that survived to 2026 is survivorship bias — delisted/bankrupt
names are missing, which inflates momentum and trend (losers vanish from the sample).

PCO must, in Track 3:
- Prefer a **point-in-time universe** (include delisted names via Stooq / Nasdaq Trader delisted
  archives / EDGAR) so the backtest universe reflects what was listed AS OF each date, not survivors.
- If full PIT universe isn't ready tonight, **label every free result `SURVIVORSHIP-BIASED` in the
  tracker**, treat DSRs as upper bounds, and **cap such signals at SANDBOX — never PASS** until
  re-tested on a PIT universe.
- Flag this in `FREE_SWEEP_2026-06-19.md` so V knows which numbers are provisional.

Better an honest SANDBOX than a fake PASS.

---

## What % of BT + WF gets done TODAY — honest answer

Measured two ways:

**By signal count (at least one honest BT+WF verdict today):**
- 27 non-bottlenecked signals: full-universe verdict today -> ~55%
- ~22 MarketData signals: verdict on 49-name cache today (not full universe) -> partial
- **Realistic: ~70-80% of signals get a defensible BT+WF verdict by tomorrow morning.** The gap is full-universe coverage for options signals.

**By "production-grade" (full target universe, the bar that matters for promotion):**
- Free signals: ~55% done today (full universe achievable)
- MarketData signals: gated by chain banking -> ~38 names/day -> **5-7 days to 200-core, ~13 days to 500.**
- **Realistic: ~50% production-grade today, 100% in 5-7 days for the 200-core universe.**

So: **today gets us from "1" to roughly "55-60"** — every free signal honestly tested at scale, every FMP/EDGAR/CFTC source ingesting, the bottleneck saturated and counting down. The last 40 points are the MarketData universe filling over the next week, which now runs on autopilot via Track 1.

That is the 10x. Four days got us 0->1 because we ran serial and never touched the free 55%. One night of four parallel tracks gets us to ~55-60, and the remainder auto-completes.

---

## Acceptance checklist for tomorrow morning

- [ ] `FREE_SWEEP_2026-06-19.md` — every free signal + every decomposed primitive, BT/WF DSR + MTM DD, across 500/1000/2000 universe slices
- [ ] Per-primitive IC table (RSI vs MACD vs Stoch vs BB vs ATR etc. — which one actually has edge)
- [ ] FMP daemon running as a background process; `_daemon_progress.log` shows ≥50k calls cached, all endpoints PROBE OK (or failures documented + fixed)
- [ ] EDGAR Form 4 + CFTC COT + short-interest CSV ingested to feature store
- [ ] FRED expanded to 30+ series
- [ ] Skew_25d regime-conditioning verdict with PRE-REGISTERED hypothesis stated before results
- [ ] MarketData: +~38 names banked, <150 credits left, Track-1 daemon set to auto-resume at reset
- [ ] `signal_post_mortem.md` — per-signal: why it hasn't worked yet + what unblocks it (V's ask)
- [ ] Stage 5 briefing-replay credit estimate recomputed now that Ollama LLM = $0
- [ ] pytest 94/94 green throughout
- [ ] Per-track journal with hourly timestamps + credit counters

---

## Escalation criteria (only reasons to interrupt V mid-run)

- A signal logic bug (not just bad numbers) — V decides fix-now vs document
- FMP daemon endpoints mostly PROBE FAIL (suggests plan/auth issue, not a code bug)
- A free signal shows implausibly good results (DSR > 1.5 on full universe) — smells like leakage; flag before trusting
- MarketData account error that isn't a rate limit (billing/suspension)
- Any track fully blocked with no parallel work left (shouldn't happen with 4 tracks)

## Standing rules (unchanged)

- Do NOT promote anything in `signal_registry`. V's call only.
- No live capital. Paper only.
- pytest 94/94 green after every change.
- Persistent disk caches stay on (MarketData parquet + FMP json).
- No emojis in code or commits.
- No new signals invented — only what's in `scoring/signal_registry.py`.
- Pre-register every regime/conditioning hypothesis BEFORE looking at which bucket wins. No p-hacking a sandboxed signal into a promotion.

## How OGO will write runbooks from now on

- Constraint map first: what's bottlenecked, what's not, before any plan.
- Default to parallel tracks; phase gates only on real dependencies.
- Daemonize every rate-limited source so a limit is never a schedule constraint.
- Size runbooks to fill PCO's full 8-12h night.
- V reviews in the morning; PCO doesn't wait mid-run except on escalation criteria.
- Free/unbottlenecked work runs at FULL universe scale by default, never on a toy 40-name set.
