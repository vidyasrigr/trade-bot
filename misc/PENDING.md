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

## ⚪ Deferred (do NOT do until validation succeeds)

- [ ] LLM agent graph tests (fragile mocking — wait until prompts stabilize)
- [ ] Full DB fixture infrastructure (half-day setup, low value pre-revenue)
- [ ] VCR-style HTTP recordings (useful for CI; not critical solo)
- [ ] Russell rebalance calendar wiring
- [ ] Term-structure inversion harvest (~20 LOC once you want it)
- [ ] CFTC COT → ticker mapping (CUSIP DB needed via OpenFIGI)
- [ ] CBOE COR1M data feed for sector_dispersion compound signal
