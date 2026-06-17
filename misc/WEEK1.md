# Week 1 — What to Expect Day by Day

Today: **Mon 2026-06-16, ~1pm PT**. V's PC is paused at OVERNIGHT_RUNBOOK Phase 5 waiting for MarketData API key.

This doc tells V exactly what each day's output should be, what to look at, and what action to take.

---

## TODAY — Mon 6/16 by EOD (~6pm PT)

### Without MarketData key (free signals only)

| What Haiku runs | Output file | What V should look at |
|---|---|---|
| Cross-section job (6 signals: vrp_z, skew_25d, iv_term, iv_call_put_spread, momentum_12_1, vrp_level) | `signal_ranks` table | `SELECT signal_type, COUNT(*) FROM signal_ranks WHERE as_of_date=CURRENT_DATE GROUP BY signal_type;` should show 6 rows × ~1000 symbols each |
| Insider opportunistic detector | `insider_signals` table + signal_ranks `insider_cluster` | `SELECT symbol, n_distinct, confidence FROM insider_signals WHERE cluster_date >= CURRENT_DATE - 30 ORDER BY confidence DESC LIMIT 10;` — these are real names with current insider buying clusters |
| Lead-lag graph rebuild | `lead_lag_edges` table | `SELECT leader, follower, lag_days, correlation FROM lead_lag_edges WHERE computed_on=CURRENT_DATE ORDER BY ABS(correlation) DESC LIMIT 20;` — top 20 learned supply-chain edges |
| Short squeeze detector | `short_squeeze_signals` table + signal_ranks `short_squeeze` | `SELECT symbol, si_pct_float, confidence FROM short_squeeze_signals WHERE confidence > 70 AND as_of_date=CURRENT_DATE;` — current squeeze setups |
| Per-stock climate + market weather | `stock_climate` + `market_weather` tables | `SELECT climate, COUNT(*) FROM stock_climate WHERE as_of_date=CURRENT_DATE GROUP BY climate;` — distribution of stocks across bull/bear/chop/squeeze/high_vol |

**EOD action for V**:
1. Run `python3 -m scripts.audit_signals` → should be all-clear
2. Eyeball top insider clusters, top squeeze setups, today's market weather
3. Paste MarketData key into `.env` when ready — Haiku resumes Phase 5

### Realistic timeline if key arrives today

- **Key arrives by 3pm PT** → Phase 5 smoke test runs (1 min), Phase 6 launches → ~4 hours of credits burning overnight on VRP
- **Key arrives after 6pm PT** → only free signals run today, options backtests start tomorrow

---

## Day-by-day expectations through Sat 6/21

| Day | What runs | What V sees | Action |
|---|---|---|---|
| **Mon 6/16** | Free signals (above) + MarketData smoke test if key arrives | Today's signal rankings, climate map, insider clusters | Eyeball signal_ranks, check audit |
| **Tue 6/17** AM | VRP train fold (2018-2024) starts on 5 tickers (SPY, QQQ, AAPL, MSFT, NVDA) | Partial results EOD | `tail -30 data/backtest_reports/vrp_leg1_train.log` |
| **Tue 6/17** PM | **Fed press conf (Warsh first)** — watch volatility expansion | Live market reaction; system briefing should call it out | Read `/api/briefing/daily` text |
| **Wed 6/18** | VRP train continues (5 more tickers); WF starts on Tue's 5 | 10 tickers train-validated, 5 tickers WF | Check per-ticker DSR if available |
| **Thu 6/19** | VRP completes (last 5 tickers + all WF) | Final aggregated metrics across 15 tickers | Run morning verdict template in RUNBOOK |
| **Fri 6/20** | **Verdict day** — PROMOTE / OVERFIT / NO EDGE on VRP | Begin paper trading if PROMOTE | If PROMOTE: write small live ticket via `/api/trades/paper/open`; if SANDBOX: tune sweeper variants |
| **Sat 6/21** | **Nasdaq-100 rebalance effective date** — CRWV, NBIS, RKLB, ALAB, TER added; CHTR, CTSH, INSM, VRSK, ZS removed | Use this as a *test event* — does our scanner flag the added names? | Check if Mon 6/22 scan results boost CRWV/NBIS/RKLB |

---

## VRP DSR scorecard — what to do at each verdict

| Verdict | Train DSR | WF DSR | Action |
|---|---|---|---|
| **STRONG PROMOTE** | > 0.70 | > 0.50 | Paper trade at $1k/trade Fri; live small at $500/trade Mon 6/23 |
| **PROMOTE** | > 0.50 | > 0.30 | Paper trade at $500/trade Fri; full 4-week paper before live |
| **WEAK** | 0.35-0.50 | 0.35-0.50 | Sandbox + try sweeper variants over weekend; revisit Mon |
| **OVERFIT** | > 0.50 | < 0.30 | Sandbox VRP; move on to next signal (skew, PEAD, momentum) |
| **NO EDGE** | < 0.35 | < 0.35 | Sandbox; investigate engine first (smoke test may have lied) |

---

## Critical things to look at by EOD today

1. **Signal audit** — `python3 -m scripts.audit_signals` should print `✅ No issues detected.` If 🔴 critical findings, contamination = STOP.

2. **Market weather** — Should print something like:
   - `weather: chop  vix: 18.4  spy_ret_20d: 0.012`
   - Confirms data pipelines work
   - Watch the Fed press conf tomorrow — weather will probably flip if surprise

3. **Stock climate** — Should print 5-class distribution like:
   - `bull: 312  chop: 421  bear: 145  squeeze: 8  high_vol: 76`
   - Roughly aligned with current market: if VIX < 20 and SPY at ATH, bulk should be `bull` or `chop`

4. **Insider clusters** — 5-15 names with `confidence > 70` from the last 30 days. These are real buying opportunities surfaced by the system **today**.

---

## What V should NOT expect this week

- ❌ Full backtest of all 18 signals (only VRP this week)
- ❌ Statistical confidence intervals on signal interactions
- ❌ Live trading at scale (paper only)
- ❌ Profit/loss reports (paper-trade trades just started Fri at earliest)
- ❌ Any improvement to news classifier (PENDING item, next session)

## What V SHOULD see by Sun 6/22

- ✅ 1-2 signals validated with DSR > 0.5 (most likely VRP harvest)
- ✅ 5+ signals computing daily rankings (cross-section + insider + squeeze + climate + lead-lag)
- ✅ Paper trades opening on the validated signals
- ✅ Daily briefing JSON at `/api/briefing/daily` showing top picks across all 3 streams (options / swing / LT)
- ✅ Empty postmortems table (no closed trades yet — 1-2 weeks from now)
