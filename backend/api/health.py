"""
/api/health — single-call health probe for every external dependency.

Status:
  green: dependency reachable AND working
  yellow: reachable but degraded (e.g. stale data, partial response)
  red: not reachable, system silently degraded — Discord alert fires

Endpoints:
  GET /api/health          — JSON of every component's status
  GET /api/health/quick    — single liveness boolean for uptime monitors
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from fastapi import APIRouter


async def _check_postgres() -> dict:
    t0 = time.perf_counter()
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "green", "latency_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"status": "red", "error": str(e)[:200]}


async def _check_redis() -> dict:
    t0 = time.perf_counter()
    try:
        from core.redis_client import cache_set, cache_get
        await cache_set("health:probe", "ok", ttl=10)
        v = await cache_get("health:probe")
        if v != "ok":
            return {"status": "yellow", "note": f"unexpected value {v!r}"}
        return {"status": "green", "latency_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"status": "red", "error": str(e)[:200]}


async def _check_marketdata() -> dict:
    from core.config import settings
    if not settings.MARKETDATA_API_KEY:
        return {"status": "yellow", "note": "MARKETDATA_API_KEY not set"}
    t0 = time.perf_counter()
    try:
        from data.marketdata import MarketDataClient
        client = MarketDataClient()
        chain = await client.get_options_chain("SPY", expiry="2099-12-19")
        # 204 / empty is fine — proves auth works
        return {
            "status": "green",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "note": f"returned {len(chain)} contracts (auth verified)",
        }
    except Exception as e:
        return {"status": "red", "error": str(e)[:200]}


async def _check_fmp() -> dict:
    from core.config import settings
    if not settings.FMP_API_KEY:
        return {"status": "yellow", "note": "FMP_API_KEY not set (insiders, fundamentals, PEAD degraded)"}
    t0 = time.perf_counter()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://financialmodelingprep.com/api/v3/profile/AAPL",
                params={"apikey": settings.FMP_API_KEY},
            )
            if r.status_code == 200:
                return {"status": "green", "latency_ms": int((time.perf_counter() - t0) * 1000)}
            return {"status": "red", "error": f"status={r.status_code}"}
    except Exception as e:
        return {"status": "red", "error": str(e)[:200]}


async def _check_fred() -> dict:
    from core.config import settings
    if not settings.FRED_API_KEY:
        return {"status": "yellow", "note": "FRED_API_KEY not set (macro signals degraded)"}
    t0 = time.perf_counter()
    try:
        from data.macro_feeds import _fred_latest
        out = await _fred_latest("T10Y2Y")
        if out is None:
            return {"status": "red", "error": "no data returned"}
        return {"status": "green", "latency_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as e:
        return {"status": "red", "error": str(e)[:200]}


async def _check_anthropic() -> dict:
    from core.config import settings
    if not settings.ANTHROPIC_API_KEY:
        return {"status": "yellow",
                "note": "ANTHROPIC_API_KEY not set (live LLM scans disabled; backtest unaffected)"}
    return {"status": "green", "note": "key present (no live ping to avoid cost)"}


async def _check_ollama() -> dict:
    t0 = time.perf_counter()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            from core.config import settings
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if r.status_code != 200:
                return {"status": "yellow", "note": f"ollama returned {r.status_code}"}
            data = r.json()
            models = [m["name"] for m in data.get("models", [])]
            return {
                "status": "green",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "models": models,
            }
    except Exception as e:
        return {"status": "yellow", "error": str(e)[:200],
                "note": "ollama unreachable (adversary, sentiment, embeddings degrade)"}


async def _check_feature_store() -> dict:
    try:
        from store.feature_store import get_feature_store
        s = get_feature_store()
        latest = s.latest_snapshot()
        if not latest:
            return {"status": "yellow", "note": "empty — run backfill_feature_store"}
        latest_d, row_count = latest
        age = (datetime.utcnow().date() - latest_d).days
        if age <= 1:
            return {"status": "green", "latest": str(latest_d), "rows": row_count}
        if age <= 3:
            return {"status": "yellow", "latest": str(latest_d),
                    "note": f"snapshot is {age}d old"}
        return {"status": "red", "latest": str(latest_d),
                "note": f"snapshot is {age}d old — nightly scan likely failing"}
    except Exception as e:
        return {"status": "red", "error": str(e)[:200]}


async def _check_marketdata_cache() -> dict:
    try:
        from pathlib import Path
        import os
        root = Path(os.environ.get("MARKETDATA_CACHE_ROOT", "data/marketdata_cache"))
        if not root.exists():
            return {"status": "yellow", "note": "no chains cached yet"}
        files = list(root.glob("**/*.parquet"))
        size_mb = sum(f.stat().st_size for f in files) / 1e6
        return {"status": "green", "chains_cached": len(files),
                "size_mb": round(size_mb, 1)}
    except Exception as e:
        return {"status": "yellow", "error": str(e)[:200]}


def get_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict:
        import asyncio
        pg, rd, md, fmp, fred, anthropic, ollama, fs, md_cache = await asyncio.gather(
            _check_postgres(),
            _check_redis(),
            _check_marketdata(),
            _check_fmp(),
            _check_fred(),
            _check_anthropic(),
            _check_ollama(),
            _check_feature_store(),
            _check_marketdata_cache(),
        )
        components = {
            "postgres": pg, "redis": rd, "marketdata": md, "fmp": fmp,
            "fred": fred, "anthropic": anthropic, "ollama": ollama,
            "feature_store": fs, "marketdata_cache": md_cache,
        }
        reds = [k for k, v in components.items() if v.get("status") == "red"]
        yellows = [k for k, v in components.items() if v.get("status") == "yellow"]
        overall = "red" if reds else ("yellow" if yellows else "green")
        return {
            "overall": overall,
            "reds": reds,
            "yellows": yellows,
            "components": components,
            "checked_at": datetime.utcnow().isoformat(),
        }

    @router.get("/health/quick")
    async def quick() -> dict:
        try:
            pg = await _check_postgres()
            return {"ok": pg["status"] == "green"}
        except Exception:
            return {"ok": False}

    return router
