# skew_25d regime-conditioning RESULT (2026-06-19, Track 4b)

Universe: 49 cached names. 0 new credits (cached chains only).
Windows: train 2021-07-01..2024-12-31 | wf 2025-01-01..2026-06-30. MIN_N=30.
Hypothesis pre-registered in SKEW_REGIME_PREREG_2026-06-19.md (committed first).

## hold=21d

Pooled (baseline, reproduces MASTER_REPORT_MTM):

| window | n | cohorts | DSR | Sharpe | MTM_DD | win |
|---|---|---|---|---|---|---|
| train | 362 | 35 | 0.598 | 0.142 | 33% | 47% |
| wf | 86 | 8 | 0.989 | 1.794 | 8% | 55% |

By regime bucket (num_trials=6 for deflation):

| window | regime | n | DSR | Sharpe | MTM_DD | win | note |
|---|---|---|---|---|---|---|---|
| train | high_vol|bear | 16 | 0.000 | -7.312 | 3% | 56% | LOW-N (excluded from decision) |
| train | high_vol|range | 84 | 0.001 | -3.301 | 6% | 46% |  |
| train | low_vol|bear | 62 | 0.172 | 0.407 | 21% | 42% |  |
| train | normal_vol|bear | 100 | 0.245 | 0.488 | 14% | 47% |  |
| train | normal_vol|bull | 42 | 0.027 | -1.052 | 8% | 40% |  |
| train | normal_vol|range | 58 | 0.163 | 0.366 | 4% | 57% |  |
| wf | high_vol|range | 22 | 0.000 | 0.000 | 0% | 41% | LOW-N (excluded from decision) |
| wf | normal_vol|bull | 8 | 0.000 | 0.000 | 0% | 75% | LOW-N (excluded from decision) |
| wf | normal_vol|range | 56 | 0.664 | 1.338 | 10% | 57% |  |

## hold=42d

Pooled (baseline, reproduces MASTER_REPORT_MTM):

| window | n | cohorts | DSR | Sharpe | MTM_DD | win |
|---|---|---|---|---|---|---|
| train | 362 | 35 | 0.921 | 0.679 | 41% | 49% |
| wf | 82 | 7 | 0.940 | 1.708 | 12% | 44% |

By regime bucket (num_trials=6 for deflation):

| window | regime | n | DSR | Sharpe | MTM_DD | win | note |
|---|---|---|---|---|---|---|---|
| train | high_vol|bear | 16 | 0.000 | 0.060 | 0% | 56% | LOW-N (excluded from decision) |
| train | high_vol|range | 84 | 0.044 | -0.778 | 7% | 50% |  |
| train | low_vol|bear | 62 | 0.205 | 0.518 | 23% | 45% |  |
| train | normal_vol|bear | 100 | 0.989 | 1.480 | 4% | 52% |  |
| train | normal_vol|bull | 42 | 0.006 | -1.219 | 25% | 38% |  |
| train | normal_vol|range | 58 | 0.069 | -0.216 | 11% | 53% |  |
| wf | high_vol|range | 22 | 0.000 | 0.000 | 0% | 41% | LOW-N (excluded from decision) |
| wf | normal_vol|bull | 8 | 0.000 | 0.000 | 0% | 62% | LOW-N (excluded from decision) |
| wf | normal_vol|range | 52 | 0.468 | 1.190 | 11% | 42% |  |


---

## VERDICT (scored against the pre-registered hypothesis)

**H1 (edge concentrated in calm/risk-on regimes): REJECTED.**

- The hypothesized calm-bull bucket `normal_vol|bull` is DEAD in train (DSR 0.027 @hold=21,
  0.006 @hold=42) and underpowered in WF (n=8). The edge does not live in the calm-bull regime.
- The only adequately-powered (n>=30) train buckets that carry edge are `normal_vol|bear` (0.245 /
  0.989) and `low_vol|bear` (0.172 / 0.205) — BEAR buckets, the opposite of the hypothesis.
- The only adequately-powered WF bucket is `normal_vol|range` (DSR 0.664 @21, 0.468 @42, n=52-56).
- Train-winning buckets (bear) and the WF-winning bucket (range) DISAGREE. There is no stable
  cross-window regime that carries the edge.

**H2 (dead train explained by bear-bucket share): NOT SUPPORTED in the hypothesized direction.**
The bear buckets are actually the *better* train performers, not the drag. The train drag is
`high_vol|range` (0.001) and `normal_vol|bull` (0.027).

**Decision (per the pre-registered rule):** a DIFFERENT bucket carried the edge than hypothesized,
and the winning buckets differ between train and WF. That is noise/new-hypothesis territory, NOT a
promotion and NOT evidence for regime-gating. skew_25d stays SANDBOX.

**Root cause = statistical power, not regime.** Pooled WF rests on only 7-8 cohorts; no regime
bucket has both adequate n AND a consistent train/WF story. The apparent WF strength
(pooled DSR ~0.99) is concentrated in a single regime on ~5 cohorts — exactly the kind of
small-sample artifact pre-registration exists to catch. Had the buckets been inspected first, the
temptation would have been to crown `normal_vol|range` (WF 0.66) or `normal_vol|bear` (train 0.99)
as "the regime" — but they are different buckets, so it is mining.

**Next step (gated on Track 1):** re-run this exact bucketing once the chain bank grows from 49 to
200+ names. Only with >=30 trades in the calm buckets in BOTH windows can a regime-gating claim be
made. Until then: no gate change, no promotion (V's call regardless).
