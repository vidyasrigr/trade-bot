# Parallel Validation Plan

**TL;DR**: I was thinking sequentially when I shouldn't have been. Most signals share input data, so they can be backtested **simultaneously** from one MarketData chain fetch. Plus the entire **swing + long-term streams** can be backtested in parallel on yfinance for **free** while the options backtest runs.

Real timeline with proper parallelism: **3-4 days to validate ~15 signals across all 3 streams**, not 6 weeks.

---

## Table 1 — Options & Swing Signals (Data Dependencies)

Each row = one signal. Columns = data source it needs. **Same colored highlight = can share a single fetch.**

| Signal | yfinance OHLCV | MarketData chain | FMP fundamentals | FMP insider | EDGAR | FRED | Cost per ticker per year |
|---|---|---|---|---|---|---|---|
| **VRP-harvest** (Carr-Wu) | ✅ HV20 | ✅ chains @ 45 DTE | — | — | — | — | ~3k credits |
| **Skew shorting** (Xing-Zhang-Zhao) | ✅ | ✅ same chain | — | — | — | — | **shares VRP chain — $0 extra** |
| **IV-spread** (Cremers-Weinbaum) | ✅ | ✅ same chain | — | — | — | — | **shares VRP chain — $0 extra** |
| **IV term-slope** (Vasquez) | ✅ | ✅ chains @ 2 DTEs | — | — | — | — | +1k for second DTE |
| **GEX regime** (SqueezeMetrics) | ✅ | ✅ same chain | — | — | — | — | **shares VRP chain — $0 extra** |
| **Pre-FOMC straddle** (Lucca-Moench) | ✅ SPY only | ✅ SPY only @ FOMC dates | — | — | — | ✅ FOMC dates | ~50 credits total |
| **Earnings IV-crush** | ✅ | ✅ pre/post earnings | ✅ earnings dates | — | — | — | ~500 credits |
| **Momentum 12-1** (Jegadeesh-Titman) | ✅ | — | — | — | — | — | **$0 — free** |
| **PEAD** (Bernard-Thomas) | ✅ | — | ✅ earnings + beats | — | — | — | **$0 — free** |
| **Insider opportunistic** (Cohen-Malloy-Pomorski) | — | — | — | ✅ Form 4 | — | — | **$0 — free** |
| **Short squeeze** (Drechsler) | ✅ | — | ✅ short interest | — | — | — | **$0 — free** |
| **Whale flow** (Pan-Poteshman) | — | ✅ chain w/ vol/OI | — | — | — | — | **shares VRP chain — $0 extra** |
| **Supply-chain lead-lag** (Cohen-Frazzini) | ✅ | — | — | — | — | — | **$0 — free** |
| **Pairs trading** (cointegration) | ✅ | — | — | — | — | — | **$0 — free** |

**Key insight from the table**: 6 options signals share the same chain fetch. One MarketData call on SPY/2020-05-01 gives us data for VRP, skew, IV-spread, term slope, GEX, and whale flow simultaneously. **The marginal cost of adding more options signals is ZERO** as long as they use the same chain window.

And the 7 stock-only signals cost **$0** total because yfinance + FMP free tier covers them.

---

## Table 2 — Long-Term Investment Signals (Data Dependencies)

| Signal | yfinance | FMP fundamentals | FMP insider | EDGAR 13F | Backtest cost |
|---|---|---|---|---|---|
| **LT Score** (Piotroski + FCF + ROIC) | ✅ | ✅ qtr statements | — | — | $0 — free |
| **52-week high momentum** (George-Hwang) | ✅ | — | — | — | $0 — free |
| **Analyst revision cascade** (Womack) | — | ✅ estimates | — | — | $0 — free |
| **Insider executive buys** (CMP) | — | — | ✅ Form 4 + role | — | $0 — free |
| **13F smart-money crowding** | — | — | — | ✅ quarterly | $0 — free |
| **Quality momentum** (12-1 + Piotroski) | ✅ | ✅ | — | — | $0 — free |
| **Beat-and-raise PEAD** (small/mid only) | ✅ | ✅ | — | — | $0 — free |

