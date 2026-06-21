# REGIME AUDIT 2010-2026 — app GMM classifier vs factual ground truth (0621.2 A2b)

Compares the live GMM `regime_state` (research/regime/regime_state) against ex-post factual
labels (research/regime/factual: SPY drawdown weather + VIX). This is the A3 diagnostic that lets
us separate "signal is bad" from "classifier is wrong."

## Headline: the app classifier is REGIME-BLIND TO STRESS.

App GMM state -> factual weather distribution (row-normalized):
```
state  bear  bull  correction  crisis   mean_vix  mean_dd   n
0      .01   .81   .18         .00      20.5      -0.06    1289
1      .00  1.00   .00         .00      12.9      -0.01     937
2      .04   .80   .15         .01      20.7      -0.05     618
3      .00  1.00   .00         .00      15.3      -0.01     577
4      .00   .39   .55         .06      33.4      -0.12     214   <- the only stress-ish state
5      .00   .97   .03         .00      17.8      -0.03     505
```
**5 of 6 states are dominantly "bull."** Only state 4 leans correction. The model never cleanly
isolates bear or crisis.

## At the moments that matter most, the app is WRONG
| date | what actually happened | app state | app's dominant weather |
|---|---|---|---|
| 2018-12-24 | SPY -19%, VIX 36 (near-bear) | 2 | **80% bull** |
| 2020-03-23 | COVID bottom: SPY -34%, VIX 62 (crisis) | 2 | **80% bull** |
| 2022-10-12 | 2022 bear: SPY -24%, VIX 34 | 2 | **80% bull** |
| 2024-07-01 | calm bull, VIX 12 | 1 | bull (correct) |

The GMM lumps the three worst drawdowns of the period into "state 2," which is 80% bull. It cannot
distinguish a -34% crisis from a routine pullback. It identifies calm-bull sub-types fine (states
1/3/5) but is blind to the stress regimes that regime-conditional strategies most need.

## Why: the fingerprint features cluster on calm-market micro-structure
The GMM was fit on the fingerprint (breadth, dispersion, factor RS, correlation, VIX, ...). Those
features separate calm-bull textures well but VIX/drawdown get diluted among 11 features, so the
clusters track "flavors of bull" rather than the crisis/bull axis that matters for risk.

## Consequence (escalation per the runbook)
**Earlier regime-conditional nulls (0620.2 S2/S3) were PARTLY a classifier artifact.** Gating a
signal on the app `regime_state` couldn't capture "trade only in stress / only in calm" because the
classifier never identified stress. This is exactly why, in the new-signals sweep, the ORACLE arm
(ex-post factual regime) rescued signals the APP arm did not (e.g. sector_relative_strength: oracle
sharpe 0.65 vs app 0.30) — the oracle has real stress labels; the GMM does not.

## Recommendation
Replace the GMM `regime_state` for gating with a CAUSAL drawdown+VIX+breadth classifier (an online
version of the factual labels: running-peak drawdown bucket + VIX percentile + 200dma trend, all
as-of-T). It is interpretable, separates crisis/bear/correction/bull by construction, and would make
regime-conditional testing meaningful. The GMM can stay as a secondary "bull-texture" descriptor.
This is the single highest-leverage fix to the regime program — flagged for V.

## Flip-lag (illustrative)
Because state 2 spans both calm and crisis, a clean flip-lag isn't well-defined for the GMM (it often
doesn't flip at all into a distinct stress state). The factual labels flip immediately by construction
(drawdown threshold), which is the behavior a deployable gate needs.
