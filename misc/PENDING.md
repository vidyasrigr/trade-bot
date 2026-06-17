# Pending Tasks Tracker

Single source of truth for what's done and what's left. The companion script
`backend/scripts/status.py` reads the actual filesystem/env and updates the
"detected" status below — run it any time with:

```bash
cd backend && python3 -m scripts.status
```

Last updated by hand: 2026-06-15

---

## 🟢 Setup you can do today (no code, ~30 min)

- [ ] **Set `FMP_API_KEY`** in `backend/.env` — driving fundamentals, insider data, earnings (Starter $14/mo recommended)
- [ ] **Set `DISCORD_WEBHOOK_URL`** — receive 🔴 signal contamination alerts
- [ ] **Change `SECRET_KEY`** from the default in `backend/.env` — auth JWT
- [ ] (already have: `ANTHROPIC_API_KEY`, `FRED_API_KEY`, `MARKETDATA_API_KEY`, `ALPHA_VANTAGE_API_KEY`)
- [ ] **Pip install missing deps**:
  ```bash
  pip install duckdb lightgbm feedparser redis pytest pytest-asyncio
  ```
- [ ] **Pull QwQ-32B on the 5080** for better adversary reasoning:
  ```bash
  ollama pull qwq:32b-q3_k_m
  # Then in .env: OLLAMA_ADVERSARY_MODEL=qwq:32b-q3_k_m
  ```

---

## 🟡 Database migrations (run once, in order)

```bash
psql $DATABASE_URL -f backend/db/init.sql
for f in backend/db/migrations/*.sql; do psql $DATABASE_URL -f "$f"; done
```

- [ ] `init.sql` — base schema
- [ ] `004` — stock DNA, LT pipeline
- [ ] `005` — agent monitor
- [ ] `006` — users + auth
- [ ] `007` — backtest_runs
- [ ] `008` — conviction calibration
- [ ] `009` — strategy_overrides
- [ ] `010` — Phase A cleanup (drops dead columns, creates seed_lessons)
- [ ] `011` — signal_ranks (cross-section)
- [ ] `012` — insider_signals + lead_lag_edges
- [ ] `013` — model_runs (LightGBM)
- [ ] `014` — phase F ops (signal_status column)
- [ ] `015` — regime_forecasts (Markov)
- [ ] `016` — whale_flow + short_squeeze + reddit signals

---

## 🟠 Bootstrap (once, ~30 min wall time)

- [ ] **Backfill 700 days of features**:
  ```bash
  cd backend && python3 -m scripts.backfill_feature_store --days 700 --max-symbols 500
  ```
- [ ] **First LightGBM train** (otherwise sits idle until next Sunday):
  ```bash
  python3 -c "import asyncio; from scoring.ranker import retrain_ranker; print(asyncio.run(retrain_ranker()))"
  ```
- [ ] **First Markov regime fit**:
  ```bash
  python3 -c "import asyncio; from analysis.regime_markov import run_regime_markov_job; print(asyncio.run(run_regime_markov_job()))"
  ```
- [ ] **First signal audit** — should return all-clear:
  ```bash
  python3 -m scripts.audit_signals
  ```

---

## 🔴 Validation — the only thing that actually proves the system works

- [ ] **Run VRP harvest backtest 2018-2024** (train fold)
- [ ] **Walk-forward VRP harvest 2025-01 → 2026-06** (out-of-sample)
- [ ] **Run sweeper on 27-variant grid for VRP** — pick variants with DSR > 0.5 and consistent across both folds
- [ ] **Repeat for skew_25d / momentum_12_1 / PEAD / pre-FOMC straddle**
- [ ] **Promote 2-5 signals that survive both folds** to `paper` status
- [ ] **Paper-trade survivors 4 weeks** — track Brier score on conviction
- [ ] **Calibration check**: realized win rate per conviction decile within 5% of midpoint?
- [ ] **Promote winners to live small** ($500-1k per trade) → 8 weeks
- [ ] **Promote to live full** based on rolling DSR

**Realistic timeline: 2-3 months** to a system you can actually trust.

---

## 🟣 Optional improvements (only when first quarter is profitable)

- [ ] **Unusual Whales $48/mo** — clean sweep tape replaces DIY whale_flow
- [ ] **ORATS / LiveVol** — clean historical vol surfaces
- [ ] **EarningsWhispers $30/mo** — pre-announce consensus drift
- [ ] **CRSP** — fixes yfinance survivorship bias (institutional pricing)
- [ ] Build LSTM per-stock vol forecast on the 5080
- [ ] Build 8-K full-text classifier with Qwen3-14B
- [ ] Build pairs-trading engine (stat-arb)
- [ ] Build gamma-squeeze detector (needs UW for cleanest input)

---

## 🆕 Future TODOs (organized by phase — execute in order after validation succeeds)

### Phase O — Real-time / Daily operations (5 items, ~250 LOC total)

