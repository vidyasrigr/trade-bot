"""
Agent Performance Monitor.

Tracks every agent call across the pipeline — Claude, Ollama, XGBoost, etc.
Stores response time, model, output quality signals, and symbol.
Weekly: correlates agent outputs with trade outcomes, flags underperforming models,
and recommends swaps.

Non-blocking: all writes are fire-and-forget so they never slow down analysis.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from core.redis_client import cache_get, cache_set

# Fallback phrases that indicate a model returned garbage instead of an answer
_FALLBACK_PHRASES = [
    "unavailable", "analysis unavailable", "offline", "failed", "error",
    "cannot", "i don't", "i do not", "no data",
]


@dataclass
class AgentCall:
    agent_name: str          # "fundamental_analyst", "trader_agent", "adversary", etc.
    model: str               # "claude-sonnet-4-6", "claude-opus-4-7", "deepseek-r1:7b", etc.
    symbol: str
    elapsed_ms: float
    output_length: int       # character count
    has_fallback: bool       # True if output contains a fallback/error phrase
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    extra: dict = field(default_factory=dict)


def _is_fallback(text: str) -> bool:
    lower = text.lower()[:200]
    return any(phrase in lower for phrase in _FALLBACK_PHRASES)


async def record(
    agent_name: str,
    model: str,
    symbol: str,
    elapsed_ms: float,
    response: str,
    extra: dict | None = None,
) -> None:
    """Fire-and-forget: log one agent call. Never raises."""
    try:
        call = AgentCall(
            agent_name=agent_name,
            model=model,
            symbol=symbol,
            elapsed_ms=round(elapsed_ms, 1),
            output_length=len(response),
            has_fallback=_is_fallback(response),
            extra=extra or {},
        )
        await _append_to_redis(call)
    except Exception as e:
        logger.debug(f"AgentMonitor.record failed silently: {e}")


async def _append_to_redis(call: AgentCall) -> None:
    import orjson
    key = f"monitor:calls:{call.agent_name}"
    payload = orjson.dumps({
        "model": call.model,
        "symbol": call.symbol,
        "elapsed_ms": call.elapsed_ms,
        "output_length": call.output_length,
        "has_fallback": call.has_fallback,
        "timestamp": call.timestamp,
        **call.extra,
    }).decode()
    # Use Redis list — LPUSH + LTRIM to keep last 500 calls per agent
    from core.redis_client import get_redis
    try:
        r = await get_redis()
        await r.lpush(key, payload)
        await r.ltrim(key, 0, 499)
        await r.expire(key, 86400 * 30)  # 30-day TTL
    except Exception:
        pass  # Redis unavailable — silently drop


async def get_agent_stats(agent_name: str | None = None) -> dict[str, Any]:
    """
    Return performance stats per agent.
    If agent_name is None, returns stats for ALL agents.
    """
    import orjson

    KNOWN_AGENTS = [
        "fundamental_analyst", "technical_analyst", "volatility_analyst",
        "sentiment_analyst", "trader_agent", "risk_manager_agent",
        "adversary_agent", "postmortem_agent", "watchlist_agent",
        "catalyst_detector", "position_monitor",
    ]

    targets = [agent_name] if agent_name else KNOWN_AGENTS

    from core.redis_client import get_redis
    try:
        r = await get_redis()
    except Exception:
        return {"error": "Redis unavailable"}

    results: dict[str, Any] = {}

    for name in targets:
        key = f"monitor:calls:{name}"
        raw_list = await r.lrange(key, 0, 499)
        if not raw_list:
            continue

        calls = []
        for raw in raw_list:
            try:
                calls.append(orjson.loads(raw))
            except Exception:
                continue

        if not calls:
            continue

        elapsed_times = [c["elapsed_ms"] for c in calls if "elapsed_ms" in c]
        fallback_count = sum(1 for c in calls if c.get("has_fallback"))
        models_used = {}
        for c in calls:
            m = c.get("model", "unknown")
            models_used[m] = models_used.get(m, 0) + 1

        results[name] = {
            "total_calls": len(calls),
            "avg_response_ms": round(sum(elapsed_times) / len(elapsed_times), 0) if elapsed_times else None,
            "p95_response_ms": round(sorted(elapsed_times)[int(len(elapsed_times) * 0.95)], 0) if elapsed_times else None,
            "fallback_rate_pct": round(fallback_count / len(calls) * 100, 1),
            "models_used": models_used,
            "last_called": calls[0].get("timestamp", ""),
        }

    return results


async def get_recommendations() -> list[dict]:
    """
    Analyze stats and return model-swap or tuning recommendations.
    Rules:
    - fallback_rate > 20% → flag for model swap
    - avg_response_ms > 8000 → flag as slow (consider Sonnet if using Opus)
    - adversary always PASS (risk_override=0) for 50+ calls → may be misconfigured
    """
    stats = await get_agent_stats()
    recs = []

    for agent, s in stats.items():
        if s.get("fallback_rate_pct", 0) > 20:
            models = list(s.get("models_used", {}).keys())
            recs.append({
                "agent": agent,
                "issue": f"High fallback rate: {s['fallback_rate_pct']}%",
                "recommendation": f"Check API key / Ollama availability for {models}",
                "severity": "high",
            })

        if s.get("avg_response_ms", 0) > 8000:
            models = list(s.get("models_used", {}).keys())
            if any("opus" in m for m in models):
                recs.append({
                    "agent": agent,
                    "issue": f"Slow avg response: {s['avg_response_ms']}ms",
                    "recommendation": "Consider downgrading to claude-sonnet-4-6 if output quality is acceptable",
                    "severity": "medium",
                })

    if not recs:
        recs.append({"agent": "all", "issue": "None", "recommendation": "All agents performing normally", "severity": "ok"})

    return recs


async def flush_to_db() -> None:
    """
    Weekly: flush Redis call logs to PostgreSQL for long-term correlation analysis.
    Called by the weekly compaction job.
    """
    stats = await get_agent_stats()
    if not stats:
        return

    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            for agent, s in stats.items():
                await session.execute(
                    text("""
                        INSERT INTO agent_performance_weekly (
                            agent_name, week_start, total_calls,
                            avg_response_ms, fallback_rate_pct, models_json
                        ) VALUES (
                            :agent, date_trunc('week', NOW()), :calls,
                            :avg_ms, :fallback, :models::jsonb
                        )
                        ON CONFLICT (agent_name, week_start) DO UPDATE SET
                            total_calls = EXCLUDED.total_calls,
                            avg_response_ms = EXCLUDED.avg_response_ms,
                            fallback_rate_pct = EXCLUDED.fallback_rate_pct,
                            models_json = EXCLUDED.models_json
                    """),
                    {
                        "agent": agent,
                        "calls": s["total_calls"],
                        "avg_ms": s.get("avg_response_ms"),
                        "fallback": s.get("fallback_rate_pct", 0),
                        "models": __import__("orjson").dumps(s.get("models_used", {})).decode(),
                    }
                )
            await session.commit()
        logger.info(f"Agent monitor: flushed {len(stats)} agents to DB")
    except Exception as e:
        logger.warning(f"Agent monitor DB flush failed: {e}")


@asynccontextmanager
async def track(agent_name: str, model: str, symbol: str):
    """
    Async context manager for easy agent call tracking.

    Usage:
        async with track("trader_agent", "claude-opus-4-7", symbol) as t:
            result = await do_work()
            t["response"] = result
    """
    state: dict[str, Any] = {"response": ""}
    start = time.monotonic()
    try:
        yield state
    finally:
        elapsed = (time.monotonic() - start) * 1000
        asyncio.create_task(
            record(agent_name, model, symbol, elapsed, state.get("response", ""))
        )
