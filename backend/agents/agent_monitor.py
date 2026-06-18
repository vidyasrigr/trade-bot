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

# Pricing in USD per 1M tokens (input, output)
_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "claude-opus-4-6":           (15.0,  75.0),
    "claude-opus-4-7":           (15.0,  75.0),
    "claude-sonnet-4-6":         (3.0,   15.0),
    "claude-sonnet-4-7":         (3.0,   15.0),
    "claude-haiku-4-5-20251001": (0.80,  4.0),
    "claude-haiku-4-5":          (0.80,  4.0),
    # Ollama models are local/free
    "llama3.1:8b":               (0.0,   0.0),
    "deepseek-r1:7b":            (0.0,   0.0),
    "deepseek-r1:14b":           (0.0,   0.0),
    "nomic-embed-text":          (0.0,   0.0),
}


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = _PRICING_PER_1M.get(model, (3.0, 15.0))  # default sonnet pricing
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 8)


# Fallback phrases that indicate a model returned garbage instead of an answer
_FALLBACK_PHRASES = [
    "unavailable", "analysis unavailable", "offline", "failed", "error",
    "cannot", "i don't", "i do not", "no data",
]


@dataclass
class AgentCall:
    agent_name: str          # "fundamental_analyst", "trader_agent", "adversary", etc.
    model: str               # "claude-sonnet-4-6", "deepseek-r1:7b", etc.
    symbol: str
    elapsed_ms: float
    output_length: int       # character count
    has_fallback: bool       # True if output contains a fallback/error phrase
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
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
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Fire-and-forget: log one agent call. Never raises."""
    try:
        cost = _calc_cost(model, input_tokens, output_tokens)
        call = AgentCall(
            agent_name=agent_name,
            model=model,
            symbol=symbol,
            elapsed_ms=round(elapsed_ms, 1),
            output_length=len(response),
            has_fallback=_is_fallback(response),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            extra=extra or {},
        )
        await _append_to_redis(call)
    except Exception as e:
        logger.debug(f"AgentMonitor.record failed silently: {e}")


async def _append_to_redis(call: AgentCall) -> None:
    import orjson
    from core.redis_client import get_redis
    try:
        r = await get_redis()

        # Per-agent call log (existing)
        key = f"monitor:calls:{call.agent_name}"
        payload = orjson.dumps({
            "model": call.model,
            "symbol": call.symbol,
            "elapsed_ms": call.elapsed_ms,
            "output_length": call.output_length,
            "has_fallback": call.has_fallback,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cost_usd": call.cost_usd,
            "timestamp": call.timestamp,
            **call.extra,
        }).decode()
        await r.lpush(key, payload)
        await r.ltrim(key, 0, 499)
        await r.expire(key, 86400 * 30)

        # Global cost event log — for timeline aggregation
        cost_payload = orjson.dumps({
            "agent": call.agent_name,
            "model": call.model,
            "symbol": call.symbol,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cost_usd": call.cost_usd,
            "elapsed_ms": call.elapsed_ms,
            "timestamp": call.timestamp,
        }).decode()
        await r.lpush("monitor:cost_events", cost_payload)
        await r.ltrim("monitor:cost_events", 0, 9999)
        await r.expire("monitor:cost_events", 86400 * 30)
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


async def get_cost_stats(period: str = "daily") -> dict[str, Any]:
    """
    Aggregate token + cost usage from Redis cost event log.
    period: "hourly" (last 24h by hour) | "daily" (last 7d by day) | "weekly" (last 4w by week)
    """
    import orjson
    from core.redis_client import get_redis
    from collections import defaultdict

    try:
        r = await get_redis()
    except Exception:
        return {"error": "Redis unavailable"}

    raw_list = await r.lrange("monitor:cost_events", 0, 9999)
    if not raw_list:
        return {"period": period, "summary": _empty_summary(), "by_model": [], "by_agent": [], "timeline": []}

    events = []
    for raw in raw_list:
        try:
            events.append(orjson.loads(raw))
        except Exception:
            continue

    # Determine cutoff and bucket function
    now = datetime.utcnow()
    if period == "hourly":
        cutoff = now - timedelta(hours=24)
        def bucket(ts: datetime) -> str:
            return ts.strftime("%Y-%m-%d %H:00")
        def all_buckets() -> list[str]:
            return [(now - timedelta(hours=i)).strftime("%Y-%m-%d %H:00") for i in range(23, -1, -1)]
    elif period == "weekly":
        cutoff = now - timedelta(weeks=4)
        def bucket(ts: datetime) -> str:
            start = ts - timedelta(days=ts.weekday())
            return start.strftime("%Y-%m-%d")
        def all_buckets() -> list[str]:
            buckets = []
            for w in range(3, -1, -1):
                d = now - timedelta(weeks=w)
                buckets.append((d - timedelta(days=d.weekday())).strftime("%Y-%m-%d"))
            return list(dict.fromkeys(buckets))
    else:  # daily
        cutoff = now - timedelta(days=7)
        def bucket(ts: datetime) -> str:
            return ts.strftime("%Y-%m-%d")
        def all_buckets() -> list[str]:
            return [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

    # Filter to window
    filtered = []
    for e in events:
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", ""))
            if ts >= cutoff:
                e["_ts"] = ts
                filtered.append(e)
        except Exception:
            continue

    def _new_bucket() -> dict:
        return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    by_model: dict[str, dict] = defaultdict(lambda: {**_new_bucket(), "model": ""})
    by_agent: dict[str, dict] = defaultdict(lambda: {**_new_bucket(), "agent": "", "model": ""})
    timeline: dict[str, dict] = defaultdict(_new_bucket)

    total = _new_bucket()

    for e in filtered:
        m = e.get("model", "unknown")
        a = e.get("agent", "unknown")
        b = bucket(e["_ts"])
        inp = e.get("input_tokens", 0)
        out = e.get("output_tokens", 0)
        cost = e.get("cost_usd", 0.0)

        for d in [by_model[m], by_agent[a], timeline[b], total]:
            d["calls"] += 1
            d["input_tokens"] += inp
            d["output_tokens"] += out
            d["cost_usd"] += cost

        by_model[m]["model"] = m
        by_agent[a]["agent"] = a
        by_agent[a]["model"] = m  # last seen model for agent

    # Build timeline with all expected buckets (fill zeros for missing)
    buckets_list = all_buckets()
    timeline_out = []
    for b in buckets_list:
        row = timeline.get(b, _new_bucket())
        timeline_out.append({
            "bucket": b,
            "calls": row["calls"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cost_usd": round(row["cost_usd"], 6),
        })

    def _fmt(d: dict) -> dict:
        d["cost_usd"] = round(d["cost_usd"], 6)
        return d

    return {
        "period": period,
        "summary": {
            "total_cost_usd": round(total["cost_usd"], 6),
            "total_input_tokens": total["input_tokens"],
            "total_output_tokens": total["output_tokens"],
            "total_calls": total["calls"],
        },
        "by_model": sorted([_fmt(v) for v in by_model.values()], key=lambda x: -x["cost_usd"]),
        "by_agent": sorted([_fmt(v) for v in by_agent.values()], key=lambda x: -x["cost_usd"]),
        "timeline": timeline_out,
    }


def _empty_summary() -> dict:
    return {"total_cost_usd": 0.0, "total_input_tokens": 0, "total_output_tokens": 0, "total_calls": 0}


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
        async with track("trader_agent", "claude-sonnet-4-6", symbol) as t:
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
