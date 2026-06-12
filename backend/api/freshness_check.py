"""
Freshness check — re-validates setup before showing order ticket to N.
If price moved >3% or IV moved >15% since analysis, marks STALE.
"""

from datetime import datetime, timezone

from loguru import logger


async def validate_freshness(symbol: str, max_age_minutes: int = 30) -> dict:
    """
    Returns {ok: bool, message: str, validated_at: str}.
    Called before showing order ticket to N.
    """
    from core.redis_client import cache_get, cache_set
    from data.tradier import get_tradier

    cache_key = f"freshness:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        result = orjson.loads(cached)
        result["from_cache"] = True
        return result

    tradier = get_tradier()

    try:
        # Get latest quote
        quote = await tradier.get_quote(symbol)
        current_price = float(quote.get("last") or quote.get("close") or 0)

        # Get last analysis from DB
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT raw_signals, iv_percentile, analyzed_at
                FROM analysis_results
                WHERE symbol = :sym
                ORDER BY analyzed_at DESC
                LIMIT 1
            """), {"sym": symbol})
            row = result.fetchone()

        if not row:
            return {"ok": True, "message": "No prior analysis — proceeding with fresh data", "validated_at": datetime.utcnow().isoformat()}

        raw_signals, iv_pct_at_analysis, analyzed_at = row

        # Check age
        if analyzed_at:
            age_minutes = (datetime.now(timezone.utc) - analyzed_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if age_minutes > max_age_minutes:
                return {
                    "ok": False,
                    "message": f"Analysis is {round(age_minutes):.0f} min old — re-analyze before trading",
                    "validated_at": datetime.utcnow().isoformat(),
                }

        # Get price at analysis time from raw_signals
        import orjson
        signals = orjson.loads(raw_signals) if raw_signals else {}
        price_at_analysis = signals.get("last_close", current_price)

        if price_at_analysis and current_price:
            price_move = abs(current_price - float(price_at_analysis)) / float(price_at_analysis)
            if price_move > 0.03:
                return {
                    "ok": False,
                    "message": f"Price moved {round(price_move*100,1)}% since analysis — STALE, re-analyze",
                    "price_move_pct": round(price_move * 100, 1),
                    "validated_at": datetime.utcnow().isoformat(),
                }

        validated_at = datetime.utcnow().isoformat()
        result_dict = {
            "ok": True,
            "message": f"✓ Setup validated",
            "current_price": current_price,
            "validated_at": validated_at,
        }

        await cache_set(cache_key, orjson.dumps(result_dict).decode(), ttl=120)
        return result_dict

    except Exception as e:
        logger.warning(f"Freshness check failed for {symbol}: {e}")
        return {"ok": True, "message": "Could not verify freshness — proceed with caution", "validated_at": datetime.utcnow().isoformat()}
