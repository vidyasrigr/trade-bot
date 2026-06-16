"""
Catalyst Detection Engine — monitors SEC 8-K + unusual options flow + earnings surprises.
Fires when catalyst detected → auto-queues symbol for full analysis.
"""

import asyncio
from datetime import datetime

from loguru import logger

from core.redis_client import cache_get, cache_set


async def detect_catalysts() -> list[dict]:
    """
    Main catalyst detection loop — runs every 30 min during market hours.
    Returns list of catalyst events detected.
    """
    from data.tradier import get_tradier
    from data.news import get_news_aggregator, get_ollama_filter
    from data.scanner import get_full_universe

    universe = get_full_universe()
    events = []

    # 1. Unusual options volume scan
    volume_events = await _scan_unusual_options_volume(universe[:200])  # top-200 for speed
    events.extend(volume_events)

    # 2. News catalyst scan
    news_events = await _scan_news_catalysts(universe[:200])
    events.extend(news_events)

    # 3. Earnings beat-and-raise compound signal (Phase H.8) —
    # iterate today's earnings releases and fire PEAD signal for mid/small caps.
    try:
        earnings_events = await _fire_earnings_compound_signals(universe[:200])
        events.extend(earnings_events)
    except Exception as e:
        logger.debug(f"earnings compound signals skipped: {e}")

    # 4. Analyst-revision cascade (Phase H.8) — for symbols with recent revisions.
    try:
        revision_events = await _fire_revision_compound_signals(universe[:200])
        events.extend(revision_events)
    except Exception as e:
        logger.debug(f"revision compound signals skipped: {e}")

    # Persist to DB
    await _persist_events(events)

    # Update Redis catalyst queue
    if events:
        import orjson
        await cache_set("catalysts:latest", orjson.dumps(events[:20]).decode(), ttl=3600)

    logger.info(f"Catalyst detection complete: {len(events)} events")
    return events


