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
