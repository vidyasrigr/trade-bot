"""
Recommendation log + outcomes tracking.

Every pipeline output (options ticket, swing pick, mid-term setup, LT candidate)
gets one row in `recommendations`. The row records:
  - what we PREDICTED at the time (target, stop, EV, prob_profit, horizon)
  - which signals fired
  - which models reasoned about it
  - the raw ticket as JSONB for forensic replay

Then `recommendation_outcomes` adds checkpoint rows over the holding period.

A scheduled nightly job (`evaluate_predictions.py`) walks open recommendations
whose `target_resolution_date <= today` and logs the actual outcome. This works
for any horizon — a swing rec from 3 weeks ago resolves at 3 weeks; an LT rec
from 6 months ago resolves at 6 months. The system never forgets.

Usage at recommendation time:
    rec_id = await log_recommendation(stream='options', symbol='NVDA', ...)

Usage at outcome time (auto from the scheduled job):
    await log_checkpoint(rec_id, checkpoint_date=today, actual_price=..., ...)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Iterable

from loguru import logger


STREAM_DEFAULT_HORIZON_DAYS = {
    "options": 30,         # avg options hold
    "swing": 14,           # 1-4 weeks
    "mid_term": 75,        # 1-3 months
    "long_term": 180,      # ~6 months default, can be overridden
}


@dataclass
class RecommendationInput:
    stream: str
    symbol: str
    strategy: str | None = None
    direction: str | None = None
    conviction: float | None = None
    entry_price: float | None = None
    target_price: float | None = None
    stop_price: float | None = None
    predicted_max_profit_usd: float | None = None
    predicted_max_loss_usd: float | None = None
    expected_value_pct: float | None = None
    prob_profit: float | None = None
    target_resolution_date: date | None = None
    thesis: str | None = None
    signals_fired: list[str] | None = None
    market_climate: str | None = None
    stock_climate: str | None = None
    model_version: str | None = None
    pipeline_version: str | None = None
    raw_ticket: dict | None = None

    def default_resolution(self) -> date:
        days = STREAM_DEFAULT_HORIZON_DAYS.get(self.stream, 30)
        return date.today() + timedelta(days=days)


async def log_recommendation(rec: RecommendationInput, session=None) -> int:
    """Insert the recommendation. Returns the new id."""
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await log_recommendation(rec, s)

    from sqlalchemy import text
    import orjson

    target_res = rec.target_resolution_date or rec.default_resolution()
    raw = orjson.dumps(rec.raw_ticket or {}).decode()
    signals = rec.signals_fired or []

    result = await session.execute(text("""
        INSERT INTO recommendations
            (stream, symbol, strategy, direction, conviction,
             entry_price, target_price, stop_price,
             predicted_max_profit_usd, predicted_max_loss_usd,
             expected_value_pct, prob_profit,
             target_resolution_date, thesis,
             signals_fired, market_climate, stock_climate,
             model_version, pipeline_version, raw_ticket)
        VALUES
            (:stream, :symbol, :strategy, :direction, :conviction,
             :entry, :target, :stop,
             :pmp, :pml,
             :ev, :pp,
             :target_res, :thesis,
             :sigs, :mc, :sc,
             :mv, :pv, :raw::jsonb)
        RETURNING id
    """), {
        "stream": rec.stream, "symbol": rec.symbol,
        "strategy": rec.strategy, "direction": rec.direction,
        "conviction": rec.conviction,
        "entry": rec.entry_price, "target": rec.target_price, "stop": rec.stop_price,
        "pmp": rec.predicted_max_profit_usd, "pml": rec.predicted_max_loss_usd,
        "ev": rec.expected_value_pct, "pp": rec.prob_profit,
        "target_res": target_res,
        "thesis": (rec.thesis or "")[:8000],
        "sigs": signals,
        "mc": rec.market_climate, "sc": rec.stock_climate,
        "mv": rec.model_version, "pv": rec.pipeline_version,
        "raw": raw,
    })
    rec_id = int(result.fetchone()[0])
    await session.commit()
    return rec_id


async def link_to_paper_trade(rec_id: int, paper_trade_id: int, session=None) -> None:
    """When a recommendation becomes a paper trade, link them."""
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await link_to_paper_trade(rec_id, paper_trade_id, s)
    from sqlalchemy import text
    await session.execute(text("""
        UPDATE recommendations
        SET paper_trade_id = :tid, status = 'paper_filled'
        WHERE id = :rid AND status = 'open'
    """), {"tid": paper_trade_id, "rid": rec_id})
    await session.commit()


async def log_checkpoint(
    recommendation_id: int,
    *,
    checkpoint_date: date,
    actual_price: float | None,
    actual_pnl_usd: float | None = None,
    actual_pnl_pct: float | None = None,
    target_hit: bool = False,
    stop_hit: bool = False,
    drawdown_max: float | None = None,
    expected_vs_actual: float | None = None,
    notes: str | None = None,
    session=None,
) -> int:
    """Log a checkpoint row. Idempotent per (rec_id, date)."""
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await log_checkpoint(
                recommendation_id,
                checkpoint_date=checkpoint_date, actual_price=actual_price,
                actual_pnl_usd=actual_pnl_usd, actual_pnl_pct=actual_pnl_pct,
                target_hit=target_hit, stop_hit=stop_hit,
                drawdown_max=drawdown_max, expected_vs_actual=expected_vs_actual,
                notes=notes, session=s,
            )

    from sqlalchemy import text

    # Read rec to compute days elapsed
    rec_row = await session.execute(text("""
        SELECT recommended_at::date FROM recommendations WHERE id = :rid
    """), {"rid": recommendation_id})
    row = rec_row.fetchone()
    if row is None:
        logger.warning(f"log_checkpoint: recommendation {recommendation_id} not found")
        return 0
    rec_date = row[0]
    days_elapsed = (checkpoint_date - rec_date).days

    result = await session.execute(text("""
        INSERT INTO recommendation_outcomes
            (recommendation_id, checkpoint_date, days_elapsed,
             actual_price, actual_pnl_usd, actual_pnl_pct,
             target_hit, stop_hit, drawdown_max,
             expected_vs_actual, notes)
        VALUES
            (:rid, :cd, :de, :ap, :ap_usd, :ap_pct,
             :th, :sh, :dd, :eva, :notes)
        ON CONFLICT (recommendation_id, checkpoint_date) DO UPDATE SET
            actual_price = EXCLUDED.actual_price,
            actual_pnl_usd = EXCLUDED.actual_pnl_usd,
            actual_pnl_pct = EXCLUDED.actual_pnl_pct,
            target_hit = EXCLUDED.target_hit,
            stop_hit = EXCLUDED.stop_hit,
            drawdown_max = EXCLUDED.drawdown_max,
            expected_vs_actual = EXCLUDED.expected_vs_actual,
            notes = EXCLUDED.notes
        RETURNING id
    """), {
        "rid": recommendation_id, "cd": checkpoint_date, "de": days_elapsed,
        "ap": actual_price, "ap_usd": actual_pnl_usd, "ap_pct": actual_pnl_pct,
        "th": target_hit, "sh": stop_hit, "dd": drawdown_max,
        "eva": expected_vs_actual, "notes": (notes or "")[:2000],
    })
    out_id = int(result.fetchone()[0])

    # Resolve the parent if target or stop hit
    if target_hit or stop_hit:
        new_status = "resolved_win" if (actual_pnl_usd or 0) > 0 else "resolved_loss"
        await session.execute(text("""
            UPDATE recommendations
            SET status = :s, actual_resolution_date = :cd
            WHERE id = :rid AND status NOT LIKE 'resolved%'
        """), {"s": new_status, "cd": checkpoint_date, "rid": recommendation_id})

    await session.commit()
    return out_id


async def log_model_decision(
    recommendation_id: int | None,
    *,
    agent_role: str,
    model_id: str,
    prompt: str | None = None,
    raw_response: str | None = None,
    structured_output: dict | None = None,
    latency_ms: int | None = None,
    cost_usd: float | None = None,
    session=None,
) -> int:
    """Lineage trail for an LLM call. prompt_hash is stored, prompt body is not."""
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await log_model_decision(
                recommendation_id,
                agent_role=agent_role, model_id=model_id,
                prompt=prompt, raw_response=raw_response,
                structured_output=structured_output,
                latency_ms=latency_ms, cost_usd=cost_usd, session=s,
            )

    from sqlalchemy import text
    import orjson

    prompt_hash = hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()[:32] if prompt else None
    result = await session.execute(text("""
        INSERT INTO model_decisions
            (recommendation_id, agent_role, model_id, prompt_hash,
             raw_response, structured_output, latency_ms, cost_usd)
        VALUES
            (:rid, :role, :mid, :hash, :raw, :so::jsonb, :lat, :cost)
        RETURNING id
    """), {
        "rid": recommendation_id,
        "role": agent_role, "mid": model_id, "hash": prompt_hash,
        "raw": (raw_response or "")[:50_000],
        "so": orjson.dumps(structured_output or {}).decode(),
        "lat": latency_ms, "cost": cost_usd,
    })
    out_id = int(result.fetchone()[0])
    await session.commit()
    return out_id


# ---------------------------------------------------------------------------
# Daily signal performance snapshot
# ---------------------------------------------------------------------------

async def snapshot_signal_performance(as_of: date | None = None, session=None) -> int:
    """
    Nightly: write one row per signal into signal_performance_daily summarizing
    fires + hit_rate over recent windows. Pulls from signal_ranks, recommendations,
    recommendation_outcomes, factor_ic_scores, backtest_runs.
    """
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await snapshot_signal_performance(as_of, s)

    from sqlalchemy import text
    from scoring.signal_registry import REGISTRY

    today = as_of or date.today()
    written = 0
    for spec in REGISTRY:
        try:
            # Fires today + trailing 30d (from signal_ranks)
            r = await session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE as_of_date = :today)         AS today_n,
                    COUNT(*) FILTER (WHERE as_of_date >= :today - 30)   AS m30_n,
                    COUNT(*)                                             AS total_n
                FROM signal_ranks WHERE signal_type = :sig
            """), {"today": today, "sig": spec.name})
            counts = r.fetchone() or (0, 0, 0)

            # Hit rate 30d / total — from recommendations that fired this signal AND resolved
            r2 = await session.execute(text("""
                SELECT
                    AVG((status = 'resolved_win')::int) FILTER (
                        WHERE recommended_at >= NOW() - INTERVAL '30 days'
                    ) AS hit30,
                    AVG((status = 'resolved_win')::int) AS hit_total,
                    AVG(o.actual_pnl_pct) FILTER (
                        WHERE recommended_at >= NOW() - INTERVAL '30 days'
                    ) AS er30,
                    AVG(o.actual_pnl_pct) AS er_total
                FROM recommendations rec
                LEFT JOIN LATERAL (
                    SELECT actual_pnl_pct FROM recommendation_outcomes
                    WHERE recommendation_id = rec.id
                    ORDER BY checkpoint_date DESC LIMIT 1
                ) o ON TRUE
                WHERE :sig = ANY(rec.signals_fired)
                  AND rec.status LIKE 'resolved%'
            """), {"sig": spec.name})
            perf = r2.fetchone() or (None, None, None, None)

            # IC score + weight from factor_ic_scores (regime='all')
            r3 = await session.execute(text("""
                SELECT ic_score, current_weight_multiplier, signal_status
                FROM factor_ic_scores WHERE category = :sig AND regime = 'all'
            """), {"sig": spec.name})
            ic_row = r3.fetchone() or (None, None, None)

            # Most-recent DSR from backtest_runs
            r4 = await session.execute(text("""
                SELECT deflated_sharpe, created_at
                FROM backtest_runs
                WHERE strategy = :sig
                ORDER BY created_at DESC LIMIT 1
            """), {"sig": spec.name})
            bt = r4.fetchone() or (None, None)

            await session.execute(text("""
                INSERT INTO signal_performance_daily
                    (signal_name, as_of_date, fires_today, fires_trailing_30d, fires_total,
                     hit_rate_30d, hit_rate_total, mean_excess_return_30d,
                     mean_excess_return_total, ic_score, weight_multiplier,
                     promotion_status, last_dsr, last_dsr_at)
                VALUES
                    (:sig, :d, :ft, :f30, :ftot,
                     :h30, :htot, :er30, :ertot, :ic, :wm,
                     :ps, :dsr, :dsrat)
                ON CONFLICT (signal_name, as_of_date) DO UPDATE SET
                    fires_today = EXCLUDED.fires_today,
                    fires_trailing_30d = EXCLUDED.fires_trailing_30d,
                    fires_total = EXCLUDED.fires_total,
                    hit_rate_30d = EXCLUDED.hit_rate_30d,
                    hit_rate_total = EXCLUDED.hit_rate_total,
                    mean_excess_return_30d = EXCLUDED.mean_excess_return_30d,
                    mean_excess_return_total = EXCLUDED.mean_excess_return_total,
                    ic_score = EXCLUDED.ic_score,
                    weight_multiplier = EXCLUDED.weight_multiplier,
                    promotion_status = EXCLUDED.promotion_status,
                    last_dsr = EXCLUDED.last_dsr,
                    last_dsr_at = EXCLUDED.last_dsr_at
            """), {
                "sig": spec.name, "d": today,
                "ft": int(counts[0] or 0), "f30": int(counts[1] or 0), "ftot": int(counts[2] or 0),
                "h30": perf[0], "htot": perf[1],
                "er30": perf[2], "ertot": perf[3],
                "ic": ic_row[0], "wm": ic_row[1], "ps": ic_row[2] or spec.promotion_status,
                "dsr": bt[0], "dsrat": bt[1],
            })
            written += 1
        except Exception as e:
            logger.debug(f"signal_performance_daily failed for {spec.name}: {e}")
    await session.commit()
    return written
