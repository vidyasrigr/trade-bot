"""
Daily 3-stream briefing — Phase F.3.

Endpoint:    GET /api/briefing/daily
Discord hook: build_and_send_briefing() runs at 8:00 AM ET Mon-Fri.

Streams:
  - options:  top 5 from latest scanner results
  - swing:    top 5 by combined 21d ranker score + momentum_12_1 percentile
  - long_term: top 5 LEAPS / long candidates from analysis/lt_scoring.py

Output schema kept deliberately simple — the UI just renders the list per stream.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import httpx
import orjson
from loguru import logger

from core.config import settings
from core.redis_client import cache_get


async def _options_stream() -> list[dict]:
    cached = await cache_get("scan:latest")
    if not cached:
        return []
    items = orjson.loads(cached)
    out = []
    for r in items[:5]:
        out.append({
            "symbol": r.get("symbol"),
            "conviction_score": r.get("conviction_score"),
            "direction": r.get("direction"),
            "vol_regime": r.get("vol_regime"),
            "thesis": (r.get("trade_thesis") or "")[:240],
            "ticket": r.get("order_ticket"),
            "stream": "options",
        })
    return out


async def _swing_stream() -> list[dict]:
    """
    Top symbols by composite swing signal:
      0.6 * latest ranker_score (h=21) + 0.4 * momentum_12_1 percentile.
    Pulled from signal_ranks (Phase C) + per-symbol scanner cache.
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT symbol, percentile
                FROM signal_ranks
                WHERE signal_type = 'momentum_12_1'
                  AND as_of_date = (SELECT MAX(as_of_date) FROM signal_ranks
                                     WHERE signal_type = 'momentum_12_1')
                ORDER BY percentile DESC
                LIMIT 25
            """))
            momentum_top = [(r[0], float(r[1])) for r in result.fetchall()]
    except Exception as e:
        logger.debug(f"swing stream: signal_ranks unavailable: {e}")
        return []

    # Try to add ranker_score if available
    try:
        from scoring.ranker import score_symbols
        from store.feature_store import get_feature_store
        store = get_feature_store()
        latest = store.latest_snapshot()
        if latest:
            latest_d, _ = latest
            panel = store.read_panel(
                features=[
                    "total_score", "ret_20d", "vol_ratio", "price_pct_52range",
                    "cat_iv_analysis", "cat_momentum", "cat_trend", "cat_options_flow",
                ],
                start=latest_d, end=latest_d,
            )
            rows = {r["symbol"]: r.drop(["as_of_date", "symbol"]).to_dict()
                    for _, r in panel.iterrows()}
            preds = score_symbols(rows, horizon=21)
        else:
            preds = {}
    except Exception as e:
        logger.debug(f"swing stream: ranker unavailable: {e}")
        preds = {}

    composite: list[tuple[str, float]] = []
    for sym, mom_pct in momentum_top:
        ranker = float(preds.get(sym, 0.0))
        score = 0.4 * mom_pct + 0.6 * ranker
        composite.append((sym, score))
    composite.sort(key=lambda x: x[1], reverse=True)
    return [
        {"symbol": s, "composite_score": round(c, 4), "stream": "swing"}
        for s, c in composite[:5]
    ]


async def _long_term_stream() -> list[dict]:
    """Top-5 LT candidates from analysis_results enriched with lt_scoring tier."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT symbol, total_score, trade_thesis, analyzed_at
                FROM analysis_results
                WHERE analyzed_at > NOW() - INTERVAL '7 days'
                ORDER BY total_score DESC
                LIMIT 25
            """))
            candidates = [dict(r) for r in result.mappings().all()]
    except Exception:
        candidates = []

    out = []
    for c in candidates:
        try:
            from analysis.lt_scoring import score_stock
            lt = await score_stock(symbol=c["symbol"])
            if lt.tier in ("long", "leaps_candidate"):
                out.append({
                    "symbol": c["symbol"],
                    "lt_score": float(lt.total_score),
                    "tier": lt.tier,
                    "thesis": (c.get("trade_thesis") or "")[:240],
                    "stream": "long_term",
                })
        except Exception:
            continue
        if len(out) >= 5:
            break
    return out


async def build_briefing() -> dict:
    options, swing, long_term = await asyncio.gather(
        _options_stream(), _swing_stream(), _long_term_stream(),
        return_exceptions=True,
    )
    if isinstance(options, Exception):
        options = []
    if isinstance(swing, Exception):
        swing = []
    if isinstance(long_term, Exception):
        long_term = []
    return {
        "date": date.today().isoformat(),
        "generated_at": datetime.utcnow().isoformat(),
        "options": options,
        "swing": swing,
        "long_term": long_term,
    }


async def send_to_discord(briefing: dict) -> None:
    if not settings.DISCORD_WEBHOOK_URL:
        return
    embed_fields = []
    for stream, label in (("options", "📈 Options"), ("swing", "🚀 Swing"),
                           ("long_term", "💎 Long-Term")):
        items = briefing.get(stream, [])
        if not items:
            embed_fields.append({"name": label, "value": "—", "inline": False})
            continue
        lines = []
        for it in items:
            tail = ""
            if "conviction_score" in it:
                tail = f" ({it['conviction_score']}/100 {it.get('direction', '?')})"
            elif "composite_score" in it:
                tail = f" ({it['composite_score']:+.2f})"
            elif "lt_score" in it:
                tail = f" ({it['lt_score']}/100 {it.get('tier', '')})"
            lines.append(f"• **{it['symbol']}**{tail}")
        embed_fields.append({"name": label, "value": "\n".join(lines), "inline": False})

    payload = {
        "embeds": [{
            "title": f"Daily Briefing — {briefing['date']}",
            "description": "Top setups across all 3 streams",
            "color": 0x3399FF,
            "fields": embed_fields,
        }]
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
        logger.info("Daily briefing sent to Discord")
    except Exception as e:
        logger.warning(f"Daily briefing Discord send failed: {e}")


async def build_and_send_briefing() -> dict:
    briefing = await build_briefing()
    await send_to_discord(briefing)
    return briefing
