# Master Validation Report — 2026-06-17 (PC Opus)

Owner: PC Opus (signal validation). Decision-maker for promotion/capital/budget: V.
Gate: **DSR > 0.5 train AND > 0.3 walk-forward → PROMOTE.** Train 2021-07→2024-12,
walk-forward 2025-01→2026-06. This report uses the **clean isolated-run numbers**, not
the contaminated all-concurrent run (see "Methodology note" — the free APIs rate-limit
when every signal fetches at once).

## Verdicts at a glance

| Signal / variant | Train DSR | WF DSR | Train DD | WF DD | n (tr/wf) | Verdict |
|---|---|---|---|---|---|---|
| **vrp_harvest** naked strangle | **0.904** | **0.317** | 27% | 51% | 526/215 | **PASSES GATE** (tail risk) |
| vrp regime-gate ratio=1.5 (post-hoc) | 0.831 | 0.321 | 29% | **48%** | 495/182 | PASSES, best tail fix |
| vrp regime-gate ratio=1.3 (post-hoc) | 0.690 | 0.320 | 32% | 47% | 438/163 | PASSES, fewer trades |
| vrp naked stop=1.5x | 0.896 | 0.308 | 28% | 56% | 526/215 | passes, stop never binds |
| vrp naked stop=1.0x | 0.887 | 0.312 | 28% | 53% | 526/215 | passes, stop never binds |
| vrp iron_condor 1.5/2.0/2.5/3.0σ | 0.00 | 0.00 | ~32% | ~14% | ~330/153 | **DEAD** (net negative) |
| pead hold=10d | **0.527** | — | 77% | — | 321/— | **PROMISING, WF blocked** |
| pead hold=5d | 0.066 | — | 78% | — | 321/— | weak train |
| momentum 6-1 (126d, post-hoc) | 0.354 | 0.307 | 30% | 14% | 840/320 | SANDBOX (most consistent) |
| momentum 12-1 (252d) | 0.023 | 0.527 | 68% | 29% | 830/320 | SANDBOX (regime-dependent) |
| momentum 9-1 (189d, post-hoc) | 0.003 | 0.600 | 89% | 18% | 836/320 | SANDBOX (regime-dependent) |
| momentum 3-1 (63d, post-hoc) | 0.236 | 0.047 | 39% | 52% | 840/320 | NO EDGE |
| skew_25d hold=21d (post-hoc) | 0.006 | 0.752 | 23% | 5% | 136/70 | SANDBOX (regime-dependent) |
| skew_25d hold=42d (post-hoc) | 0.000 | 0.581 | 45% | 4% | 136/66 | SANDBOX (regime-dependent) |
| lead_lag (Cohen-Frazzini) | 0.025 | 0.008 | 19% | 28% | 319/213 | **NO EDGE** |
| insider opportunistic | — | — | — | — | 0/0 | **BLOCKED** (FMP tier 402) |
| short_squeeze | — | — | — | — | 0/0 | **BLOCKED** (no hist. short interest) |

## Recommendations (V decides; I do not touch signal_registry)

1. **vrp_harvest → promote to PAPER, with the regime gate, as a SMALL sleeve.**
   The edge is real and reproduces exactly (train DSR 0.90 / wf 0.32). It is the only
   PROMOTE-class options signal. BUT its ~51% out-of-sample drawdown is the binding risk,
   and I proved the two obvious fixes do NOT work:
   - **Iron condor (any wing 1.5-3.0σ): net-negative.** Wings eat the thin credit; 4-leg
     cost + the 2x-credit stop (looser than the structural max) kill it. Dead end.
   - **Tighter stops (1.0/1.5x): no effect.** Identical trade count; the EOD stop never
     binds (21-DTE/profit exits dominate). And % drawdown is scale-invariant, so smaller
     size cannot fix the 51% either.
   - **Regime-gating entries (skip opening into accelerating vol) is the ONLY lever that
     keeps the edge** (train 0.83 / wf 0.32) AND trims the tail — but only 51%→48%.
   Net: paper-trade VRP with the regime gate + the system's fractional-Kelly sizing, small
   size, NOT a core allocation. The deeper tail fix to try next: VIX term-structure
   backwardation gate, or a cap on simultaneous open strangles (the tail is correlated
   across names — adding breadth made DD worse, 51%→74% at 40 names).

