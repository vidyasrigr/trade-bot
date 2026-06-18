# P0 RUNBOOK — Pre-Paper-Trade Hardening

**Date:** 2026-06-17
**Owner:** PC Opus
**Author:** V + Mac Opus (consolidated from GPT audits `1.initial_0617.md` + `2.final_0617.md`)
**Status:** BLOCKING — no further signal validation runs until Stage 1 complete

---

## Why this runbook exists

GPT audit identified that the codebase has **built-but-unwired** safety infrastructure (`ticket_guards`, `recommendation_log`, signal_registry enforcement) and a **scope mismatch**: 49 signals registered but only VRP promoted, and VRP's 51% walk-forward drawdown would fail any reasonable risk gate. Before we run another validation cycle or open a paper trade, this runbook must be green.

**Hard rule:** Do NOT promote anything yourself. V owns `signal_registry.promotion_status`. Your job is to wire the gates and make the existing gates ENFORCED.

**Acceptance test for the whole runbook:** A fake high-conviction ticket with an earnings event inside DTE MUST be blocked by guards and logged as `rejected`. A real ticket MUST appear in `recommendation_log` with a `recommendation_id` that the paper-trade endpoint requires.

---

## Stage 1 — WIRING (today, blocking) ~2–3h

Goal: make existing infra actually run on the production paths.

### 1.1 `data/tradier.py` shim
- Create `backend/data/tradier.py` that re-exports `get_tradier` from `data/marketdata.py` (or whatever the current client is)
- Affected importers (per GPT inventory): `analysis/engine.py`, `agents/graph.py`, `analysis/whale_flow.py`, `analysis/liquidity_gate.py`, `agents/position_monitor.py`, `api/optimizer.py`
- Verify: `python3 -c "from data.tradier import get_tradier; print(get_tradier())"` succeeds
- 94/94 pytest stays green

### 1.2 Wire `run_all_guards()` into ticket build
- Edit `backend/scoring/_build_order_ticket` (or wherever the ticket dict is finalized)
- Call `run_all_guards(ticket, context)` BEFORE the ticket is returned
- If any CRITICAL guard fires → return `None` and log `guard_blocked` to `recommendation_log` with the failing guard names
- WARNING guards → attach to `ticket["guard_warnings"]`, do NOT block
- Guards must run on every emit path: scanner, briefing, analysis, paper-trade open

### 1.3 Wire `log_recommendation()` everywhere a ticket is emitted
- Production paths to instrument:
  - `data/scanner.py` final emit
  - `api/briefing.py` daily briefing assembly
  - `analysis/engine.py` per-symbol analysis
  - `agents/graph.py::_run_trader` final state
- Each call must return a `recommendation_id` (UUID) attached to the ticket payload
- Acceptance: after a scanner run, `SELECT COUNT(*) FROM recommendation_log WHERE created_at > NOW() - INTERVAL '1 hour'` > 0

### 1.4 Gate `/trades/paper/open` on recommendation_id
- Endpoint must accept `recommendation_id` (required, not optional)
- Re-run `run_all_guards()` at open-time (state may have changed — earnings moved, position appeared)
- If guards now fail → reject with 409 and update `recommendation_log.status = 'stale'`
- Reject opens with no matching `recommendation_id` row → 404

### 1.5 Hard runtime guard inside `compute_final_score()`
- Read `signal_registry` at function entry
- Any contributing signal whose `promotion_status NOT IN ('live_small', 'live_full')` MUST contribute 0 to the score (not just downweighted)
- Log unpromoted contributions to a metrics counter for visibility
- This is the kill-switch for sandboxed signals leaking into production conviction

### Stage 1 done-when
- [ ] `pytest` 94/94 green
- [ ] Manual: trigger scanner, inspect that all emitted tickets have a `recommendation_id` and that one synthetic earnings-in-DTE ticket gets blocked
- [ ] Journal entry in `pc/journal_2026-06-17.md`

---

## Stage 2 — LLM CEILING + LIFECYCLE (today if time permits) ~1–2h

### 2.1 Cap LLM conviction at quant
In `agents/graph.py` after the trader node:
```python
state["conviction_score"] = min(
    state["llm_conviction"],
    state["scoring"]["conviction_score"],
)
```
- LLM may LOWER conviction (challenge/risk-flag); never RAISE it above the quant score
- Persist both raw fields for audit (`llm_conviction_raw`, `quant_conviction_raw`)

