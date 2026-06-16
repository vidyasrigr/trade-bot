# Agentic Trading Research System — 2026 Clean-Sheet Assessment

A from-first-principles design for a private edge-discovery and trade-ticket generator for 2 traders (V designs, N executes), covering 3 streams:
1. **Options strategies** (spreads, condors, LEAPS, directional)
2. **Swing/mid-term stock trades** (1–4 weeks)
3. **Long-term investments** (3–18 months)

Scans the full NASDAQ universe (~5,000 names) nightly. Not a bot — output is a daily briefing of executable trade tickets a human places manually. Budget: up to $200/mo. Hardware: RTX 5080 (16GB VRAM) for local LLM work.

---

## Part 0: Brutal honesty (read this first)

The stated goal — "30–100% safe trades and 2x–10000x ambitious ones, all with high confidence" — needs recalibration, because building toward a fantasy produces an overfit system that loses money:

1. **30–100% return on defined-risk option structures is a payoff shape, not an edge.** A debit spread bought at $0.40 paying $1.00 is +150% — and the market prices that at roughly fair odds. The *edge* is winning 56% of the time when the market prices 50%. Realistic, achievable edge after costs: **+3–10% expectancy per trade**, compounding to portfolio-level **15–40%/yr** if risk is managed. That is elite. Renaissance Medallion — the best fund in history, capacity-constrained, with PhD armies — did ~39% net.
2. **"High confidence 100x" does not exist.** Far-OTM options are systematically *overpriced* because retail loves lotteries — Boyer & Vorkink (2014, *J. Finance*), "Stock Options as Lotteries": deep-OTM equity options have strongly **negative** expected returns. The right way to chase convexity is a **barbell**: 90–95% of risk in positive-expectancy defined trades, 5–10% in small (0.5–1% each) convex bets where research says the tail is *underpriced* (squeeze setups, binary biotech events, vol regime breaks). Expect most convex bets to expire worthless; one 20x pays for the book.
3. **The competition is Citadel/Jane Street on speed and breadth.** Retail edge lives in: (a) longer horizons they can't bother with, (b) capacity-constrained anomalies too small for funds, (c) cross-domain synthesis at scale — exactly what an LLM-agent system is for.
4. **The #1 failure mode is backtest overfitting, not bad ideas.** Harvey, Liu & Zhu (2016, *RFS*): most published factors fail out of sample; demand t-stat > 3. Bailey & López de Prado (2014): deflated Sharpe ratio. Half this design is validation machinery for that reason.
5. **Costs kill more retail option strategies than bad signals.** Option spreads are wide (Muravyev & Pearson 2020, *RFS*, "Options Trading Costs Are Lower Than You Think" — *if* you use mid-or-better limits and time execution). Hard liquidity gate: OI > 500, bid-ask < 10% of mid, never market orders.

What the system CAN honestly deliver: scan ~5,000 names across ~15 signal families nightly, surface the 5–10 setups with genuinely stacked odds, structure them optimally, size them via half-Kelly, and track its own live hit rate so you know which signals are real.

---

## Part 1: The edges worth building around (research-backed)

Ranked by evidence strength × retail accessibility.

### Tier 1 — Core, persistent, options-native

