# PC Session Log

Running record of work done on V's RTX 5080 PC, kept for later review against laptop-Opus.
Append-only. Newest entries at the bottom of each section. Times in PT.

**Session owner:** Claude Code (PC), high-effort.
**Operating contract (from PC_OPUS_HANDOFF.md + SESSION_CONTEXT.md):**
- Diagnose → root cause → fix-or-escalate. Never conclude before evidence.
- 0 trades = bug indicator, NOT a verdict. "Failed validation" only when trades ≥ ~100 AND DSR < 0.35.
- No re-architecting. No invented signals. Every signal stays in `scoring/signal_registry.py`.
- Don't disable the persistent parquet cache. Don't burn MarketData credits on speculative tests.
- Promotion requires DSR > 0.5 train AND > 0.3 walk-forward.
- pytest must be 94/94 before declaring any code change done.

---

## Environment facts (PC, confirmed this session)

- Python: system pyenv default was 3.8.18 (too old). App needs 3.11+. Using a venv at
  `/home/vi/Projects/Trade Bot/venv` built from `/usr/bin/python3.12`.
- GPU: RTX 5080, 16.6 GB VRAM, torch CUDA available (cu124 wheels).
- Postgres 15 + Redis 7 + Ollama running. Ollama models: llama3.1:8b, deepseek-r1:7b, nomic-embed-text.
- MarketData key set in `backend/.env` (Starter tier per Opus notes).

---

## Issues found

### I-1  Overnight VRP backtest produced 0 trades (both legs) — SILENT INFRA FAILURE
- **When:** 2026-06-16 evening run (vrp_2018_2024_train.json + vrp_2025_2026_walkforward.json both `num_trades: 0`).
- **NOT** a strategy verdict. Real VRP on 40 mega-caps over years should fire 50–200+ trades/name.
- **Primary root cause (confirmed):** `pyarrow`/`fastparquet` not installed in venv.
  `MarketDataHistoricalSource.trading_days()` does `pd.read_parquet`/`to_parquet`; on failure returns `[]`;
  `simulate_trade` aborts at `if not days: return None` → every trade dropped → `{"num_trades": 0}`.
  Log evidence: `trading_days SPY fetch failed: Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'.`
- **Secondary root cause (confirmed):** `run_vrp_backtest` uses `get_multi_ohlcv_yfinance(period="5y")`.
  From 2026 that yields only 2021-06-17 → 2026-06-16. The "2018–2024 train fold" is missing 2018–2021,
  including the COVID-2020 vol spike. Even with parquet fixed, train leg window would be wrong.
