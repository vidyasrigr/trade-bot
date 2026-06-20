# TRACKERS SPEC — Single Source of Truth Dashboards

**Date:** 2026-06-19
**Owner:** PC Opus (build as Track 5 of CONSTRAINT_RUNBOOK_2026-06-19)
**Why:** No matter how good the work is, if tracking isn't in place our results and inference get skewed. These three trackers let V see, at a glance, what's done / pending / why — without sifting the DB and piecing it together (which itself creates gaps).

## Design rules

- **Auto-generated, never hand-edited.** One script `scripts/build_trackers.py` reads the DB + cache dirs + report files and regenerates all three. Stale-by-construction is the failure we're avoiding, so they regenerate at the end of every PCO run AND on an hourly schedule via APScheduler.
- **Plain markdown + monospace tables.** Renders in any editor, diffs cleanly in git, no server needed. ASCII progress bars (`████████░░ 80%`) for coverage.
- **Text status badges (no emojis — these get committed):** `PASS` `FAIL` `SANDBOX` `NO_EDGE` `PENDING` `BLOCKED` `PARTIAL`.
- **Top of every tracker = a one-line summary** so V reads the headline without scanning rows.
- Written to `data/trackers/` and also copied to `mac/trackers/` so V sees them outside the backend.

---

## TRACKER 1 — `SIGNAL_STATUS.md`

Answers: how many of the 49 signals are tested, for which streams (O/S/M/L), did they pass/fail, and why.

```
SIGNAL STATUS  —  generated 2026-06-19 23:14
=================================================================================
Tested: 18/49   PASS: 2   SANDBOX: 5   NO_EDGE: 6   BLOCKED: 5   PENDING: 31
By stream:  O 4/22   S 9/20   M 3/14   L 1/6
Bottleneck: 22 signals waiting on MarketData chain bank (49/200 names = 25%)
=================================================================================

CROSS-SECTION                 O S M L  DATA   BT   WF   TRAIN  WF_DSR  MTM_DD  VERDICT    BLOCKED_BY
---------------------------------------------------------------------------------------------------
skew_25d                      x . . .  ready  done done  0.12   0.66    4%     SANDBOX    regime-conditioned: see note
momentum_12_1                 . x x x  ready  done done  0.41   0.38   18%     PASS       -
vrp_z                         x . . .  ready  done done  0.84   0.31   82%     NO_EDGE    DD>25% hard gate
insider_cluster               . . x x  PART   ---  ---    -      -       -      BLOCKED    FMP insider bank 40%
pead (beat_and_raise)         . x x .  PART   done ---    0.55   -       -      PENDING    FMP earnings bank 60%
...
ENGINE (rollup + primitives)  O S M L  DATA   BT   WF   TRAIN  WF_DSR  MTM_DD  VERDICT    BLOCKED_BY
---------------------------------------------------------------------------------------------------
momentum  (rollup)            . x x .  ready  done done  0.33   0.29   14%     SANDBOX    -
  - rsi_14                    . x . .  ready  done done  0.21   0.19   11%     NO_EDGE    -
  - macd                      . x x .  ready  done done  0.44   0.41   12%     PASS       -
  - stoch                     . x . .  ready  done done  0.08   0.05    9%     NO_EDGE    -
trend     (rollup)            x x x .  ready  done done  ...
  - ema_align                 . x x .  ready  done done  ...
...

NOTES
-----
skew_25d: dead train (0.12) but WF 0.66 @ 4% DD. Pre-registered regime hypothesis
  {low_vol_bull, mid_vol_range} tested -> [PCO fills result]. Not promotable until train clears.
vrp_z: real edge, disqualifying 82% MTM drawdown. Parked.
```