- [ ] **O.1 — Intraday Discord alert for tail-stack setups.** Why: daily briefing is morning-only; conviction-100 setup at 2pm waits until next morning. How: new `agents/intraday_alerter.py` polls scanner cache every 30 min; when ANY symbol shows conviction > 85 AND independent_signals ≥ 6 AND tail_signal_aligned, push to Discord with the rec id. ~100 LOC.
- [ ] **O.2 — Slippage tracking on live fills.** Why: predicted entry vs actual fill divergence is the live-vs-backtest gap. Already have infra (recommendation_outcomes.expected_vs_actual). Just needs a UI input. How: extend `frontend/components/OrderTicket.tsx` with "Record actual fill" field; POST to new endpoint `/api/recommendations/{id}/fill`. ~30 LOC + 20 frontend.
- [ ] **O.3 — End-of-day Discord recap.** Why: morning briefing only. Don't know what filled, closed, drifted. How: new `run_daily_eod_recap` in main.py, schedule at 16:30 ET; Discord embed with today's fired recommendations, today's closures, top 3 winners/losers of resolved trades. ~80 LOC.
- [ ] **O.4 — Model quality monitoring.** Why: Claude/Qwen output quality drifts; you don't notice until trades go bad. How: extend `agents/agent_monitor.py` to track parse-failure rate, structured output validation rate, content length collapse per model_id over rolling 7d. Discord alert if >5% degradation. ~120 LOC.
- [ ] **O.5 — Auto-dedup at recommendation persistence.** Why: ticket_guards module is built but not yet called. How: wire `scoring/ticket_guards.run_all_guards()` into wherever `log_recommendation()` is called (~10 LOC). Block critical, surface warnings.

### Phase P — News + event-typed catalysts (3 items)

- [ ] **P.1 — Event-typed news classifier (Qwen3-14B local).** Why: CRWV/NBIS Nasdaq-100 inclusion (June 11) was in our RSS but treated as generic score_delta. An `index_rebalance` detector would have flagged it. How: extend `data/news.py` ingest pipeline. New `analysis/news_classifier.py` runs Qwen3-14B over headline+summary, outputs `{event_type: 'index_rebalance' | 'fed_event' | 'm_and_a' | 'leadership_change' | 'regulation' | 'earnings' | 'guidance' | 'partnership' | 'litigation', severity: 0-100}`. Persist to new `news_events` table. ~200 LOC. Local-LLM, free.
- [ ] **P.2 — Nasdaq quarterly rebalance calendar.** Why: deterministic event-window (T-5 to T+30 around effective date). How: new `data/nasdaq_rebalance.py` scrapes Nasdaq's quarterly announcement page; adds `nasdaq_rebalance_window` flag. ~60 LOC, free.
- [ ] **P.3 — Fed chair speech tracker.** Why: Warsh-specific dovish/hawkish surprise scorer. How: extend `data/news.py` MACRO_RSS_FEEDS with federalreserve.gov speeches; new `analysis/fed_speech_scorer.py` runs Qwen sentiment per speech. ~100 LOC.

### Phase Q — Gaps Fable's blueprint flagged that we still haven't built (11 items)

Each item below has: **Why | How | LOC | Data source**.

- [ ] **Q.1 — Implied vs realized earnings move signal.** Why: per-name straddles systematically overprice earnings moves; Tier 1 per Fable. How: extend `analysis/earnings_adj_iv.py` to compute `implied/realized` ratio; fire short straddle when ratio > 1.3, long when < 0.8. Persist as `signal_ranks(signal_type='earnings_iv_premium')`. ~120 LOC. Data: existing MarketData chains + FMP earnings dates.
- [ ] **Q.2 — 0DTE / charm-vanna intraday flows.** Why: SPX 0DTE = 40%+ volume; predictable late-day drift in pinned regimes. How: new `analysis/charm_vanna.py`. Intraday hourly job pulls SPX 0DTE OI by strike, computes net gamma/vanna by strike, identifies pin candidates within ±0.5σ of spot. New `intraday_gamma_levels` table. ~200 LOC. Data: MarketData live SPX chain (extra credits).
- [ ] **Q.3 — FDA / PDUFA calendar overlay.** Why: biotech pre-PDUFA volatility expansion is documented; binary outcomes = clean event-window plays. How: new `data/fda_calendar.py` scrapes `fda.gov/drugs`. ~80 LOC, free.
- [ ] **Q.4 — Lockup expiration tracker.** Why: 6-month post-IPO lockup expiration historically causes 5-15% drop on insider selling. How: extend `analysis/ipo_halo.py`, parse S-1 filings for lockup date. ~60 LOC, free.
- [ ] **Q.5 — Govt contract awards.** Why: +3-10% pop on multi-billion contract awards (PLTR, RKLB, LMT etc.). How: new `data/usaspending.py` polls `api.usaspending.gov/api/v2/search/spending_by_award/`. ~150 LOC, free.
- [ ] **Q.6 — Deep Researcher agent (LT narrative thesis).** Why: `lt_scoring.py` returns a score but no thesis. Strategist would benefit from narrative context. How: new `agents/deep_researcher.py` runs Qwen3-14B over 10-K + earnings transcripts, outputs `{bull_thesis, bear_thesis, key_risks, moat_evidence}`. Cached 90d per symbol. ~200 LOC. Free (current quarter); $14/mo FMP upgrade for older transcripts.
- [ ] **Q.7 — 8-K full-text classifier on 5080.** Why: a single 8-K can be partnership (bullish) or CEO resignation (bearish) or routine filing (noise). How: see P.1 above — same module covers 8-K + RSS. ~included in P.1.
- [ ] **Q.8 — Google Trends.** Why: spike in retail search precedes price moves on small/mid caps (Lopez-Lira 2023). How: new `data/google_trends.py` using `pytrends`. Weekly velocity per top 200 small/mid caps. ~50 LOC, free.
- [ ] **Q.9 — News-similarity dedup via embeddings.** Why: 1000 identical Reuters/Bloomberg/CNBC headlines on same Fed move shouldn't count as 1000 sentiment hits. How: embed each headline via nomic-embed-text on Ollama, cluster cosine > 0.92, keep one rep. ~100 LOC, free.
- [ ] **Q.10 — StockTwits API.** Why: skews to active traders (vs Reddit retail); different signal. How: new `data/stocktwits.py`, same shape as `data/reddit.py`. ~80 LOC, free.
- [ ] **Q.11 — Regime Sentinel consolidated agent.** Why: we have pieces (vol_regime + Markov + stock_climate + market_weather) but no single declarative state saying "regime is X; active playbooks: VRP harvest + momentum; dormant: long-vol". How: new `agents/regime_sentinel.py`. Pre-market job; reads all pieces; outputs `{regime, active_playbooks, dormant_playbooks, rationale}`. Strategist prompt injects verbatim. ~150 LOC.