- **Note vs handoff:** PC_OPUS_HANDOFF.md ranked causes (#1 MarketData empty old dates, #2 candle endpoint,
  #3 strike rounding, #4 Friday expiry) were written from the laptop without PC log access. The actual
  primary cause (missing parquet engine) was not in that list. Handoff fixes #3/#4 still apply as robustness
  (2018 chains use $5 strike increments; not every Friday was an expiry) and will be evaluated via D3.
- **RESOLVED via D3 — see E-1 below.** Starter tier caps at a rolling 5 years; 2018 data simply doesn't exist on this plan.

### I-2  Phase 6.5 free-signal jobs all died on wrong interpreter
- cross_section / insider / lead_lag / squeeze / climate logs show `ModuleNotFoundError: No module named 'redis'`
  and `pydantic_settings`. Root cause: they were launched before the py3.12 venv existed (used bare system python).
- **Fix:** re-run with `venv` python (pending). Also note `data.scanner` import of `data.tradier` was stale —
  already repointed to `data.marketdata` this session (the module was deleted in the MarketData migration).

---

## Diagnostics run (PC_OPUS_HANDOFF D1–D4)

- **D1** (logs): 1026× "No trading days" + 16× "trading_days SPY fetch failed" → parquet-engine failure was the
  dominant signature. Confirms I-1 primary cause.
- **D2** (cache): 0 parquet files, empty `_calendar/`. Chains were never fetched — `trading_days()` returned `[]`
  first and `simulate_trade` bailed. So empty cache is downstream of I-1, NOT independent proof of a data-access limit.
- **D3** (source on old dates): TRADING DAYS Q1 2018 = 0 but Q1 2025 = 61. 2018 chain → HTTP error/None.
  2024 control (535C exp 2024-06-21 as_of 2024-05-15) → bid 5.36 / ask 5.39 ✓. Integration works; history is the limit.
  Direct no-retry probe returned the API's own message: **402 "Starter users can only access up to 5 years of data."**
  Boundary: as_of 2021-06-01 = 402 (blocked); 2022-06-01 = 203, 414 contracts (works); 2023/24/25 all work.
  Candle endpoint earliest = 2021-06-16 (1255 rows) — same 5y cap.
- **D4** (signal logic, yfinance-only, free): SPY full history 1993→2026. HV-rank Mar 2020 = 100.0, VRP-z = 7.08
  (COVID spike screaming, as expected). **51 VRP trades generated for SPY 2018–2024.** Signal logic is CORRECT —
  the handoff's "algorithm broken" worst case is ruled out. Note `period="5y"` in `run_vrp_backtest` truncated
  yfinance to 2021+; `period="max"` returns full history.

---

## Fixes applied

- **F-1** `pip install pyarrow` (24.0.0) into venv — restores `trading_days()` parquet read/write AND the persistent
  disk cache (free re-runs / sweeps). Non-controversial; needed regardless.
- **F-2** `backend/data/scanner.py`: `from data.tradier import get_tradier` → `from data.marketdata import get_tradier`
  (the `data.tradier` module was deleted in the MarketData migration; scanner still imported it). Done earlier this session.

### Planned (pending V's window decision — see E-1)
- Fix `run_vrp_backtest`: `period="5y"` → full history, and compute VRP indicators on full history then gate ENTRY
  dates to [start,end] so warmup uses pre-window bars (legit PIT) instead of eating the first ~year of the window.
- Re-run VRP train + walk-forward on the **5-year-feasible** window.
- Evaluate handoff fixes #3 (strike-snapping) / #4 (3rd-Friday expiry) AGAINST a real 2022+ chain before changing —
  post-2021 SPY has $1 strikes + weekly expiries, so dollar-rounding/Friday may already match. Don't fix what isn't broken.

---

## Performance log

- VRP signal generation (D4): 51 trades/SPY over 2018–2024 from yfinance. ~40 names → expect ~1000+ trades on a
  multi-year window. Backtest runtime TBD after re-run.
- **Proof run (post-fix), SPY+QQQ 2022–2023:** 5 trades, all priced from real MarketData chains. metrics flowed
  (win_rate 1.0, total_pnl $558, DSR 0.51, mdd 0). 60 API fetches / 2 names / 2yr ≈ 15 credits/name/yr (then cached).
  **Plumbing CONFIRMED. The 5-trade metrics are NOT a verdict** — too few samples, benign low-vol sub-period inflates
  win_rate/Sharpe. Need full 40-name run for a meaningful DSR.

## Fixes applied (cont.)

- **F-3** `vrp_harvest.py`: indicators now computed on FULL yfinance history; entry dates gated to [start,end] via new
  `entry_start`/`entry_end` args (no more ~1yr warmup eating the window). `run_vrp_backtest` uses `period="10y"`
  (NOT "max" — bulk yfinance with max gives spurious 1927-start "possibly delisted" empties for 40 tickers).
- **F-4** `_next_45_dte_expiry` → 3rd-Friday monthly (was: nearest Friday). Weekly expiries didn't exist historically
  for many names (IWM etc.) → those chains 404 "no_data" → trades silently dropped. Evidence: raw probe showed
  IWM 2022-04-22 = 404 no_data while SPY same-era weeklies = 200. (Caveat: 3rd Friday shifts on holidays, e.g.
  2022-04-15 Good Friday → handled by F-5.)
- **F-5** Real-chain resolver (the proper fix for handoff #3 strike-mismatch + #4 expiry). New `generate_vrp_candidates`
  (single source of truth for the entry gate) + async `_resolve_candidate`: for each gate-fired date, query MarketData
  `get_expirations(as_of=date)` → snap to the real listed expiry nearest 45 DTE; load that chain → snap strikes to
  the real available strikes. Drops candidates with no listed chain (honestly unpriceable, not mispriced). Added
  `as_of` param to `MarketDataClient.get_expirations`. `generate_vrp_trades` kept (formula strikes) for tests/synthetic.

## Performance log (cont.)

- **Proof run v2 (post F-3/4/5), SPY+IWM 2022–2023:** 56/56 candidates resolved to real contracts (0 dropped, IWM
  included). 43 trades after simulation. **win_rate 0.767** (matches Carr-Wu canonical ~70%). Exit reasons:
  31 profit_target / 9 stop_loss / 3 forced_exit — we now capture the fat-left-tail losers, not just winners.
  Sharpe 1.98, DSR 0.089 (low only due to small 2-name sample vs num_trials=20 penalty). 250 API fetches / 2 names / 2yr.
- **pytest: 94/94 passed** after the refactor (handoff gate met).

## Credit budget note

- MarketData ratelimit: 10,000/day. After today's probes + proofs: **8989 remaining**.
- Full 40-name × 5yr both legs extrapolates to ~12.6k fetches → exceeds one day's budget.
- **Decision:** run a **20-name sector-diverse subset** for both legs (~6.3k fetches, fits today). ~900 trades is
  ample for a statistically meaningful DSR verdict. Cache persists, so expanding to 40 tomorrow (fresh 10k) is cheap.
  This is a scope/credit choice, not a strategy change. Universe halving noted for Opus review.

---

## Runbook phases completed

- Phases 0–4: complete (prior sessions).
- Phase 5 (MarketData historical chains smoke test): PASS — 3 dates returned real, differing bid/ask.
- Phase 6 (overnight jobs): launched, but VRP legs produced 0 trades (see I-1). DNA seed completed (107 symbols).
- Phase 6.5 free signal jobs: launched; status to be re-verified in D1.

---

## VERDICT — vrp_harvest (20-name, 5y window) — 2026-06-16

Gate: DSR > 0.5 train AND > 0.3 walk-forward. **RESULT: PASS (but marginal + risky).**

| Leg | Trades | Win rate | DSR | Sharpe | Max DD | Total PnL |
|---|---|---|---|---|---|---|
| Train 2021-07→2024-12 | 526 | 68.4% | **0.904** | 2.52 | 27% | $245,303 |
| Walk-fwd 2025-01→2026-06 | 215 | 67.0% | **0.317** | 1.39 | **51%** | $151,698 |

**Honest read (for Opus review):**
1. **PASSES the literal gate** → eligible for paper-trade stage, NOT live. 741 trades, win rates ~67-68% match the
   Carr-Wu canonical ~70%. The edge is real, not a plumbing artifact.
2. **Walk-forward DSR is razor-thin: 0.317 vs 0.30 threshold.** Large in-sample→OOS decay (0.90 → 0.32) — typical of
   a regime-dependent short-vol edge. Don't oversell it.
3. **51% max drawdown out-of-sample is a serious risk flag.** This is the short-strangle fat-left-tail biting even in
   a relatively calm 2025-26 window. stop_loss=2.0 (lose 2× credit) lets losers run. In a real crisis (which the 5y
   window EXCLUDES — no COVID/2018) it would likely be worse. Before any live sizing: tighter stops, smaller size,
   or switch naked strangle → defined-risk iron condor. Flag for V/Opus.
4. Credits: run consumed ~7,466 (8989 → 1523 remaining). 40-name run must wait for tomorrow's reset. Confirms the
   20-name subset decision was correct — 40 would have blown the daily cap mid-run.
5. Minor: some NFLX 2025-26 daily-mark chains 404'd late in the run (non-fatal — those days are skipped, trades still
   complete). Worth a look if NFLX-specific, but didn't affect the verdict.

**Recommended next step:** promote vrp_harvest to paper-trade stage WITH a risk-management revisit (drawdown), and
re-run on 40 names tomorrow to confirm the walk-forward DSR holds with broader breadth. Do NOT go live on this alone.

---

## Escalated to V / open questions

- **E-1 [ANSWERED, awaiting V's window decision]:** MarketData Starter caps at a **rolling 5 years**
  (its own 402 message: "Starter users can only access up to 5 years of data."). Usable window ≈ **2021-06-17 → today**,
  real clean chains. The originally-planned 2018–2024 train fold is impossible on this tier.
  Options for V:
    1. **(Recommended)** Shift validation window to fit 5y: train ≈ 2021-07 → 2024-12 (~3.5y), walk-forward
       2025-01 → today (~1.5y). Free, uses data we already pay for, ~1000+ VRP trades → DSR is computable.
       **Caveat:** excludes COVID-2020 and 2018 vol-mageddon — the two best VRP tail/crisis stress tests.
       The backtest can't prove crash behavior; that risk shifts onto the walk-forward + paper-trade gate.
    2. Upgrade MarketData tier (their msg implies higher tiers exceed 5y; cost/depth unconfirmed).
    3. ThetaData (~$80/mo) for deep 2018+ history — bigger integration lift.
  Handoff pre-authorized option 1 as acceptable. Recommending option 1; flagged the COVID-exclusion caveat for Opus review.

---

## 2026-06-17 (PC, fresh 10k credits) — V's three-task batch

### Cache survived overnight ✓
backend/data/marketdata_cache: **122 MB, 11,492 parquet files**, all 40 tickers present.
The 20-name naked run is fully cached (20 names @ 276+ chains each). Iron-condor variant runs ~free.

### TASK 1 — Iron-condor VRP variant — **VERDICT: FAIL (do not promote)**
New file: `backend/backtest/strategies/vrp_harvest_ic.py`. Apples-to-apples by construction:
same entry gate (reuses `generate_vrp_candidates`), **same short strikes** (reuses `_strangle_strikes`),
**same expiry** (resolved from the on-disk cache, not get_expirations → $0 + identical contract to naked),
plus long wings 1σ further OTM (≈5Δ at 45 DTE/30% vol) snapped to a real listed strike beyond the short.
Note: cached historical chains carry **delta == 0** (MarketData Starter returns no greeks on history), so
wings are placed by moneyness — same language the naked run used. Can't select by real 5Δ.

20-name results (same windows as naked):
| Leg | Trades | Win | DSR | max_dd | PnL |
|-----|--------|-----|-----|--------|-----|
| Train 2021-07→2024-12 | 332 | 48.5% | ~0 | 33.9% | **−$33,837** |
| Walk-fwd 2025-01→2026-06 | 153 | 47.7% | ~0 | 14.7% | **−$13,412** |

vs naked: +$245,303 / +$151,698, DSR 0.904 / 0.317, win 68% / 67%.

**The 1σ iron condor converts a profitable vol harvest into a net loser.** Why (economic, not a bug):
- Wings eat the premium — net credit becomes thin relative to the 4-leg cost (commission $5.20/trade +
  0.5×half-spread slippage on 4 legs). E.g. TSLA 2023-01: 15-wide condor for a **$5.10** credit.
- Capping the tail also caps the premium that made naked work; win rate falls 68%→48%.
- stop_loss=2.0×(net credit) is now LOOSER than the structural max loss, so the stop never protects;
  breached condors lose near-max.
- Tail-capping IS real (walk-forward max_dd 51%→15%), but worthless when the strategy loses money.

**Data-quality caveat (verified, doesn't change verdict):** deep-OTM wings are illiquid historically.
On a 98-trade NVDA/TSLA/AMD/AAPL/MSFT sample: **6/98 trades exceed the structural max loss** (missing wing
quotes → engine falls back to last mark) and **13/98 exit via `data_end`** (quote gap). Worst artifact:
TSLA 2022-05-05 lost $2,191 vs $998 theoretical max. Removing artifacts reduces the loss magnitude but
does NOT flip the sign — 48% win + capped upside is negative-EV regardless. Verdict robust.

**Recommendation:** 1σ IC is a NO. If V wants defined risk, the path is **wider/cheaper wings (2–2.5σ tail
insurance)** that preserve most of the naked credit while capping only the catastrophic tail — but those are
even deeper OTM (worse historical quote coverage), so test carefully. Otherwise keep **naked VRP + smaller
size + tighter stop** as the production path. Do NOT touch signal_registry.py — V's call.
Credit cost of this task: api_fetches 373 (holding-day chains the naked run exited before reaching). Not $0,
but ~373 credits — wings themselves were free from cache.

### TASK 2 — 40-name confirmation — credit estimate (NOT yet launched; needs V)
Real anchor from naked run: **6.78 credits/candidate** (7,466 cr / 1,101 cached-20 candidates).
New 20 names (DIA AVGO INTC MU GS MS WFC CVX JNJ PFE ABBV HD KO PEP MCD CRM ORCL BA CAT MMM):
**1,146 candidates → ~7,771 credits both legs** — OVER V's 7,000 cap (under the 10k daily budget though).
Walk-forward leg only = 322 candidates ≈ **~2,180 credits** (directly answers "does walk-forward DSR hold
with breadth"). Awaiting V's decision on scope before spending. (original 20 are cached → free.)

### TASK 3 — Free signal batch (momentum_12_1, PEAD, skew_25d, insider, lead-lag) — pending, $0 MarketData.

(expanded ↓)

#### TASK 3 detail
No equity-signal backtest harness exists (backtest/engine.py is options-only; cross_section_job.py computes
signal *values for today* + persists ranks, NOT forward-return DSR). Each "backtest" needs a harness built.

**DATA BLOCKER (verified):** cached historical MarketData chains carry `mid_iv == 0` AND `delta == 0` on every
row sampled — Starter returns bid/ask/OI/volume but **no IV / no greeks on history**. So:
  - `skew_25d` "from cached chains" is NOT possible (needs 25Δ put/call IV). Recoverable only via BS-inverting
    IV from option mid (underlying_price IS cached → real work) or a greeks source (ThetaData). Same blocker
    hits iv_call_put_spread, iv_term_slope, chain-based vrp_z. (Naked VRP sidesteps it: HV proxies for the
    gate + real bid/ask for pricing — never needed historical greeks.)
  - FMP_API_KEY is live (32 chars) → PEAD + insider are data-feasible (harness TBD).

**momentum_12_1 — SANDBOX (no edge on this narrow universe).** New: backtest/strategies/momentum_xs.py
(Jegadeesh-Titman 1993, monthly quintile long-short, strict PIT, DSR via same deflated_sharpe as VRP).
36 single names. Train: 42mo, win 59.5%, +15.6%, annSharpe 0.30, DSR 0.084, maxdd 44.4%.
Walk-fwd: 16mo, win 37.5%, +18.2%, annSharpe 0.46, DSR 0.089, maxdd 31.4%. DSR ~0.08 << 0.3 gate — BUT
36 names is too narrow for a real momentum factor and 2022 was a momentum-crash year. Inconclusive, not a
hard kill; proper test needs the full scan universe (free yfinance) — next step.

Remaining (not run): PEAD (FMP+yf), insider (FMP+yf), lead-lag (yf) — harnesses TBD. skew_25d — BLOCKED.

#### TASK 2 RESULT — 40-name naked walk-forward — DSR HOLDS, but tail gets WORSE
2025-01-01 → 2026-06-17, 40 names. **430 trades, win 59.3%, DSR 0.309, Sharpe 1.15, max_dd 73.6%, PnL +$115,062.**
Credit cost: api_fetches 1,651 (UNDER the ~2,180 estimate; cached 20 free).

Comparison to the 20-name walk-forward (215 trades, win 67%, DSR 0.317, max_dd 51%):
  - **DSR survives breadth: 0.317 → 0.309** (still > 0.30 gate). The edge is NOT an artifact of the original
    20-name selection — it's real across a 40-name sector-diverse universe. This is the confirmation V wanted. ✓
  - **BUT win rate fell 67% → 59.3%** (the added 20 are lower-vol / less liquid → weaker per-name VRP), and
  - **max drawdown got MUCH WORSE: 51% → 73.6%.** Critical insight: adding names did NOT diversify the tail.
    Short-vol drawdowns are a COMMON FACTOR — when vol spikes, every short-strangle loses together, so more
    names = more correlated tail exposure, not less. Breadth amplifies the crash, it doesn't soften it.

### CONSOLIDATED VERDICT (after today's work)
1. Naked VRP edge is REAL and robust to breadth (DSR ~0.31 on both 20 and 40 names). Passes the gate.
2. Tail risk is SEVERE and worsens with breadth (51%→74% dd). Not diversifiable by adding names.
3. The naive defined-risk fix (1σ iron condor) DESTROYS the edge (net loss). Ruled out.
4. => Production path: naked VRP with EXPLICIT tail management — fractional Kelly size (already in system),
   tighter stop, vol-regime entry gate (don't open new shorts when realized/implied vol is spiking), and/or
   SPARSE far-OTM tail hedges (2–2.5σ, cheap — NOT 1σ). PAPER-TRADE first. Do NOT go live unhedged.
   signal_registry.py untouched — promotion is V's call.

Approx MarketData credits used today: ~2,400 (IC 373 + 40wf 1,651 + sanity/diagnostics ~few hundred).
Well under 10k; plenty left for free-signal work (yfinance/FMP = $0 MarketData).

---
## 2026-06-17 (PC Opus, ownership session) — Phase A harnesses + FMP finding

NEW FILES: backtest/equity_engine.py, backtest/strategies/momentum_xs_v2.py,
backtest/strategies/pead.py, backtest/strategies/insider.py.
EDITS: vrp_harvest_ic.py now parametric (wings_sigma = wing distance from spot in
sigma units; replaces fixed wing_sigma_mult). scripts/run_full_validation.py:
shared+sequential VRP source (avoids N-fold re-fetch), REPORTS_DIR=repo-root,
universe-kwarg-collision fix, get_full_universe (~150 liquid) instead of alphabetical
get_scan_universe()[:N], dropped pre_fomc grid entry, added --vrp-universe.

FMP API BREAKAGE (app-wide, important):
  Legacy v3/v4 endpoints 403 since FMP's Aug-2025 migration. Affects insider_flow,
  short_squeeze, fundamental, lt_scoring, stock_dna, analyst_targets, calendar.
  New stable API: stable/earnings (works, PEAD source), stable/profile (works),
  stable/insider-trading/search (402 - not on V's tier). 
  => PEAD validated via stable/earnings. insider + squeeze BLOCKED (tier/data).

DATA RECAP (from yesterday, still true): cached MarketData historical chains carry
mid_iv==0 AND delta==0 (no historical greeks on Starter). skew/term/IV-spread family
blocked unless IV is recovered by BS-inversion from option mid prices (building now).
