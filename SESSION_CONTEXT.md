# Session Context — Read This First

**Purpose**: any new Claude Code session (Haiku/Sonnet/Opus, on V's laptop OR PC) reads this first to inherit the prior session's context without losing the thread.

V cannot transfer my live session memory across machines. But the docs below collectively *are* the persistent memory — read them in this order and you'll inherit ~95% of where we are.

## Who's working with whom

- **V (Vidyasri)** — AI engineer, system designer
- **N (Vidyasri's partner)** — actual trader, executes trades from app output
- **Sonnet/Opus on laptop (me)** — system architect; writes/audits code; main session
- **Haiku on PC** — operational runner; follows runbooks; doesn't invent code

## Project: `/Users/V/Projects/Options` — agentic trading research system

**Goal**: surface high-conviction signals across 3 streams (options / swing / LT) on the ~6,900-stock NASDAQ universe. Output executable trade tickets for N to place manually. Not a bot, no autonomous orders.

**Hardware**: RTX 5080 PC (16GB VRAM), runs Postgres + Redis + Ollama + the backend.

**Budget**: ~$30-44/mo total ops (MarketData $30 + optional FMP Starter $14).

## Where we are RIGHT NOW (as of 2026-06-16 ~1pm PT)

1. **Phases A-L done**: code is feature-complete for validation phase. 49 signals registered, 17 migrations exist, 94 pytest tests pass, signal audit machinery wired.
2. **Phase L just shipped**: per-stock climate + market weather (this session).
3. **V is bootstrapping the PC**: Phases 0-4 of `OVERNIGHT_RUNBOOK.md` complete; stuck at Phase 5 waiting for MarketData API key.
4. **Next action**: Haiku launches FREE signals + waits for MD key, then runs VRP backtest legs.

## The four files to read, in order

1. **`/Users/V/Projects/Options/OVERNIGHT_RUNBOOK.md`** — exact bash commands for the PC. Phases 0-6, idempotent. Haiku follows this verbatim.
2. **`/Users/V/Projects/Options/misc/WEEK1.md`** — day-by-day expectations for this week.
3. **`/Users/V/Projects/Options/misc/PENDING.md`** — checklist + future TODOs (news classifier, Nasdaq rebalance detector, Fed speech tracker).
4. **`/Users/V/Projects/Options/misc/PARALLEL_VALIDATION_PLAN.md`** — the data-dependency map showing which signals share chain fetches and which run on yfinance for free.

## Hard rules

1. **No mock data anywhere.** mockData.ts was deleted Phase A. Anything that looks like fake numbers in output = bug.
2. **No code from YouTube/Discord/Substack without a peer-reviewed citation.** Signals must have a research anchor; see `scoring/signal_registry.py`.
3. **Backtest must use point-in-time data.** No yfinance "today's price" sneaking into past dates. The H5 PIT discipline must hold.
4. **Never modify `/Users/V/Projects/Options` directly without V's explicit consent** unless a runbook says to.
5. **Treat sandbox signals as observe-only.** They must have `influences_conviction=False` in the registry. Audit fires red alert otherwise.

## Quick architecture summary (one paragraph)

5-stage scanner funnel: ~6,900 stocks → stage1 momentum/vol screen → stage2 quick technical → stage3 catalyst/political/halo → stage4 deep LangGraph (4 analysts + adversary + rebuttal + risk officer using Claude Opus/Sonnet or local QwQ) → top 5-10 executable tickets. Signals fan out into 6 buckets (engine, overlay, cross-section, compound, dna, strategy) and feed `compute_final_score` with IC-weighted ranking, 3-signal confirmation gate, anti-crowding penalty, half-to-full Kelly sizing (tail-aligned). Backtester is async multi-leg with deflated Sharpe; sweeper parallelizes parameter grids. Point-in-time feature store (DuckDB/Parquet) for LightGBM ranker training.

## The validation gate

Every signal goes through: backtest → DSR > 0.5 train + > 0.3 walk-forward → paper trade 4 weeks → live small → live full. Demotion on rolling DSR < 0 for 30 days. **No signal escapes this without evidence.**

## Where my session memory persists outside this file

| Where | What it remembers |
|---|---|
| Code in `/backend` | The system itself |
| `/backend/db/migrations/` | Schema history (017 migrations) |
| `/backend/scoring/signal_registry.py` | Every signal declared + status |
| `/backend/tests/` | 94 invariants any session must preserve |
| `/misc/` | All planning + assessment docs |
| `/OVERNIGHT_RUNBOOK.md` | The recipe for operational runs |
| Auto-memory at `~/.claude/projects/-Users-V-Projects-Options/memory/` | V's profile + collaboration style |

## How to be useful in V's words

- **Brutally honest**, never flatter
- **Recommend specific options first**, then explain the trade-off
- **No emojis unless V uses them first**
- **Don't write code unless asked or unless the runbook says to**
- **For UI/frontend changes, test in the browser** before claiming success
- **If unsure, ask** rather than guess

## Open questions for any new session

1. Did the MarketData smoke test pass (Phase 5)? — check `data/backtest_reports/`
2. Are any of the overnight backtests done? — check log files
3. What's the current `python3 -m scripts.audit_signals` output? — should be all-clear

Read those three before doing anything else. That's the resume point.
