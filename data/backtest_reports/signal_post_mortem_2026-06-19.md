# Signal Post-Mortem — 2026-06-19

Per-signal: why it hasn't produced a promotable edge yet, and the single thing that unblocks it.
Owner: PC Opus. Decision-maker (promotion): V. Source: MASTER_REPORT_MTM, FREE_SWEEP_2026-06-19,
SKEW_REGIME_2026-06-19, the trackers, and the registry. Nothing here is promoted.

## The honest one-paragraph summary
Across 49 signals, **one** has cleared the hard gates in any window: momentum_12_1 (lookback=126) on
liquid_264 — and it is held at SANDBOX by survivorship-capping, not promoted. Everything else is
blocked on data, partial (clears one gate, misses another), or has no edge. The dominant blockers are
(1) options breadth — 22 signals need the chain bank past 49→200 names, now filling; (2) the
survivorship/PIT gap that caps every free-signal result; (3) missing backtest adapters for the engine
analyzers (trend/candles/etc.). None of the blockers is "the signal is fundamentally dead" except where
explicitly noted.

## Cleared a gate (closest to promotable)
- **momentum_12_1 (lookback=126)** — train 0.678 / wf 0.332 / wf-DD 15% on liquid_264: clears all hard
  gates. WHY NOT PROMOTED: survivorship-biased universe (currently-listed only) caps it at SANDBOX; the
  107-name cap previously masked it. UNBLOCK: point-in-time universe with delisted names + re-test. This
  is the top free-signal candidate.
- **momentum_12_1 (lookback=252 / 189)** — wf 0.75 at 5-8% DD but train 0.08-0.28: strong out-of-sample,
  weak in-sample. WHY: regime-dependent (momentum crashes in 2022). UNBLOCK: Daniel-Moskowitz crash
  filter / regime gate, then PIT re-test.
- **skew_25d** — wf DSR 0.58-0.75 at 4-5% DD, dead train. WHY: edge concentrated in a single regime on
  7-8 cohorts (pre-registered regime hypothesis REJECTED 2026-06-19 — no stable cross-window regime;
  small-sample artifact). UNBLOCK: chain bank to 200+ names for >=30 trades/bucket, then re-bucket.

## Real edge, disqualifying risk
- **vrp_harvest (vrp_z / vrp_level / naked strangle)** — train DSR 0.80+, but MTM drawdown 51% train /
  79-87% wf. WHY: uninvestable tail risk (naked short vol); IC wings kill the edge. UNBLOCK: a tail
  defense proven to cut an 82%-class DD below 25% without erasing the premium — none found yet. Parked.

## Partial / no-edge on current data
- **pead (beat_and_raise_pead)** — train 0.554 (clears), wf 0.252 (just misses), high DD. WHY: thin
  universe + annual-fundamentals granularity. UNBLOCK: FMP earnings bank (now filling, 5.8k cached) +
  full-universe re-run; earnings dates are intact (epsActual/epsEstimated present).
- **supply_chain_lead_lag** — 0.026/0.040 on liquid_264: NO_EDGE. WHY: lead-lag correlations unstable
  at this breadth. UNBLOCK: larger PIT universe + economic-link priors (Cohen-Frazzini), else retire.
- **vrp_iron_condor** — net-negative (dead). WHY: defined-risk wings cost more than the harvested premium
  in this regime. UNBLOCK: regime-gated entry only; low priority.

## Blocked on data (no verdict yet — not "failed")
- **Options-bound (22):** iv_analysis, options_chain, greeks, trade_structure, liquidity, gex_dex,
  options_flow, earnings_adj_iv, volatility_regime, iv_call_put_spread, iv_term_slope, whale_flow,
  pre_fomc_drift, pre_fomc_straddle, etc. WHY: need chains across a broad universe; only 49→62 names
  banked. UNBLOCK: chain-bank daemon (running, ~85-120 names/day, auto-resume) → re-run XS options sweep
  at 100/200 names.
- **FMP-bound:** insider_cluster, insider_analyst_combo (FMP insider VERIFIED real rows, 4.5k cached →
  testable once a backtest reader is wired), analyst_revision_cascade (FMP grades verified), fundamental.
  WHY: backtest readers not yet pointed at the FMP disk cache. UNBLOCK: wire analysis/* FMP readers to
  data/cache/fmp + build the insider/analyst backtest generators' data path.
- **short_squeeze** — FMP short-interest = 404 on Starter. UNBLOCK: free exchange short-interest CSV
  ingest (Track 4a, deferred) — the genuine remaining data gap.

## No backtest adapter yet (engine analyzers)
- **trend, candles, chart_patterns, support_resistance, risk, macro, sector_dispersion,
  regime_markov_*** — live-pipeline category scorers with no cross-sectional backtest generator. WHY:
  never built as XS strategies. UNBLOCK: the ~15-adapter primitive-decomposition build (RSI/MACD/Stoch/
  EMA/ADX/BB/ATR as separate IC-tested signals) — a dedicated later night.

## Feature-only (cannot be promoted by design)
- cot_extreme, political_boost, halo_boost, smart_money_crowded, vix_term_contango, yield_curve_slope,
  hy_credit_spread, finra_short_volume, reddit_mentions, reddit_polarity (sandbox). Context for the LLM,
  not scored. No action unless reclassified (V's call).

## The one cross-cutting fix that matters most
A **point-in-time universe** (delisted names included). Until it exists, every free-signal DSR is an
upper bound and the best candidate (momentum 126) cannot move past SANDBOX. This is the highest-leverage
unblock for the whole free-signal half of the system.
