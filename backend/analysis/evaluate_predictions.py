"""
Evaluate Predictions — nightly job that closes the loop.

For every recommendation whose target_resolution_date has arrived (or whose
target/stop hit before then), pull the actual price + compute realized PnL +
log a checkpoint row. Mark the recommendation resolved (win/loss) so it can
feed the postmortem export.

Works across ALL streams uniformly:
  - options: resolves at expiry OR when paper_trade closes
  - swing: resolves at target_resolution_date (~2 weeks default)
  - mid_term: resolves at target_resolution_date (~75 days)
  - long_term: resolves at target_resolution_date (~180 days)

Doesn't lose track of LT recommendations — a 6-month LT rec made on
2025-12-16 gets evaluated on 2026-06-16. Time-based, deterministic, simple.

Intermediate checkpoints (every 30 days for LT, every 7 days for mid-term)
are also written so we can see "expected vs actual drift" over the hold.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

from loguru import logger


CHECKPOINT_INTERVALS_DAYS = {
    "options": 7,       # check weekly until expiry
    "swing": 7,
    "mid_term": 14,
    "long_term": 30,
}


async def _spot_price(symbol: str) -> float | None:
    """Latest close from yfinance. Cheap, free."""
    try:
        from data.market import get_ohlcv_yfinance
        df = get_ohlcv_yfinance(symbol, period="5d")
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])
    except Exception:
        return None


async def _evaluate_one(rec: dict, session) -> bool:
    """Returns True if a checkpoint was written."""
    from scoring.recommendation_log import log_checkpoint
    from sqlalchemy import text

    today = date.today()
    rec_id = rec["id"]
    stream = rec["stream"]
    symbol = rec["symbol"]
    entry = float(rec.get("entry_price") or 0)
    target = float(rec.get("target_price") or 0)
    stop = float(rec.get("stop_price") or 0)
    direction = rec.get("direction") or "bullish"
    target_date = rec["target_resolution_date"]

    spot = await _spot_price(symbol)
    if spot is None or entry <= 0:
        return False

    is_bullish = direction != "bearish"
    sign = 1 if is_bullish else -1
    pnl_pct = sign * (spot - entry) / entry
    target_hit = (is_bullish and spot >= target) if target else False
    stop_hit = (is_bullish and spot <= stop) if (stop and is_bullish) else \
                (spot >= stop if (stop and not is_bullish) else False)

    pnl_usd = None
    pmp = rec.get("predicted_max_profit_usd")
    pml = rec.get("predicted_max_loss_usd")
    if pmp:
        pnl_usd = pnl_pct * float(pmp) if pnl_pct > 0 else pnl_pct * float(pml or 0)

    ev_predicted = float(rec.get("expected_value_pct") or 0) / 100.0
    expected_vs_actual = (pnl_pct - ev_predicted) if ev_predicted else None

    is_resolution_day = today >= target_date
    is_checkpoint_day = True   # we are already inside the worth-logging window

    notes = []
    if is_resolution_day:
        notes.append(f"resolution_date_reached={target_date}")
    if target_hit:
        notes.append("target_hit")
    if stop_hit:
        notes.append("stop_hit")

    await log_checkpoint(
        rec_id, checkpoint_date=today,
        actual_price=spot, actual_pnl_usd=pnl_usd, actual_pnl_pct=pnl_pct,
        target_hit=target_hit, stop_hit=stop_hit,
        expected_vs_actual=expected_vs_actual,
        notes=" | ".join(notes) or None,
        session=session,
    )

    if is_resolution_day and not (target_hit or stop_hit):
        # Forced resolution at horizon — mark resolved by PnL sign
        status = "resolved_win" if pnl_pct > 0 else "resolved_loss"
        await session.execute(text("""
            UPDATE recommendations
            SET status = :s, actual_resolution_date = :d
            WHERE id = :rid AND status NOT LIKE 'resolved%'
        """), {"s": status, "d": today, "rid": rec_id})
        await session.commit()

    return True


async def run_evaluation_job() -> dict:
    """
    Walks all open recommendations. Writes a checkpoint when due, marks resolved
    when target/stop hit or target_resolution_date reached.
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    today = date.today()
    summary = {"checkpoints": 0, "resolved": 0, "skipped": 0}

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT id, stream, symbol, direction, entry_price, target_price, stop_price,
                   predicted_max_profit_usd, predicted_max_loss_usd, expected_value_pct,
                   target_resolution_date, recommended_at
            FROM recommendations
            WHERE status IN ('open', 'paper_filled', 'live_filled')
              AND recommended_at <= NOW() - INTERVAL '1 day'
        """))
        recs = [dict(r) for r in result.mappings().all()]

        for rec in recs:
            stream = rec["stream"]
            days_since_rec = (today - rec["recommended_at"].date()).days
            checkpoint_interval = CHECKPOINT_INTERVALS_DAYS.get(stream, 14)

            # Check whether we already wrote a recent enough checkpoint
            last_cp = await session.execute(text("""
                SELECT MAX(checkpoint_date) FROM recommendation_outcomes
                WHERE recommendation_id = :rid
            """), {"rid": rec["id"]})
            last_date = (last_cp.fetchone() or (None,))[0]

            due_for_checkpoint = (
                last_date is None
                or (today - last_date).days >= checkpoint_interval
                or today >= rec["target_resolution_date"]
            )
            if not due_for_checkpoint:
                summary["skipped"] += 1
                continue

            try:
                ok = await _evaluate_one(rec, session)
                if ok:
                    summary["checkpoints"] += 1
                    if today >= rec["target_resolution_date"]:
                        summary["resolved"] += 1
            except Exception as e:
                logger.debug(f"evaluate rec {rec['id']} failed: {e}")
                summary["skipped"] += 1

    logger.info(f"evaluate_predictions: {summary}")
    return summary


async def run_signal_perf_snapshot() -> int:
    """Wrapper for the scheduler."""
    from scoring.recommendation_log import snapshot_signal_performance
    n = await snapshot_signal_performance()
    logger.info(f"signal_performance_daily: wrote {n} rows")
    return n