### 2.2 Disable LightGBM ranker tilt
- Until we have ≥500 closed real labels, the ranker should run in shadow mode only
- Read `recommendation_log` row count at scanner startup; if < 500, set ranker influence weight to 0 and log a warning
- Re-enable automatically once threshold crossed

### 2.3 Recommendation lifecycle states
Migration `019_recommendation_lifecycle.sql`:
- Extend `recommendation_log.status` enum: `recommended | guarded_warn | rejected | ignored_by_user | stale | paper_opened | paper_closed`
- Default = `recommended`
- Briefing endpoint reads status to surface "WHY NOT TRADE" section

### 2.4 Calibration + regime + benchmark capture (per GPT review)
Same migration `019` — extend `recommendation_log` with:
- `predicted_conviction NUMERIC` — what the system said (0-100)
- `predicted_win_prob NUMERIC` — implied probability
- `actual_outcome NUMERIC` — populated at close (PnL or +1/-1)
- `market_regime TEXT` — `bull | bear | high_vol | low_vol | trend | range` (from `regime_classifier`)
- `stock_regime TEXT` — per-symbol regime from `stock_climate`
- `spy_return_holding_period NUMERIC` — populated at close
- `qqq_return_holding_period NUMERIC` — populated at close

**Why these matter (GPT's framing, worth quoting verbatim):**
- Calibration: "Conviction 90 → did it actually win 90%? If not, the system is miscalibrated. A lot of models have edge but terrible calibration."
- Regime attribution: enables "VRP works only in low vol; momentum works only in trend — now you know WHEN to deploy."
- SPY/QQQ benchmark: "Many 'winning' strategies don't actually beat buy-and-hold."

These are all schema-only — fill at recommendation time + close time. No new compute. Do them now while we're touching the table.

### 2.5 Calibration view
Add `views/v_calibration_buckets.sql`:
- Buckets predicted_win_prob into deciles
- Compares decile midpoint to realized win rate
- Briefing surfaces a calibration warning when any decile is >15pp off after ≥30 closed trades

---

## Stage 3 — HARD PROMOTION GATES (this week, before any VRP paper fill) ~2h

This is the biggest blocker for VRP — current 51% DD must fail the gate.

### 3.1 Add DD + concentration filters to `scoring/promotion.py`
- WF max drawdown < 25% — HARD GATE (kills current VRP promotion)
- No single ticker > 25% of total PnL
- No single sector > 35% of exposure
- Profit factor > 1.3
- WF trade count ≥ 100

### 3.2 Stream-specific paper duration gates
| Stream | Minimum paper duration | Minimum closed trades |
|---|---|---|
| Options (defined-risk) | 8 weeks | 100 |
| **Short-vol / VRP** | **6 months + 1 documented vol spike** | 100 |
| Swing | 3 months | 75 |
| Long-term | 3–6 months paper forward, must beat SPY risk-adjusted | n/a |

Encode as dict in `scoring/promotion.py::PAPER_DURATION_GATES` keyed by signal category.

### 3.3 Rolling demotion trigger
- Daily job: any signal with negative 30-day expectancy → auto-demote one tier
- Log demotion to `signal_registry_changes` table (new in migration 020)
- Slack/Discord webhook on demotion event

### 3.4 Synthetic 2020 stress test
- Before any short-vol signal can advance from `sandbox` → `paper`, it must be replayed against a synthetic Feb–Mar 2020 path (VIX 12 → 82 in 4 weeks)
- Pass criterion: max DD under stress < 40% AND no margin call event
- Stored as `backtest_runs.stress_test_passed` boolean

---

## Stage 4 — PAPER FILL REALISM (before first paper fill) ~1h

Per GPT initial doc — paper trade must be MORE conservative than backtest, not the same.

### 4.1 Conservative fill model in `backtest/fills.py` (extend, don't replace)
- Add `PaperFillModel` class:
  - Long premium entry: fill at `ask + 0.05 × (ask - bid)`
  - Short premium entry: fill at `bid - 0.05 × (ask - bid)`
  - Exits: symmetric worse-than-mid
  - Skip if `bid-ask > 0.08 × mid`
  - Skip if `open_interest < 100`
  - Skip if quote `stale_seconds > 30`
  - Simulate 5% missing-fill rate (random reject)
  - Per-leg representation (not single strike/price) for multi-leg structures

### 4.2 Per-leg paper-trade schema
- Migration 021: extend `paper_trades` with `legs JSONB` column (array of `{strike, expiry, side, qty, fill_price, fill_time}`)
- Update `/trades/paper/open` to accept and store legs
- Daily MTM job marks each leg to current mid; aggregates to position-level PnL

---

## Stage 5 — BRIEFING-LEVEL BACKTEST (Phase R.1 — bigger; spec only today) 

GPT's #1 architectural gap. This is a multi-day build, NOT for today. Capture spec here so we don't lose it.

### Spec
For every trading day from 2021-01-01 to today:
1. Load only data available as-of that day (feature store + chain cache)
2. Run the full scanner → briefing → trader-agent pipeline as it exists today
3. Apply ticket guards
4. Simulate fills with `PaperFillModel`
5. Track exits, stops, expiries, drawdowns
6. Log every rejected and accepted recommendation with reason

### Output: `data/backtest_reports/briefing_replay_<date>.md`
- Total recommendations, filled, rejected-by-guards
- PnL by stream / ticker / signal
- Max drawdown, worst month
- Regime breakdown (2022 bear, 2023 recovery, 2024 melt-up, 2025 chop, 2026 YTD)

**Owner:** V will scope; PC Opus will not start until V signs off. Do NOT start Stage 5 until Stages 1–4 are green.

---

## Stage 6 — DELETIONS + DNA REFRAME (tomorrow) 

### 6.1 Reframe ticker DNA
Per GPT initial doc point N1 — DNA is a modifier, not a core signal.
- In `analysis/stock_dna.py::format_dna_context`, prepend the LLM-facing string with: `[CONTEXT ONLY — describes tendencies; cannot be used as a standalone trade trigger]`
- Audit `agents/graph.py` strategist prompt — ensure no instruction treats DNA as a green-light source
- Per-ticker overfitting note: log when DNA was built on < 20 events; surface as a warning in the briefing

### 6.2 Daily briefing structure
New `/api/briefing/daily` response shape:
```json
{
  "tradeable": [...],     // passed guards + above conviction floor
  "watch": [...],         // passed guards, below conviction floor
  "blocked": [...],       // failed CRITICAL guard, with reason
  "why_not_trade_today": "...",   // 1-paragraph summary if tradeable=[]
  "regime": {...}
}
```

---

## Escalation criteria

PC Opus, ping V immediately (don't sit on it) if:
- Any wiring change breaks > 5 existing tests
- A migration would touch live data without an obvious rollback path
- VRP regime-gated variant clears all hard gates (V wants to look before promotion)
- You discover another major gap not on this list

## What NOT to do

- Do NOT promote anything in `signal_registry`. Only V does that.
- Do NOT open a live position. Paper only.
- Do NOT remove the persistent disk cache.
- Do NOT add emojis to code or commits.
- Do NOT invent new signals.

## Deferred to post-P0 (don't start, just don't lose)

- **Portfolio-level replay** (GPT addition D) — recs A/B/C competing for capital. Comes AFTER briefing replay (Stage 5). Portfolio construction often matters more than signal quality, but only meaningful once single-rec replay works.
- **Complexity-creep audit** — GPT's caution: every new component should prove itself or get cut. Re-run the deletion pass (akin to Phase A in the old plan) after Stage 5 ships, with a fresh eye on what's still earning its keep.

---

## Sequencing summary

```
TODAY:        Stage 1 (wiring)        — BLOCKING
TODAY/+1:     Stage 2 (LLM ceiling)   — high value, low risk
THIS WEEK:    Stage 3 (hard gates)    — blocks VRP paper fills
THIS WEEK:    Stage 4 (fill realism)  — blocks any paper fill
THIS WEEK:    Stage 6 (DNA + briefing) — quality of LLM context
NEXT:         Stage 5 (briefing replay) — multi-day; V scopes first
```

## Done = ready for paper trade

The system is paper-trade-ready when:
- [ ] Stage 1–4 green
- [ ] Synthetic earnings-in-DTE ticket blocked end-to-end
- [ ] At least one VRP variant clears the 25% DD gate (or VRP stays sandboxed)
- [ ] Discord briefing posts tradeable / watch / blocked sections cleanly
- [ ] `pytest` 94/94 green throughout