async def _fire_earnings_compound_signals(symbols: list[str]) -> list[dict]:
    """
    For each symbol that reported earnings in the last 2 trading days, fetch the
    actuals + estimates and fire the beat_and_raise PEAD signal.
    """
    from core.config import settings
    from agents.compound_signals import fire_beat_and_raise
    from core.database import AsyncSessionLocal

    if not settings.FMP_API_KEY:
        return []

    import httpx
    fired: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for sym in symbols:
            try:
                # FMP earning-surprise — most recent quarter
                resp = await client.get(
                    f"https://financialmodelingprep.com/api/v3/earnings-surprises/{sym}",
                    params={"apikey": settings.FMP_API_KEY},
                )
                data = resp.json() if resp.status_code == 200 else []
                if not isinstance(data, list) or not data:
                    continue
                recent = data[0]
                from datetime import date as _date, datetime as _dt, timedelta
                event_date_str = recent.get("date") or ""
                try:
                    event_date = _dt.strptime(event_date_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
                if (_date.today() - event_date) > timedelta(days=2):
                    continue
                eps_actual = float(recent.get("actualEarningResult") or 0)
                eps_estimate = float(recent.get("estimatedEarning") or 0)
                if eps_estimate == 0:
                    continue

                # Pull profile for market cap
                profile_resp = await client.get(
                    f"https://financialmodelingprep.com/api/v3/profile/{sym}",
                    params={"apikey": settings.FMP_API_KEY},
                )
                profile = profile_resp.json() if profile_resp.status_code == 200 else []
                market_cap = float(profile[0].get("mktCap", 0)) if profile else 0
                if market_cap == 0:
                    continue

                async with AsyncSessionLocal() as session:
                    signal = await fire_beat_and_raise(
                        symbol=sym, market_cap=market_cap,
                        eps_actual=eps_actual, eps_estimate=eps_estimate,
                        # FMP earnings-surprises doesn't carry revenue actual/est —
                        # treat as zeros (the function gates on either rev beat OR
                        # raised_guidance; with both unknown the signal only fires
                        # on a strong EPS beat).
                        rev_actual=0, rev_estimate=0, raised_guidance=False,
                        session=session,
                    )
                if signal:
                    fired.append(signal)
            except Exception as e:
                logger.debug(f"earnings compound signal failed for {sym}: {e}")
    return fired


async def _fire_revision_compound_signals(symbols: list[str]) -> list[dict]:
    """
    For each symbol, pull recent analyst price-target / EPS revisions from FMP
    and fire the revision-cascade signal when 3+ revisions cleared the threshold.
    """
    from core.config import settings
    from agents.compound_signals import fire_revision_cascade
    from core.database import AsyncSessionLocal

    if not settings.FMP_API_KEY:
        return []

    import httpx
    fired: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for sym in symbols:
            try:
                resp = await client.get(
                    f"https://financialmodelingprep.com/api/v4/upgrades-downgrades",
                    params={"symbol": sym, "apikey": settings.FMP_API_KEY},
                )
                data = resp.json() if resp.status_code == 200 else []
                if not isinstance(data, list) or not data:
                    continue
                # Convert to the shape check_analyst_revision_cascade expects
                revisions = []
                for r in data[:20]:
                    if not isinstance(r, dict):
                        continue
                    revisions.append({
                        "analyst": r.get("analystName") or r.get("gradingCompany") or "",
                        "firm": r.get("gradingCompany") or "",
                        "old_eps": 0.0, "new_eps": 0.0,
                        "direction": "up" if "upgrade" in str(r.get("action", "")).lower() else "neutral",
                        "date": (r.get("publishedDate") or r.get("date") or "")[:10],
                    })
                async with AsyncSessionLocal() as session:
                    signal = await fire_revision_cascade(sym, revisions, session=session)
                if signal:
                    fired.append(signal)
            except Exception as e:
                logger.debug(f"revision compound signal failed for {sym}: {e}")
    return fired


async def get_catalyst_flags(symbol: str) -> dict:
    """
    Returns catalyst signals for a symbol (used in Stage 3 of the funnel).
    Checks Redis cache first, then DB.
    """
    import orjson
    cached = await cache_get(f"catalyst:{symbol}")
    if cached:
        return orjson.loads(cached)

    # Check DB for recent catalyst events
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT event_type, event_summary, signal_strength, detected_at
                FROM catalyst_events
                WHERE symbol = :sym AND detected_at > NOW() - INTERVAL '48 hours'
                  AND resolved = false
                ORDER BY signal_strength DESC
                LIMIT 3
            """), {"sym": symbol})
            rows = result.fetchall()

        if not rows:
            flags = {"score_delta": 0, "yt_mentions_this_week": 0}
        else:
            score_delta = sum(float(r[2] or 0) * 0.1 for r in rows)  # each strong event = +10 max
            flags = {
                "score_delta": min(score_delta, 15),
                "event_type": rows[0][0] if rows else None,
                "event_summary": rows[0][1] if rows else None,
                "signal_strength": float(rows[0][2] or 0) if rows else 0,
                "yt_mentions_this_week": 0,
            }
    except Exception:
        flags = {"score_delta": 0, "yt_mentions_this_week": 0}

    # Phase D.3: layer in pre-FOMC drift state (gated by SPX RV).
    try:
        from analysis.fomc_drift import apply_pre_fomc_overlay
        await apply_pre_fomc_overlay(flags)
    except Exception as e:
        logger.debug(f"pre-fomc overlay skipped: {e}")

    await cache_set(f"catalyst:{symbol}", orjson.dumps(flags).decode(), ttl=1800)
    return flags


async def _scan_unusual_options_volume(symbols: list[str]) -> list[dict]:
    """
    Checks Tradier for unusual call volume: today's vol > 150% of 20-day avg.
    Proxy: compare today's volume to OI ratio across strikes.
    """
    from data.tradier import get_tradier

    events = []
    tradier = get_tradier()

    batch_size = 10
    for i in range(0, min(len(symbols), 50), batch_size):
        batch = symbols[i : i + batch_size]
        tasks = [_check_symbol_flow(sym, tradier) for sym in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for sym, result in zip(batch, results):
            if not isinstance(result, Exception) and result:
                events.append(result)

    return events


async def _check_symbol_flow(symbol: str, tradier) -> dict | None:
    try:
        chain = await tradier.get_best_chain(symbol, min_dte=7, max_dte=30)
        if not chain:
            return None

        total_call_vol = sum(int(c.get("volume") or 0) for c in chain if c.get("option_type") == "C")
        total_call_oi  = sum(int(c.get("open_interest") or 0) for c in chain if c.get("option_type") == "C")

        if total_call_oi < 100:
            return None

        vol_oi_ratio = total_call_vol / total_call_oi if total_call_oi > 0 else 0

        # Unusual: vol > 150% of OI (fresh positioning, not just hedging)
        if vol_oi_ratio > 1.5:
            strength = min(vol_oi_ratio * 30, 100)
            return {
                "symbol": symbol,
                "event_type": "unusual_options",
                "event_summary": f"Call volume {round(vol_oi_ratio*100,0):.0f}% of OI — unusual institutional positioning",
                "signal_strength": strength,
                "detected_at": datetime.utcnow().isoformat(),
            }
    except Exception:
        pass
    return None


async def _scan_news_catalysts(symbols: list[str]) -> list[dict]:
    """Scan news for govt contracts, earnings surprises, SEC 8-K events."""
    from data.news import get_news_aggregator, get_ollama_filter

    agg = get_news_aggregator()
    filt = get_ollama_filter()

    try:
        raw_items = await agg.get_news_for_symbols(symbols[:30], hours_back=12)
        filtered = await filt.filter_and_tag(raw_items, symbols[:30])

        events = []
        for item in filtered:
            if item.get("urgency", 0) >= 4 and item.get("ticker"):
                events.append({
                    "symbol": item["ticker"],
                    "event_type": "news_catalyst",
                    "event_summary": item.get("headline", "")[:200],
                    "signal_strength": item.get("urgency", 3) * 20,
                    "detected_at": datetime.utcnow().isoformat(),
                })
        return events
    except Exception as e:
        logger.debug(f"News catalyst scan failed: {e}")
        return []


async def _persist_events(events: list[dict]):
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    if not events:
        return

    async with AsyncSessionLocal() as session:
        for e in events:
            try:
                await session.execute(text("""
                    INSERT INTO catalyst_events (symbol, event_type, event_summary, signal_strength, detected_at)
                    VALUES (:sym, :etype, :summary, :strength, NOW())
                    ON CONFLICT DO NOTHING
                """), {
                    "sym": e["symbol"],
                    "etype": e["event_type"],
                    "summary": e.get("event_summary", "")[:500],
                    "strength": e.get("signal_strength", 50),
                })
            except Exception:
                pass
        await session.commit()
