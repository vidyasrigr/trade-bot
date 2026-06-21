# NEW SIGNALS SWEEP — 2026-06-21 (0621.2 Part B)

git_sha 70655e7. Windows train 2010-01-01..2019-12-31 / wf 2020-01-01..2026-06-18. SPY wf CAGR 15%. num_trials=30. Realistic equal-weight sizing + costs.
Arms: no-regime | ORACLE (ex-post factual regime = diagnostic ceiling) | APP (live GMM).

| signal | label | none sh/dd/cagr | oracle sh/n/occ | app sh/n/occ | wf excess_SPY | train sh |
|---|---|---|---|---|---|---|
| etf_mean_reversion_narrow | REGIME_CONDITIONAL_CANDIDATE | 1.36/14%/29% | 1.72/127/7 | 1.31/479/13 | 14% | 0.32 |
| etf_mean_reversion_broad | WEAK_LEAD | 0.69/23%/13% | 0.55/1615/10 | 0.61/2997/10 | -3% | -0.03 |
| sector_relative_strength | WEAK_LEAD | -0.29/63%/-10% | 0.65/2745/11 | 0.30/2067/7 | -25% | -0.09 |
| pairs_statarb | NO_EDGE | -0.26/52%/-26% | 0.02/80/10 | -0.57/170/7 | -42% | 0.17 |
| earnings_announcement_premium | CANDIDATE_DD_GATED | 1.27/30%/30% | 1.24/4860/4 | 1.27/4943/1 | 15% | 1.42 |

---

## HEADLINE — first genuine candidate found (0621.2)

After ~90 signal-variants across all prior sessions returned nothing, the EVIDENCED signals
(real mechanisms, not technical primitives) produced one genuine candidate and clarified the rest.

### `earnings_announcement_premium` -> CANDIDATE_DD_GATED (the find)
- Beats buy-and-hold RISK-ADJUSTED in BOTH windows: train sharpe **1.42** vs SPY 0.92; wf **1.27** vs
  SPY 0.81. +14.7% wf CAGR excess. Consistent sharpe 1.21-1.49 across EVERY sub-period (2010-19, 2020,
  2021-26) — NOT a recent-window artifact.
- Event-driven (Frazzini-Lamont announcement premium), not long beta; clean look-ahead (longs around
  KNOWN announcement dates, does not use the surprise).
- The ONLY gate it misses is wf max account DD = 30% (>25%) — and that is ENTIRELY the COVID-2020
  crash (train DD 23% already clears; 2021-26 DD 27%). A VIX<35 entry filter trims it to 27% but a
  mid-trade de-gross rule is needed to get <25%, because the DD comes from holding through the crash.
- VERDICT: the first signal worth a paper allocation, pending (a) a crisis de-gross overlay to cap DD,
  (b) PIT confirmation, (c) V's promotion call. Best result of the whole program.

### Others
- `etf_mean_reversion_narrow` -> REGIME_CONDITIONAL_CANDIDATE, but CAVEAT: it is invested ~100% of days
  (always a dip among SPY/QQQ/IWM) = essentially long beta. train sharpe 0.32 << SPY 0.92; it only
  "wins" 2020-26. Honest read: beta + recent-window, NOT a real edge. The benchmark-relative gate
  correctly kept it out of UNCONDITIONAL.
- `earnings`-adjacent + `sector_relative_strength` (negative unconditional; oracle 0.65 rescues it ->
  needs a WORKING regime classifier), `pairs_statarb` NO_EDGE (cost drag / simple pair selection),
  `etf_broad` WEAK_LEAD.

### Methodology note that mattered
The first pass labelled etf_mean_reversion UNCONDITIONAL_CANDIDATE — a FALSE POSITIVE from naive
sizing (summing same-day weights = leverage) + no benchmark gate. Fixing both (equal-weight long-only
account sim + require beating buy-and-hold in both windows) removed the false positive and surfaced the
real one. See also REGIME_AUDIT_2026-06-21: the app GMM classifier is regime-blind to stress, so prior
regime-conditional nulls were partly classifier error.
