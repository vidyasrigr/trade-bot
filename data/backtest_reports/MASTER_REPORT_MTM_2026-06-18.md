# Master Validation Report — MTM-corrected (2026-06-18 PM)

Owner: PC Opus. Decision-maker for promotion: V.
Gates (now MTM-aware): **train DSR ≥ 0.50 AND wf DSR ≥ 0.30 AND wf MTM-DD < 25% AND wf trades ≥ 100.**
Equity curve method: **daily mark-to-market** (Stage 3.0) — exposes intratrade drawdown the old
realized-exit curve hid. Universe: 40-name cached options universe (VRP) / ~150 liquid (equity signals).
Windows: train 2021-07→2024-12, wf 2025-01→2026-06 (options 5y-capped; cannot reach 2018 on Starter).

## Headline

**Under MTM drawdowns + the hard gates, ZERO signals promote.** Everything is SANDBOX or BLOCKED.
The system is correctly refusing to trust any signal whose true (mark-to-market) risk or
cross-fold consistency is unacceptable. The previously "promoted" VRP naked/stop variants are now
sandboxed on drawdown.

## Verdicts (MTM)

| Signal / variant | Train DSR | WF DSR | Train MTM-DD | WF MTM-DD | n (tr/wf) | Verdict | vs prior |
|---|---|---|---|---|---|---|---|
| vrp_naked_strangle | 0.843 | 0.309 | 51% | **82%** | 1052/430 | SANDBOX | **was PROMOTE** (DD gate now fails it) |
| vrp_naked_stop=1.5x | 0.820 | 0.316 | 51% | **87%** | 1052/430 | SANDBOX | **was PROMOTE** |
| vrp_naked_stop=1.0x | 0.802 | 0.301 | 52% | **79%** | 1052/430 | SANDBOX | **was PROMOTE** |
| vrp_regime_gate=1.5 | 0.739 | 0.304 | 54% | 79% | 978/364 | SANDBOX | keeps edge, DD still huge |
| vrp_regime_gate=1.3 | 0.580 | 0.301 | 57% | 78% | 877/330 | SANDBOX | — |
| vrp_iron_condor 1.5–3.0σ | 0.00 | 0.00 | 54–59% | 37–42% | ~695/301 | SANDBOX | net-negative (dead) |
| pead_hold=10d | **0.554** | 0.252 | 79% | 56% | 333/135 | SANDBOX | clears train, misses wf+DD |
| pead_hold=5d | 0.073 | 0.204 | 78% | 35% | 333/135 | SANDBOX | weak |
| skew_25d_hold=21d | 0.002 | **0.752** | 37% | **5%** | 236/70 | SANDBOX | strong wf + low DD, dead train |
| skew_25d_hold=42d | 0.000 | 0.581 | 46% | **4%** | 236/66 | SANDBOX | same pattern |
| momentum_12_1 (252d) | 0.023 | 0.527 | 68% | 29% | 830/320 | SANDBOX | regime-dependent |
| momentum_12_1 (189d) | 0.003 | 0.600 | 89% | 18% | 836/320 | SANDBOX | regime-dependent |
| momentum_12_1 (126d) | 0.354 | 0.307 | 30% | 14% | 840/320 | SANDBOX | most balanced momentum |
| momentum_12_1 (63d) | 0.236 | 0.047 | 39% | 52% | 840/320 | NO EDGE |
| insider / lead_lag / squeeze | — | — | — | — | 0/0 | BLOCKED | data (FMP tier / no hist SI) |

## Classification changes under MTM (the point of this sweep)

- **VRP naked + both stop variants: PROMOTE → SANDBOX.** Old realized-exit DD (27–28% train) passed
  the eye test; true MTM DD is 51% train / **79–87% wf**. The DD<25% gate correctly disqualifies them.
  This is the single most important correction: our one "promoted" signal is not deployable.
- Everything else was already sandbox/blocked; MTM didn't rescue any (equity signals already used
  cohort-level DD, so their numbers are unchanged — momentum/skew stay regime-dependent).

## What's actually interesting (for V's research direction)

1. **skew_25d**: walk-forward DSR 0.58–0.75 with **4–5% wf drawdown** — the best risk-adjusted OOS
   behaviour of anything tested. The blocker is a dead TRAIN DSR (~0): it didn't work through 2021–22.
   Worth investigating whether 2021–22 was a structurally skew-hostile regime (it can now be tagged via
   the new regime_classifier). If skew works in specific regimes, regime-gating could make it promotable.
2. **PEAD hold=10d**: only signal clearing the TRAIN gate (0.554). wf 0.252 just misses 0.30, DD high.
   With a disk-cached FMP layer + the full universe, worth a clean re-run.
3. **VRP**: real, breadth-robust edge but uninvestable drawdown. Parked. Any revival needs tail defense
   proven to cut an 82%-class DD below 25% (the IC sweep already shows wings can't without killing edge).

## Recommendation
Promote nothing (matches the gates). Next research: regime-conditioned skew_25d, and a clean PEAD
re-run once FMP quota + disk cache are in. No signal_registry change — V's call.
pytest 94/94. Prior realized-DD report preserved at MASTER_REPORT.md / MASTER_REPORT_prePhase1.md.
