"""FMP analyst price targets + EPS revision direction tracking."""

from __future__ import annotations

import httpx
from loguru import logger
from core.config import settings
from core.redis_client import cache_get, cache_set


async def get_consensus_gap(symbol: str) -> dict | None:
    """Returns {consensus_target, current_price, upside_pct, analyst_count}."""
    if not settings.FMP_API_KEY:
        return None

    cache_key = f"analyst_targets:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v4/price-target-consensus",
                params={"symbol": symbol, "apikey": settings.FMP_API_KEY},
            )
            data = resp.json()

        if not data:
            return None

        target_data = data[0] if isinstance(data, list) else data
        consensus = float(target_data.get("targetConsensus") or 0)

        async with httpx.AsyncClient(timeout=10.0) as client:
            price_resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/quote-short/{symbol}",
                params={"apikey": settings.FMP_API_KEY},
            )
            price_data = price_resp.json()

        current_price = float(price_data[0].get("price", 0)) if price_data else consensus
        upside = (consensus - current_price) / current_price * 100 if current_price > 0 else 0

        result = {
            "symbol": symbol,
            "consensus_target": consensus,
            "current_price": current_price,
            "upside_pct": round(upside, 1),
            "analyst_count": target_data.get("targetNumberOfAnalysts"),
        }

        import orjson
        await cache_set(cache_key, orjson.dumps(result).decode(), ttl=86400)
        return result
    except Exception as e:
        logger.debug(f"FMP analyst targets failed for {symbol}: {e}")
        return None


async def get_recent_revisions(symbol: str, limit: int = 20) -> list[dict]:
    """
    Fetch recent analyst EPS revisions from FMP.
    Returns list of {analyst, firm, old_eps, new_eps, direction, date}.
    Used by compound_signals.py for revision cascade detection.
    """
    if not settings.FMP_API_KEY:
        return []

    cache_key = f"revisions:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v4/price-target",
                params={"symbol": symbol, "limit": limit, "apikey": settings.FMP_API_KEY},
            )
            data = resp.json()

        if not isinstance(data, list):
            return []

        revisions = []
        for item in data[:limit]:
            try:
                new_target = float(item.get("priceTarget") or 0)
                old_target = float(item.get("priorPriceTarget") or 0)

                if old_target > 0 and new_target > 0:
                    direction = (
                        "up" if new_target > old_target * 1.02
                        else "down" if new_target < old_target * 0.98
                        else "flat"
                    )
                else:
                    direction = "flat"

                revisions.append({
                    "analyst": item.get("analystName", ""),
                    "firm": item.get("analystCompany", ""),
                    "new_target": new_target,
                    "old_target": old_target,
                    "direction": direction,
                    "rating": item.get("newGrade", ""),
                    "prior_rating": item.get("previousGrade", ""),
                    "date": (item.get("publishedDate") or "")[:10],
                })
            except (TypeError, ValueError):
                continue

        import orjson
        await cache_set(cache_key, orjson.dumps(revisions).decode(), ttl=21600)
        return revisions

    except Exception as e:
        logger.debug(f"FMP revisions failed for {symbol}: {e}")
        return []


async def get_revision_summary(symbol: str) -> dict:
    """
    Returns a summary of recent analyst revision activity.
    {direction: 'up'|'down'|'flat', up_count, down_count, net, firms_upgrading, firms_downgrading}
    """
    revisions = await get_recent_revisions(symbol, limit=10)
    if not revisions:
        return {"direction": "flat", "up_count": 0, "down_count": 0, "net": 0}

    up = [r for r in revisions if r.get("direction") == "up"]
    down = [r for r in revisions if r.get("direction") == "down"]
    net = len(up) - len(down)

    direction = "up" if net >= 2 else "down" if net <= -2 else "flat"

    return {
        "direction": direction,
        "up_count": len(up),
        "down_count": len(down),
        "net": net,
        "firms_upgrading": [r.get("firm", "") for r in up[:5]],
        "firms_downgrading": [r.get("firm", "") for r in down[:5]],
        "latest_revision_date": revisions[0].get("date") if revisions else None,
    }