2. **pead (hold=10d) is the most promising NEW signal — finish it tomorrow.**
   Train DSR 0.527 (above gate) on the curated liquid universe. Walk-forward is
   **inconclusive only because FMP's free-tier daily quota (250 req/day) was exhausted**
   by today's repeated full-universe runs — NOT a verdict. Action: (a) add a disk cache to
   the PEAD earnings fetch so one day's pull is reused forever, (b) run train+wf once
   tomorrow on fresh quota. If wf > 0.3, PEAD promotes to paper.

3. **momentum / skew_25d: SANDBOX (observe-only), do not promote.** Both are strongly
   regime-dependent: walk-forward DSR is high (momentum 0.53-0.60, skew 0.58-0.75) but
   train DSR is ~0 — they worked in 2025-26 and failed through the 2022 drawdown. That
   inconsistency is exactly what the gate is designed to reject. momentum 6-1 (126d) is the
   most balanced (0.35/0.31) and worth re-checking on a true ADV-ranked 1000-name universe.

4. **lead_lag: NO EDGE** (DSR ~0, negative Sharpe) on the liquid universe. Dead for now.

5. **insider + short_squeeze: BLOCKED on data, your budget call.** insider needs an FMP
   tier with insider-trading access (currently 402). squeeze needs a historical
   short-interest feed (FMP legacy dead; no PIT series free). Neither is validatable today.

## Findings that affect the whole app (logged in pc/log.md)

- **FMP legacy v3/v4 API is dead app-wide** (403 since FMP's Aug-2025 migration). Every
  live FMP module (insider_flow, short_squeeze, fundamental, lt_scoring, stock_dna,
  analyst_targets, calendar) calls dead endpoints and is silently broken. The new `stable/`
  API works (PEAD repointed). Migrating the live modules is a separate work item.
- **FMP free tier = 250 req/day** — too small for repeated full-universe backtests. PEAD
  needs a disk cache; or upgrade FMP.
- **MarketData Starter ships no historical greeks** (cached chains have iv=0, delta=0). I
  built `backtest/iv_inversion.py` (Black-Scholes IV/delta from cached mids) which unblocks
  the skew/IV family for $0 — validated (SPY skew +6.1%, sane ATM IVs).

## Methodology note (why two sets of numbers exist)

The all-concurrent master run (`run_full_validation`) rate-limits the free data sources:
yfinance throttles when VRP (per-variant) and the equity panel fetch hit it at once
(collapsed VRP to n=28 in v3), and FMP 429s under load. The numbers above are from
**isolated per-signal runs** which are clean. Fix for next time: pre-fetch one shared
yfinance panel for the union universe and a disk-cached FMP layer, then the concurrent
runner is reliable. The VRP cached-chain results are unaffected (disk cache) and reproduce
exactly across v1/v2. The raw auto-generated run table is preserved at
data/backtest_reports/MASTER_REPORT_v1.md (v1) and master_progress.json.

## Credits / budget

- MarketData: ~2,400 of 10,000 used today (VRP family ran off the disk cache; IC/regime
  holding-day gaps were the only spend). Plenty of headroom.
- FMP free tier: daily quota exhausted (PEAD wf deferred to tomorrow).
- No signal_registry promotion_status changed (V's call).
- pytest: 94/94.

---

## CORRECTED DRAWDOWNS (MTM, 2026-06-18) — supersedes the realized-exit figures above

After the Stage 3.0 mark-to-market fix + the leak-fixed faithful re-run on the full 40-name
universe (train chains banked, ~5,200 credits), VRP's TRUE drawdowns are far worse than the
realized-exit equity showed:

| Window | Trades | DSR | Realized maxDD (old) | **MTM maxDD (true)** | PnL |
|---|---|---|---|---|---|
| Train 2021-07→2024-12 (40-name) | 1052 | 0.843 | 28% | **51%** | +$228,915 |
| Walk-fwd 2025-01→2026-06 (40-name) | 430 | 0.309 | 74% | **82%** | +$115,062 |

The realized-exit curve hid ~1/3 of the drawdown. VRP's real out-of-sample risk is an **~82%
mark-to-market drawdown** — a practical blow-up. The edge (DSR 0.84 train / 0.31 wf) is real
and robust to breadth, but the risk is disqualifying.

**Definitive verdict:** VRP is NOT promotable. It fails the DD<25% hard gate (Stage 3.1) and the
synthetic-2020 stress test (Stage 3.4, 40x-credit loss + margin call). Both new P0 gates correctly
reject it. Do not paper-trade naked VRP. Any future attempt needs genuine tail defense proven to
hold an 82%-class drawdown down to <25% — which the iron-condor sweep already showed wings can't
do without killing the edge. Park VRP; the next real signal work is PEAD (FMP quota permitting)
and the briefing-replay (Stage 5).