### Phase R — Gaps I see in current state (not flagged by Fable, 8 items)

- [ ] **R.1 — Briefing-level backtest ⭐ HIGHEST IMPACT.** Why: we backtest individual signals. Production output is the daily briefing. Realized DSR of the briefing ≠ sum of individual signal DSRs (dedup, conviction stacking, ranker tilt all interact). **The single most important number we never measure.** How: new `backtest/strategies/briefing_replay.py` replays the pipeline against feature_store, tracks actual top-5 picks per day, computes forward returns + DSR. ~250 LOC.
- [ ] **R.2 — Per-name execution cost calibration.** Why: flat half-spread is wrong by 10x. SPY: 0.5%. Illiquid biotech: 8%. Backtest cost is wrong. How: extend `backtest/marketdata_source.py` — average bid-ask % per (symbol, expiry-bucket) from cached chains; use this instead of flat 5%. ~80 LOC, uses existing cache.
- [ ] **R.3 — Capacity modeling.** Why: at what size does our trade move the market? How: extend `analysis/liquidity_gate.py` — `max_contracts_safe = min(0.05 × OI, ADV-fraction-of-orderbook)`. ~30 LOC.
- [ ] **R.4 — Correlation-aware portfolio Kelly.** Why: 5 NVDA-correlated longs sized like 5 independent bets is dangerous. How: extend `scoring/weighted.py::_kelly_size` — pairwise correlation with open positions, reduce kelly_fraction by `(1 - mean_correlation)`. ~80 LOC.
- [ ] **R.5 — Regime-change detector for live positions.** Why: if market shifts chop → crisis at 11am, open VRP strangles run into the vol explosion. How: new `agents/regime_change_watcher.py` every 30 min, compares current `market_weather` to morning. Discord alert on transition + suggested defensive actions. ~100 LOC.
- [ ] **R.6 — Model uncertainty / confidence intervals.** Why: LightGBM gives point estimates. p=0.55 trade ≠ p=0.95 trade but we size identically. How: switch `scoring/ranker.py` from `LGBMRegressor` to quantile regression at p=0.25/0.5/0.75, OR conformal prediction wrapper. CI width feeds confidence_multiplier on sizing. ~120 LOC.
- [ ] **R.7 — Dividend handling for LT positions.** Why: ex-div affects total return + short-call early assignment risk. How: extend `analysis/calendar.py` to fetch dividend calendar from FMP; ticket builder checks for ex-div in window. ~50 LOC.
- [ ] **R.8 — Survivorship bias permanent fix.** Why: backtests on full universe overstate edge 2-5%/yr. How: integrate Norgate ($30/mo) OR scrape Russell rebalance dropouts. ~150 LOC (Norgate) or 400 (scrape).

### Phase S — Polish / lower-priority

- [ ] LLM agent graph tests (fragile mocking — wait until prompts stabilize)
- [ ] Full DB fixture infrastructure (half-day setup, low value pre-revenue)
- [ ] VCR-style HTTP recordings (useful for CI; not critical solo)
- [ ] Russell rebalance calendar wiring
- [ ] Term-structure inversion harvest (~20 LOC once you want it)
- [ ] CFTC COT → ticker mapping (CUSIP DB needed via OpenFIGI)
- [ ] CBOE COR1M data feed for sector_dispersion compound signal
- [ ] Tax-loss harvesting / wash-sale tracking (live trading only)