**All 7 long-term signals can be backtested entirely for free.** Zero MarketData credits required.

---

## The Right Parallel Plan

### Day 1 (Monday)

**Foreground job — uses MarketData credits:**
- Pull chains for 5 tickers × 2018-2024 (train fold)
- **From one fetch, compute SIX signals simultaneously**: VRP, skew, IV-spread, term slope, GEX, whale flow
- Save 6 metrics per ticker
- ~15k credits

**Background jobs — zero credits, use yfinance + FMP free:**
- Backtest momentum 12-1 across **all 6,902 stocks** 2018-2024 (yfinance batch)
- Backtest PEAD across same universe
- Backtest insider opportunistic 2018-2024
- Backtest LT score (Piotroski etc.) 2018-2024
- Backtest 13F crowded names from EDGAR
- Backtest pairs trading on top 200 names
- Backtest supply-chain lead-lag

**EOD Monday**: you have 6 options signals validated on 5 tickers + 7 stock signals validated on the full universe.

### Day 2 (Tuesday)

**Foreground**: 5 more tickers options chain → 6 more signals × 5 tickers
**Background**: walk-forward (2025-today) of all 7 stock signals already done Monday

**EOD Tuesday**: 10 tickers options-validated + 7 stock signals walk-forward complete

### Day 3 (Wednesday)

**Foreground**: 5 more tickers + walk-forward for first 10
**Aggregate**: combine all 15 tickers + both folds → final DSR per signal

**EOD Wednesday**: **PROMOTE / OVERFIT / NO EDGE verdict on ~13 signals total** (6 options + 7 stock/LT)

### Thursday

Paper-trade everything that survived. Each signal is independent — paper-trade VRP, momentum, PEAD, insider in parallel from Thursday.

---

## What I should change in the runbook

The current Phase 6 runs only VRP. **It should run 6 options signals + 7 stock signals from the same data pulls.** Specifically:

1. The MarketData fetch in `MarketDataHistoricalSource` already returns chains with greeks, IV, vol, OI — **everything** the 6 options signals need. We're throwing away most of it. The backtest engine just needs to score each strategy against the same fetched chain.

2. The 7 stock signals don't need MarketData at all — they should run on yfinance batches in parallel from Day 1.

3. Per-ticker parallelism: 5 tickers × 6 signals = 30 backtests we can launch concurrently on Monday.

4. Across-ticker parallelism (GPU sweeper): each backtest config can run as a sweeper variant. **Asyncio handles 50+ concurrent backtests trivially on your 5080 box.**

---

## Real credit budget for full validation

| Stream | Signals | Total credits | Days on Starter (10k/day) |
|---|---|---|---|
| Options (6 signals × 15 tickers × 8.5 yrs) | VRP, skew, IV-spread, term, GEX, whale | ~50-70k (shared chains) | 5-7 |
| Swing/momentum (7 signals × 6,902 stocks × 8.5 yrs) | momentum, PEAD, insider, squeeze, lead-lag, pairs, revision cascade | **$0 — yfinance + FMP free** | concurrent |
| Long-term (7 signals × 6,902 stocks × 8.5 yrs) | LT score, 52w high, 13F crowding, etc. | **$0 — fundamentals only** | concurrent |
| Pre-FOMC + earnings IV-crush | special events | ~5k | concurrent with VRP |
| **TOTAL** | **20 signals across all 3 streams** | **~55-75k** | **3 days end-to-end** |

The $30 Starter plan covers EVERYTHING across all 3 streams. **Not just VRP.**

---

## My honest mistake earlier

I was treating each options signal as a separate full backtest needing fresh chain data. That's wrong — one chain fetch is shared across 6 options signals. And I was completely silent on swing/LT validation, which costs **nothing** and could be done in parallel from day 1.

The runbook needs three updates to reflect this:

1. **Phase 6.3** should run a multi-signal backtest harness (not single VRP)
2. **New Phase 6.5** for stock/swing signal batch (yfinance, zero credits)
3. **New Phase 6.6** for LT signal batch (FMP fundamentals, zero credits)

Want me to rewrite the runbook now or wait for your overnight VRP results first to confirm the engine works?
