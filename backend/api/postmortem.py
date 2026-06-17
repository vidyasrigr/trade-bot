"""
/api/postmortem/* — exports the recommendation log, outcomes, and signal
performance history in a format a future LLM (or you) can read to do a real
postmortem and improve the system.

Endpoints:
  GET /api/postmortem/recommendations  — full recommendation history (paginated)
  GET /api/postmortem/signal/{name}    — one signal's full performance timeline
  GET /api/postmortem/summary          — high-level system metrics
  GET /api/postmortem/export           — single JSON blob covering everything,
                                          ready to paste into the next-gen model
"""

from __future__ import annotations

from fastapi import APIRouter, Query


def get_router() -> APIRouter:
    router = APIRouter()

    @router.get("/postmortem/recommendations")
    async def list_recommendations(
        stream: str | None = None,
        status: str | None = None,
        limit: int = Query(200, le=2000),
    ) -> dict:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        clauses, params = ["1=1"], {"limit": limit}
        if stream:
            clauses.append("rec.stream = :stream"); params["stream"] = stream
        if status:
            clauses.append("rec.status = :status"); params["status"] = status
        sql = f"""
            SELECT rec.id, rec.recommended_at, rec.stream, rec.symbol, rec.strategy,
                   rec.direction, rec.conviction, rec.entry_price, rec.target_price,
                   rec.stop_price, rec.predicted_max_profit_usd, rec.predicted_max_loss_usd,
                   rec.expected_value_pct, rec.prob_profit,
                   rec.target_resolution_date, rec.actual_resolution_date,
                   rec.thesis, rec.signals_fired,
                   rec.market_climate, rec.stock_climate,
                   rec.model_version, rec.status,
                   (SELECT JSON_AGG(o.*) FROM recommendation_outcomes o
                    WHERE o.recommendation_id = rec.id) AS outcomes
            FROM recommendations rec
            WHERE {' AND '.join(clauses)}
            ORDER BY rec.recommended_at DESC
            LIMIT :limit
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(sql), params)
            rows = [dict(r) for r in result.mappings().all()]
        return {"count": len(rows), "recommendations": rows}

    @router.get("/postmortem/signal/{name}")
    async def signal_timeline(name: str, days: int = 365) -> dict:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            r = await session.execute(text("""
                SELECT * FROM signal_performance_daily
                WHERE signal_name = :n AND as_of_date >= CURRENT_DATE - :d
                ORDER BY as_of_date
            """), {"n": name, "d": days})
            timeline = [dict(x) for x in r.mappings().all()]

            r2 = await session.execute(text("""
                SELECT id, recommended_at, stream, symbol, status, conviction
                FROM recommendations WHERE :n = ANY(signals_fired)
                ORDER BY recommended_at DESC LIMIT 200
            """), {"n": name})
            recs = [dict(x) for x in r2.mappings().all()]
        return {"signal": name, "timeline": timeline, "recent_recommendations": recs}

    @router.get("/postmortem/summary")
    async def summary() -> dict:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            r = await session.execute(text("""
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status LIKE 'resolved%') AS resolved,
                  COUNT(*) FILTER (WHERE status = 'resolved_win') AS wins,
                  COUNT(*) FILTER (WHERE status = 'resolved_loss') AS losses,
                  COUNT(*) FILTER (WHERE status IN ('open', 'paper_filled', 'live_filled')) AS open,
                  COUNT(DISTINCT stream) AS streams_in_use,
                  AVG(conviction) FILTER (WHERE status = 'resolved_win') AS avg_conviction_wins,
                  AVG(conviction) FILTER (WHERE status = 'resolved_loss') AS avg_conviction_losses
                FROM recommendations
            """))
            top = dict(r.mappings().first() or {})

            r2 = await session.execute(text("""
                SELECT stream, COUNT(*) AS n,
                       AVG((status='resolved_win')::int) FILTER (WHERE status LIKE 'resolved%') AS hit_rate
                FROM recommendations GROUP BY stream
            """))
            by_stream = [dict(x) for x in r2.mappings().all()]
        return {"system": top, "by_stream": by_stream}

    @router.get("/postmortem/export")
    async def export_all(limit: int = 5000) -> dict:
        """Single JSON blob for handoff to a next-gen analysis model."""
        summary_data = await summary()
        recs_data = await list_recommendations(limit=limit)

        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            r = await session.execute(text("""
                SELECT signal_name, AVG(hit_rate_30d) AS hr30,
                       AVG(hit_rate_total) AS hr_total,
                       AVG(mean_excess_return_30d) AS er30,
                       MAX(last_dsr) AS last_dsr,
                       MAX(promotion_status) AS promotion_status
                FROM signal_performance_daily
                GROUP BY signal_name
            """))
            signal_summary = [dict(x) for x in r.mappings().all()]

            r2 = await session.execute(text("""
                SELECT model_id, COUNT(*) AS calls,
                       AVG(latency_ms) AS avg_ms, SUM(cost_usd) AS total_cost
                FROM model_decisions GROUP BY model_id
            """))
            model_usage = [dict(x) for x in r2.mappings().all()]
        return {
            "system_summary": summary_data,
            "signal_summary": signal_summary,
            "model_usage": model_usage,
            "recent_recommendations": recs_data["recommendations"],
            "schema_note": "Each recommendation row includes its outcomes[] for direct expected-vs-actual analysis.",
        }

    return router
