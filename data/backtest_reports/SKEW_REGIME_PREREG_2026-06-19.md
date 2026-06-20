# PRE-REGISTRATION — skew_25d regime-conditioning experiment

**Written:** 2026-06-19, BEFORE running any regime-bucketed result (Track 4b, CONSTRAINT_RUNBOOK).
**Author:** PC Opus. **Decision-maker:** V. This file is committed before the result file exists so
the hypothesis cannot be retrofitted to whatever bucket happens to win (no p-hacking).

## Background (already known, from MASTER_REPORT_MTM)
skew_25d on the 49-name cache: TRAIN DSR ~0.00 (dead, 2021-07..2024-12), but WALK-FORWARD
DSR 0.58-0.75 at only 4-5% MTM drawdown (2025-01..2026-06). The pattern "dead train / strong
low-DD WF" suggests a regime-dependent edge, not a stable one. Train spans the 2021-22
meme-vol + bear; WF spans 2025-26.

## Hypothesis (pre-registered, directional)
The put-skew premium (Xing-Zhang-Zhao 2010, -10.9%/yr) is compensation for crash risk. The
profitable leg (shorting rich skew / going long low-skew names) should work when skew is
**over-priced and mean-reverts** — i.e. in calm, risk-on regimes — and should fail or invert in
stress regimes where elevated skew correctly prices real tail risk.

**H1:** skew_25d WF DSR is concentrated in calm regimes. Specifically, using the wired
`regime_classifier.regime_tag(entry_date)` buckets:
- WF DSR( skew_25d | regime in {low_vol|bull, normal_vol|bull, normal_vol|range} ) > 0.30
- WF DSR( skew_25d | regime in {high_vol|bear, normal_vol|bear, high_vol|range} ) <= 0.0

**H2 (train explanation):** the dead TRAIN DSR is driven by a high share of trades entered in
bear/high-vol buckets during 2021-22; train DSR within the calm buckets is materially higher
than the pooled train DSR (~0).

## Decision rule (pre-registered)
- If H1 holds (edge in the calm buckets, stress buckets flat/negative) AND no non-hypothesized
  bucket is the surprise winner -> skew_25d becomes a **regime-gating candidate**. It stays
  SANDBOX (the gate change and any promotion are V's call) and requires fresh-sample confirmation
  as the chain bank grows past the 49 names.
- If a DIFFERENT bucket carries the edge -> that is a NEW hypothesis for a fresh sample, recorded
  as such, NOT a promotion and NOT evidence for H1.
- Minimum n per bucket to report a DSR: 30 trades. Buckets below that are shown but flagged
  low-n and excluded from the decision.

## Method
Run the skew_25d cross-sectional backtest on the 49-name cache (0 new credits), MTM equity.
For each closed trade, tag the entry date with regime_tag(entry_date), group trades by bucket,
compute per-bucket deflated Sharpe + MTM drawdown on the WF window. Pooled WF/train reported
alongside as the baseline. Output -> SKEW_REGIME_2026-06-19.md, appended to MASTER_REPORT_MTM.