| Edge | Evidence | Use |
|---|---|---|
| **Variance risk premium (IV > RV)** | Carr & Wu (2009, *RFS*) "Variance Risk Premiums" — implied vol exceeds subsequent realized ~85–90% of months. CBOE PUT index ≈ SPX returns at lower vol. | Per-name VRP screen: sell premium (condors/credit spreads) when VRP wide + IV-rank > 50; buy premium when VRP inverted. |
| **Vol-surface skew/smirk** | Xing, Zhang & Zhao (2010, *JFQA*): steepest-smirk stocks underperform ~10.9%/yr risk-adjusted. Cremers & Weinbaum (2010, *JFQA*): call–put IV spread predicts ~50bp/week. An, Ang, Bali & Cakici (2014, *JF*): ΔIV(call) predicts returns. | Daily cross-sectional skew + IV-spread ranks → directional bias input for all 3 streams. |
| **Options flow as informed trading** | Pan & Poteshman (2006, *RFS*): open-buy put/call volume ratios predict stock returns (signal strongest in names with high info asymmetry). | Unusual-activity detector: volume/OI spikes, sweep classification, premium-weighted direction. |
| **Dealer gamma (GEX) regime** | SqueezeMetrics white paper; pinning at high-OI strikes into OpEx; negative GEX → trending/high realized vol, positive GEX → mean reversion. (V's own measurement: 78% directional consistency on SPX.) | Daily regime flag gating strategy choice: condors in +GEX chop, directional spreads in −GEX trends; OpEx pin candidates. |
| **Implied vs realized earnings move** | Per-name straddles systematically overprice earnings moves on average, with fat tails. | Pre-earnings screen: historical realized move distribution vs current implied move → sell or buy the event per name. |

### Tier 2 — Stock-selection alpha (feeds swing + LT)

| Edge | Evidence | Use |
|---|---|---|
| **PEAD (post-earnings announcement drift)** | Bernard & Thomas (1989); persists in small/mid caps | Post-earnings drift trades, 1–4 wk swing stream |
| **Momentum (+ crash filter)** | Jegadeesh & Titman (1993) ~1%/mo; Daniel & Moskowitz (2016) "Momentum Crashes" — gate by vol regime | 12-1 momentum + 52-wk-high proximity (George & Hwang 2004) for swing/LT ranks |
| **Insider cluster buying** | Cohen, Malloy & Pomorski (2012, *JF*) "Decoding Inside Information" — opportunistic (non-routine) buys predict; routine ones don't | SEC Form 4 stream (free, EDGAR), cluster detector, routine-trade filter |
| **Short squeeze setups** | Drechsler & Drechsler (2014) "The Shorting Premium" — high borrow fee predicts underperformance *except* when squeeze catalysts hit | High SI + high utilization + rising price + catalyst = convex-bet candidate (calls, small size) |
| **Retail flow/sentiment** | Boehmer, Jones, Zhang & Zhang (2021, *JF*) retail order imbalance predicts short-horizon returns; Lopez-Lira & Tang (2023) LLM news sentiment predicts next-day returns | LLM-scored news/Reddit sentiment as a *feature*, not a standalone signal |
| **Economic links / lead-lag** | Cohen & Frazzini (2008, *JF*) "Economic Links and Predictable Returns" — customer–supplier momentum spillover takes weeks to propagate | Supply-chain graph: when a giant guides up, rank its laggard suppliers/customers |

### Tier 3 — Timing & calendar overlays

- **Pre-FOMC drift** — Lucca & Moench (2015, *JF*): outsized equity returns in 24h pre-FOMC (weakened post-publication; use as overlay, not standalone).
- **Turn-of-month** (Lakonishok & Smidt 1988), **OpEx week** flows, quad witching, overnight-vs-intraday return anomaly (Lou, Polk & Skouras 2019).
- **0DTE/charm-vanna flows** — 0DTE ≈ 40%+ of SPX volume; intraday dealer-hedging flows create predictable late-day drift in pinned regimes.
- **Per-name day-of-week/month seasonality** — keep only with per-name statistical significance.
- **Catalyst calendar**: FDA/PDUFA dates, clinical readouts, lockup expirations, index rebalances, govt contract awards (USAspending.gov, free), 8-K full-text monitoring (EDGAR real-time, free).
- **Congressional trades**: minor feature only — NBER evidence shows no reliable abnormal returns post-disclosure.

### What NOT to build

- Deep-learning price prediction. Gradient-boosted trees beat neural nets on tabular financial data (Grinsztajn et al. 2022, NeurIPS). Save the GPU for LLM work.
- HFT/intraday execution alpha — structurally unavailable at retail.
- Satellite/credit-card alt data — out of budget; edge already arbitraged at institutional scale.

---

## Part 2: Architecture

```
┌──────────── DATA LAYER (point-in-time, append-only) ────────────┐
│ Tradier (live chains, free w/ acct) · ThetaData (hist options)  │
│ EDGAR full-text + Form 4 · FINRA short vol · FRED · OCC/CBOE    │
│ Reddit/StockTwits · USAspending · FDA calendar · Google Trends  │
└──────────────────────────┬──────────────────────────────────────┘
                ┌──────────▼──────────┐
                │ FEATURE STORE       │  ~5,000 names × ~200 features,
                │ (DuckDB/Parquet,    │  computed vectorized (no LLM),
                │  point-in-time)     │  nightly + intraday deltas
                └──────────┬──────────┘
      ┌────────────────────┼──────────────────────┐
┌─────▼──────┐     ┌───────▼──────────┐    ┌──────▼──────┐
│ SIGNAL     │     │ ML RANKER        │    │ REGIME      │
│ AGENTS     │ ──▶ │ LightGBM, IC-    │ ◀─ │ SENTINEL    │
│ (15 fams)  │     │ weighted ensemble│    │ (VIX/GEX/   │
└────────────┘     └───────┬──────────┘    │  breadth)   │
                           │ top ~30       └─────────────┘
                 ┌─────────▼──────────┐
                 │ STRATEGIST (Claude)│ deep-dive per candidate →
                 │ + RISK OFFICER     │ structure, strikes, size,
                 └─────────┬──────────┘ exits, invalidation
                           │
                 ┌─────────▼──────────┐
                 │ DAILY BRIEFING     │ 3 streams, executable
                 │ for N + V          │ tickets, confidence, EV
                 └─────────┬──────────┘
                 ┌─────────▼──────────┐
                 │ AUDITOR / IC LOOP  │ live hit-rate per signal,
                 │ + paper trading    │ decay detection, attribution
                 └────────────────────┘
```

### Agents (LangGraph)

1. **Regime Sentinel** (pre-market): VIX9D/VIX/VIX3M term structure, SPX GEX, breadth (% > 200dma), HY credit spreads, DXY → publishes a regime state that *gates* which playbooks are active. (Premium-selling playbook off when VRP inverted; momentum off in crash-vol regime per Daniel-Moskowitz.)
2. **Universe Scanner**: vectorized feature computation, full ~5K universe, no LLM cost.
3. **Signal Agents** (one per family from Part 1): each emits scored candidates with provenance.
4. **Ensemble Ranker**: LightGBM cross-sectional model, target = forward 5d/21d/63d excess returns; purged k-fold CV (López de Prado, *Advances in Financial ML*, 2018); weekly walk-forward retrain on the 5080 box. Signal weights modulated by each signal's live information coefficient (IC), tracked continuously.
5. **Strategist** (Claude API): for top ~30 only — synthesizes all signals into a thesis, selects structure per stream (condor vs credit spread vs debit spread vs PMCC/LEAPS vs shares), exact strikes/expiry (45 DTE default for premium selling), limit price at mid, half-Kelly size, profit target, stop, invalidation condition. Output = ticket N can execute verbatim.
6. **Risk Officer**: portfolio-level Greeks, correlation clusters, max-loss budget, CVaR; vetoes or resizes.
7. **Auditor** (nightly): logs every suggestion → outcome, per-signal live hit rate, deflated Sharpe on live record, flags decaying signals for demotion.
8. **Deep Researcher** (on-demand): LT theses — 10-K/transcript analysis, supply-chain mapping, secular-theme exposure.

### RTX 5080 (16GB VRAM) division of labor

- **Local LLM** (Qwen3-14B or 30B-A3B quantized via Ollama/vLLM): bulk NLP — score thousands of headlines/day, parse 8-Ks within minutes of filing, classify Form 4s routine-vs-opportunistic, summarize transcripts, Reddit sentiment. This is what makes full-universe NLP affordable.
- **Claude API**: reserved for top-30 synthesis + final tickets (~$40–60/mo with prompt caching).
- **GPU also**: embedding models for news-similarity/dedup, weekly LightGBM retrains (fast anyway).

### Validation machinery (non-negotiable)

- Point-in-time feature store; never compute features with revised data.
- Survivorship-bias-aware backtests (include delisted names where data allows).
- Walk-forward only; report deflated Sharpe; reject any signal not significant after multiple-testing correction.
- **Promotion ladder**: new signal → backtest → 4–8 weeks paper (Tradier sandbox) → small live size → full weight. Demotion on live IC decay.

---

## Part 3: Budget (up to $200/mo — V approved)

| Item | Cost | Provides |
|---|---|---|
| Tradier brokerage | free | Live options chains + greeks, paper-trading sandbox |
| ThetaData Standard | $80 | Historical options incl. intraday quotes — **the** unlock for backtesting options strategies properly |
| Unusual Whales | $48 | Cleaned flow/sweeps feed (fallback: approximate flow from Tradier volume/OI deltas, free) |
| Claude API | $40–60 | Strategist + Deep Researcher (with prompt caching) |
| EDGAR, FINRA SI, FRED, OCC, CBOE delayed, Reddit, USAspending, FDA cal, Google Trends | free | Everything else |

**Chosen stack ≈ $170–190/mo.** Local LLM on the 5080 keeps Claude costs bounded by handling all bulk NLP.

---

## Part 4: Greenfield build roadmap (priority order)

Built as a standalone project at `~/Projects/TradeResearch`.

1. **Foundation: point-in-time feature store + data ingestion** (DuckDB/Parquet; Tradier chains, EDGAR, FINRA short volume, FRED, CBOE free feeds). Prerequisite for everything honest downstream.
2. **Historical options data + options-aware backtester** (ThetaData integration). The single biggest lever: without historical chains, no options strategy can be *proven* — only believed.
3. **Tier-1 signal screens**: per-name VRP (IV vs trailing realized), vol-surface skew/IV-spread ranks, implied-vs-realized earnings move, GEX regime, flow detector (Unusual Whales feed or volume/OI deltas).
4. **ML ensemble ranker** (LightGBM + purged CV + walk-forward) over the feature store.
5. **Local LLM bulk-NLP pipeline** (Qwen via Ollama/vLLM on the 5080): EDGAR 8-K real-time full-text, Form 4 routine-vs-opportunistic classifier, universe-scale news/Reddit scoring.
6. **Agent layer (LangGraph)**: Regime Sentinel → Signal Agents → Ranker → Strategist (Claude) → Risk Officer → daily briefing with executable tickets.
7. **Auditor + promotion ladder**: live per-signal scorecards, paper-trading gate (Tradier sandbox), decay-based demotion.
8. **Tier-2/3 extensions**: supply-chain lead-lag graph, insider clusters, squeeze detector, calendar overlays. Congressional trades only as a minor feature (evidence is weak).

## Verification standard

- Backtest harness must reproduce known results (e.g., short-strangle/condor VRP harvest ≈ positive expectancy with fat left tail across 2018/2020 windows) before being trusted on new signals.
- Every new signal ships with a walk-forward report + deflated Sharpe; promotion only via the paper-trading gate.
- End-to-end: nightly run produces a briefing with ≥1 executable ticket per stream; the Auditor logs and scores it the next day.

## Key references

- Carr & Wu (2009), "Variance Risk Premiums," *Review of Financial Studies*
- Xing, Zhang & Zhao (2010), "What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?" *JFQA*
- Cremers & Weinbaum (2010), "Deviations from Put-Call Parity and Stock Return Predictability," *JFQA*
- An, Ang, Bali & Cakici (2014), "The Joint Cross Section of Stocks and Options," *Journal of Finance*
- Pan & Poteshman (2006), "The Information in Option Volume for Future Stock Prices," *RFS*
- Boyer & Vorkink (2014), "Stock Options as Lotteries," *Journal of Finance*
- Bernard & Thomas (1989), "Post-Earnings-Announcement Drift," *Journal of Accounting Research*
- Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers," *Journal of Finance*
- Daniel & Moskowitz (2016), "Momentum Crashes," *Journal of Financial Economics*
- George & Hwang (2004), "The 52-Week High and Momentum Investing," *Journal of Finance*
- Cohen, Malloy & Pomorski (2012), "Decoding Inside Information," *Journal of Finance*
- Drechsler & Drechsler (2014), "The Shorting Premium and Asset Pricing Anomalies," NBER
- Boehmer, Jones, Zhang & Zhang (2021), "Tracking Retail Investor Activity," *Journal of Finance*
- Lopez-Lira & Tang (2023), "Can ChatGPT Forecast Stock Price Movements?"
- Cohen & Frazzini (2008), "Economic Links and Predictable Returns," *Journal of Finance*
- Lucca & Moench (2015), "The Pre-FOMC Announcement Drift," *Journal of Finance*
- Lakonishok & Smidt (1988), "Are Seasonal Anomalies Real?" *RFS*
- Lou, Polk & Skouras (2019), "A Tug of War: Overnight versus Intraday Expected Returns," *JFE*
- Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns," *RFS*
- Bailey & López de Prado (2014), "The Deflated Sharpe Ratio," *Journal of Portfolio Management*
- Muravyev & Pearson (2020), "Options Trading Costs Are Lower than You Think," *RFS*
- Grinsztajn, Oyallon & Varoquaux (2022), "Why Do Tree-Based Models Still Outperform Deep Learning on Tabular Data?" NeurIPS
- López de Prado (2018), *Advances in Financial Machine Learning*, Wiley