**Columns:** stream relevance (O/S/M/L as x/.), DATA (ready / PART / waiting), BT done?, WF done?, train DSR, WF DSR, MTM DD, VERDICT, BLOCKED_BY (the single reason it's not further along).

**Source of truth:** join `signal_registry` (the 49 rows + categories + streams) with the latest row per signal in `backtest_runs` / `MASTER_REPORT*` for DSR/DD, and the data-readiness from Tracker 2.

**Stream mapping:** add a `streams` field to each `SignalSpec` (O/S/M/L) if not already present, so this is data-driven not hardcoded in the generator.

---

## TRACKER 2 — `DATA_INVENTORY.md`

Answers: what have we pulled, from where, for how many tickers, and how much is pending — so we never sift the DB to piece it together.

```
DATA INVENTORY  —  generated 2026-06-19 23:14
=================================================================================
Target universe: 200 core / 5,031 listed
Credits today:  MarketData 9,850/10,000   FMP 48,210 calls (no daily cap)
=================================================================================

SOURCE        DATASET                SYMBOLS   COVERAGE(core)        DATE_RANGE        UPDATED   PENDING
---------------------------------------------------------------------------------------------------------
MarketData    train chains            87/200   ████░░░░░░  44%       2018-01..2024-12  23:01     113 names
MarketData    wf chains               49/200   ██░░░░░░░░  25%       2025-01..2026-06  22:40     151 names
yfinance      daily OHLCV          5,031/5,031 ██████████ 100%       2015-01..today    21:55     -
FRED          macro series            31/31    ██████████ 100%       1970..today       21:30     -
FMP           earnings dates         5,031/5,031 ██████████ 100%     2018..today       22:50     -
FMP           insider txns           2,010/5,031 ████░░░░░░ 40%      2-yr trailing     23:10     ~3,000 names
FMP           short interest         5,031/5,031 ██████████ 100%     biweekly          22:20     -
FMP           analyst estimates        410/5,031 █░░░░░░░░░  8%      forward           23:12     daemon running
FMP           fundamentals (quarterly) 200/5,031 ░░░░░░░░░░  4%      16q trailing      23:05     daemon running
EDGAR         Form 4 insider         1,200/5,031 ██░░░░░░░░ 24%      full history      22:00     daemon running
CFTC          COT weekly              done      ██████████ 100%      2010..today       21:15     -
=================================================================================
ALERTS
- MarketData wf chains lag train chains by 38 names — bank wf for the 38 train-only names next.
- FMP fundamentals at 4% — lowest-priority endpoint, expected; will fill over ~6h.
```

**Columns:** source, dataset, symbols cached / target, ASCII coverage bar vs CORE universe, date range covered, last update timestamp, pending count.

**Source of truth:** count files in each cache dir (`data/marketdata_cache/`, `data/cache/fmp/<endpoint>/`, `data/feature_store/`), cross-ref against the core-200 list and the full listed universe. Credit counters from the daemon progress logs.

**This is also our credit ledger** — MarketData spend today + FMP call count, surfaced at top.

---

## TRACKER 3 — `VALIDATION_LEDGER.md`

Answers: BT / WF / paper status per signal, and rolled up per stream and per category — what's going on under the hood.

```
VALIDATION LEDGER  —  generated 2026-06-19 23:14
=================================================================================
                     BACKTEST      WALK-FWD      PAPER
Signals complete:    18/49         16/49         0/49
=================================================================================

BY STREAM        BT        WF        PAPER     PASS-RATE(BT->WF)
-----------------------------------------------------------------
Options  (O)     4/22      4/22      0/22      1 of 4 cleared WF
Swing    (S)     11/20     10/20     0/20      4 of 10 cleared WF
Mid      (M)     5/14      4/14      0/14      2 of 4 cleared WF
Long     (L)     2/6       2/6       0/6       1 of 2 cleared WF

BY CATEGORY      BT        WF        PAPER
-----------------------------------------------------------------
engine           9/15      9/15      0/15
cross_section    6/12      5/12      0/12
overlay          2/5       2/5       0/5
compound         1/3       0/3       0/3
strategy         0/2       0/2       0/2
feature_only     n/a (context-only, not validated)

PAPER PIPELINE (once a signal PASSes gates -> enters here)
-----------------------------------------------------------------
SIGNAL          STREAM   PROMOTED_ON   PAPER_TRADES   DURATION_GATE   STATUS
(empty - nothing has cleared the hard gates yet)
=================================================================================
```

**Purpose:** the per-stream / per-category rollup is what tells V where the gaps are (e.g. "strategy signals 0/2 — those are MarketData-bound" or "compound 0/3 WF — FMP not banked yet"). The paper pipeline section stays empty until something clears, then auto-populates with the stream-specific duration gate countdown from P0 Stage 3.2.

---

## The generator: `scripts/build_trackers.py`

- Single script, no LLM, pure Python. Reads DB + cache dirs + report JSONs.
- `python -m scripts.build_trackers` regenerates all three to `data/trackers/` and `mac/trackers/`.
- Wire into `main.py` APScheduler: hourly + at the end of each validation run.
- Idempotent and fast (<5s) — it only reads, never computes signals.
- If a data source is missing, the row shows `PENDING`/`0%`, never errors out.

## Done-when

- [ ] All three trackers generate from real DB + cache state
- [ ] Headline summary line correct on each
- [ ] `streams` field exists on every `SignalSpec` so O/S/M/L is data-driven
- [ ] Scheduled hourly + post-run
- [ ] Copies land in `mac/trackers/` for V
- [ ] pytest 94/94 green
