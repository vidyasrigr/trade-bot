"""
Signal promotion ladder — Phase F.1.

Each (category, regime) row in factor_ic_scores is in one of five states:

    proposed → paper → live_small → live_full → demoted

Transitions (called from postmortem after every closed trade):

    proposed → paper        as soon as the row exists (no gate)
    paper → live_small      4 wks of paper + walk-forward DSR > 0.5
    live_small → live_full  8 wks of live_small + DSR remains > 0.5
    live_full → demoted     live DSR < 0 sustained for 30 days

A demoted row's `current_weight_multiplier` is forced to 0.25 (the minimum
allowed by compute_final_score's IC-multiplier cap).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from loguru import logger


STATES = ("proposed", "paper", "live_small", "live_full", "demoted")

# ---------------------------------------------------------------------------
# P0 Stage 3.1/3.2 — hard promotion gates (DSR alone is not enough)
# ---------------------------------------------------------------------------

# WF max drawdown < 25% deliberately KILLS the current VRP promotion (51% DD).
HARD_GATES = {
    "max_wf_drawdown": 0.25,
    "min_wf_trades": 100,
    "min_profit_factor": 1.3,
    "max_ticker_pnl_share": 0.25,
    "max_sector_exposure": 0.35,
}

# Minimum paper-trade evidence per stream before live promotion is even considered.
PAPER_DURATION_GATES = {
    "options":   {"min_days": 56,  "min_closed_trades": 100},
    "short_vol": {"min_days": 182, "min_closed_trades": 100, "requires_vol_spike": True},
    "swing":     {"min_days": 90,  "min_closed_trades": 75},
    "long_term": {"min_days": 90,  "min_closed_trades": 0,   "must_beat_spy": True},
}


def passes_promotion_gates(
    wf_metrics: dict,
    *,
    ticker_pnl_shares: dict | None = None,
    sector_exposures: dict | None = None,
) -> tuple[bool, list[str]]:
    """
    Hard, deterministic gates a signal must clear ON TOP of the DSR thresholds
    before it may be promoted. Returns (passed, list_of_failure_reasons). Checks
    only what the metrics provide — profit_factor / concentration are enforced
    when supplied (None = not yet computed, skipped rather than silently passed).
    """
    fails: list[str] = []
    dd = wf_metrics.get("max_drawdown")
    if dd is not None and dd >= HARD_GATES["max_wf_drawdown"]:
        fails.append(f"WF max_drawdown {dd:.0%} >= {HARD_GATES['max_wf_drawdown']:.0%}")
    n = int(wf_metrics.get("num_trades") or 0)
    if n < HARD_GATES["min_wf_trades"]:
        fails.append(f"WF trades {n} < {HARD_GATES['min_wf_trades']}")
    pf = wf_metrics.get("profit_factor")
    if pf is not None and pf < HARD_GATES["min_profit_factor"]:
        fails.append(f"profit_factor {pf:.2f} < {HARD_GATES['min_profit_factor']}")
    if ticker_pnl_shares:
        top = max(ticker_pnl_shares.values())
        if top > HARD_GATES["max_ticker_pnl_share"]:
            fails.append(f"top-ticker PnL share {top:.0%} > {HARD_GATES['max_ticker_pnl_share']:.0%}")
    if sector_exposures:
        top_sec = max(sector_exposures.values())
        if top_sec > HARD_GATES["max_sector_exposure"]:
            fails.append(f"top-sector exposure {top_sec:.0%} > {HARD_GATES['max_sector_exposure']:.0%}")
    return (len(fails) == 0, fails)

PAPER_DURATION = timedelta(days=28)
LIVE_SMALL_DURATION = timedelta(days=56)
DEMOTION_WINDOW = timedelta(days=30)
DSR_PROMOTE = 0.5
DSR_DEMOTE = 0.0


async def _row_metrics(session, category: str, regime: str) -> dict | None:
    from sqlalchemy import text
    result = await session.execute(text("""
        SELECT signal_status, status_changed_at, ic_score, sample_count
        FROM factor_ic_scores
        WHERE category = :c AND regime = :r
    """), {"c": category, "r": regime})
    row = result.mappings().first()
    return dict(row) if row else None


async def _walk_forward_dsr(session, category: str, regime: str, window_days: int) -> float:
    """
    Approximation: pull recent trade pnls tagged with this (category, regime)
    via memory_entries.factors_that_worked / failed (already populated by
    postmortem). Compute deflated Sharpe on daily realized pnl.
    """
    from sqlalchemy import text
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    result = await session.execute(text("""
        SELECT pt.realized_pnl, pt.closed_at
        FROM paper_trades pt
        LEFT JOIN memory_entries me ON me.trade_id = pt.id
        WHERE pt.closed_at IS NOT NULL
          AND pt.closed_at >= :cutoff
          AND (me.regime = :regime OR :regime = 'all')
          AND :category = ANY (COALESCE(me.factors_that_worked, '{}') ||
                                COALESCE(me.factors_that_failed, '{}'))
    """), {"cutoff": cutoff, "regime": regime, "category": category})
    rows = result.fetchall()
    if not rows or len(rows) < 5:
        return 0.0
    pnls = [float(r[0] or 0) for r in rows]
    import numpy as np
    from backtest.metrics import deflated_sharpe
    daily = np.asarray(pnls, dtype=float)
    if daily.std(ddof=1) == 0:
        return 0.0
    # num_trials=number of (cat,regime) cells × ic-tracker’s prior choices; a sane
    # default is 40 (the size of our category×regime grid).
    return float(deflated_sharpe(daily, num_trials=40))


async def _transition(session, category: str, regime: str, new_state: str, reason: str) -> None:
    from sqlalchemy import text
    multiplier = 0.25 if new_state == "demoted" else None
    if multiplier is not None:
        await session.execute(text("""
            UPDATE factor_ic_scores
            SET signal_status = :s, status_changed_at = NOW(),
                current_weight_multiplier = :m, updated_at = NOW()
            WHERE category = :c AND regime = :r
        """), {"s": new_state, "m": multiplier, "c": category, "r": regime})
    else:
        await session.execute(text("""
            UPDATE factor_ic_scores
            SET signal_status = :s, status_changed_at = NOW(), updated_at = NOW()
            WHERE category = :c AND regime = :r
        """), {"s": new_state, "c": category, "r": regime})
    logger.info(f"promotion[{category}/{regime}]: → {new_state} ({reason})")


async def evaluate_transitions(category: str, regime: str) -> str | None:
    """Returns the new state if a transition fired, else None."""
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        metrics = await _row_metrics(session, category, regime)
        if metrics is None:
            return None
        state = metrics["signal_status"]
        since = metrics["status_changed_at"] or datetime.now(timezone.utc)
        if isinstance(since, str):
            since = datetime.fromisoformat(since)
        now = datetime.now(timezone.utc)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        age = now - since

        if state == "proposed":
            await _transition(session, category, regime, "paper", "initial promotion")
            await session.commit()
            return "paper"

        if state == "paper" and age >= PAPER_DURATION:
            dsr = await _walk_forward_dsr(session, category, regime, window_days=28)
            if dsr > DSR_PROMOTE:
                await _transition(session, category, regime, "live_small",
                                   f"paper {age.days}d DSR={dsr:.2f}>{DSR_PROMOTE}")
                await session.commit()
                return "live_small"

        if state == "live_small" and age >= LIVE_SMALL_DURATION:
            dsr = await _walk_forward_dsr(session, category, regime, window_days=56)
            if dsr > DSR_PROMOTE:
                await _transition(session, category, regime, "live_full",
                                   f"live_small {age.days}d DSR={dsr:.2f}>{DSR_PROMOTE}")
                await session.commit()
                return "live_full"

        if state in ("live_small", "live_full"):
            dsr = await _walk_forward_dsr(session, category, regime, window_days=DEMOTION_WINDOW.days)
            if dsr < DSR_DEMOTE:
                await _transition(session, category, regime, "demoted",
                                   f"sustained DSR={dsr:.2f}<{DSR_DEMOTE}")
                await session.commit()
                return "demoted"

    return None
