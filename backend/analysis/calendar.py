"""Category 2: Seasonality & Calendar (7%)"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from calendar import monthcalendar

import feedparser
import httpx
import pandas as pd
from loguru import logger
from analysis.engine import CategoryScore
from core.redis_client import cache_get, cache_set


# Monthly seasonality bias (S&P500 historical averages)
MONTHLY_BIAS = {
    1: 0.5, 2: 0.3, 3: 0.2, 4: 1.0, 5: -0.2,  # Sell in May
    6: -0.1, 7: 0.8, 8: -0.3, 9: -1.0, 10: 0.5,  # October vol
    11: 1.2, 12: 1.0,  # Santa rally
}

# Per-name DoW seasonality is computed in scoring/cross_section.py (Phase C) with
# significance gating; the global S&P 500 DoW averages used to live here as a
# proxy for every stock, which Fable correctly called out as overfitting noise.

# FOMC + CPI dates are fetched DYNAMICALLY (2026-06-14, Phase A).
# Previously hardcoded for 2026 only — would silently stop working on 2027-01-01.
# Sources: federalreserve.gov FOMC RSS + manual seed for CPI (BLS calendar is JSON).

FOMC_RSS_URL = "https://www.federalreserve.gov/feeds/fomc.xml"
_FOMC_CACHE_KEY = "calendar:fomc_dates_v2"
_FOMC_CACHE_TTL = 86400 * 7  # 7 days — Fed announces a year in advance

# CPI release schedule. BLS publishes one calendar per year and shifts only by
# 1-2 days year-over-year; ship the current rolling window and update yearly.
# This list is intentionally small + extends one year forward each January.
_CPI_FALLBACK_DATES = [
    date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 11),
    date(2026, 4, 10), date(2026, 5, 13), date(2026, 6, 10),
    date(2026, 7, 15), date(2026, 8, 12), date(2026, 9, 11),
    date(2026, 10, 14), date(2026, 11, 12), date(2026, 12, 11),
    date(2027, 1, 13), date(2027, 2, 11), date(2027, 3, 11),
]


async def get_fomc_dates() -> list[date]:
    """
    Pull upcoming FOMC meeting dates from the Federal Reserve FOMC RSS feed.
    Caches the parsed result in Redis for 7 days. Falls back to an empty list
    on parse failure — calendar.py downgrades to month-bias only in that case.
    """
    cached = await cache_get(_FOMC_CACHE_KEY)
    if cached:
        import orjson
        return [date.fromisoformat(s) for s in orjson.loads(cached)]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                FOMC_RSS_URL,
                headers={"User-Agent": "TradingResearch fomc-calendar (vidyasrigr@gmail.com)"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.warning(f"FOMC RSS fetch failed, calendar overlays disabled until next attempt: {e}")
        return []

    # FOMC items have titles like "FOMC Statement" / "Minutes of the Federal
    # Open Market Committee, March 19-20, 2026" or summaries with explicit dates.
    # Parse any "Month DD, YYYY" or "Month DD-DD, YYYY" we can find.
    pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+"
        r"(\d{1,2})(?:[-–]\d{1,2})?,\s+(\d{4})"
    )
    dates: set[date] = set()
    for entry in feed.entries[:60]:
        haystack = " ".join(filter(None, [entry.get("title", ""), entry.get("summary", "")]))
        for m in pattern.finditer(haystack):
            try:
                month_name, day_str, year_str = m.groups()
                parsed = datetime.strptime(f"{month_name} {day_str} {year_str}", "%B %d %Y").date()
                # Only retain dates from this year forward — older entries are minutes
                if parsed >= date.today().replace(month=1, day=1):
                    dates.add(parsed)
            except ValueError:
                continue

    result = sorted(dates)
    if result:
        import orjson
        await cache_set(_FOMC_CACHE_KEY, orjson.dumps([d.isoformat() for d in result]).decode(),
                         ttl=_FOMC_CACHE_TTL)
    return result


async def _all_macro_events() -> list[tuple[date, str]]:
    """FOMC (dynamic) + CPI (fallback list) combined."""
    fomc = await get_fomc_dates()
    return [(d, "FOMC") for d in fomc] + [(d, "CPI") for d in _CPI_FALLBACK_DATES]


# ---------------------------------------------------------------------------
# Event detection helpers
# ---------------------------------------------------------------------------

def _days_to_next_event(event_dates: list[date], today: date) -> int | None:
    upcoming = sorted(d for d in event_dates if d >= today)
    if upcoming:
        return (upcoming[0] - today).days
    return None


async def _find_upcoming_events(today: date, lookahead_days: int = 21) -> list[dict]:
    """Find all macro events within the next `lookahead_days`."""
    window_end = today + timedelta(days=lookahead_days)
    events = []
    for event_date, event_type in await _all_macro_events():
        if today <= event_date <= window_end:
            events.append({
                "type": event_type,
                "date": event_date.isoformat(),
                "days_away": (event_date - today).days,
            })
    return sorted(events, key=lambda e: e["days_away"])


async def _get_earnings_date(symbol: str, today: date) -> date | None:
    """Get the next earnings date for a symbol from FMP (cached 24h)."""
    cache_key = f"earnings_date:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        d = orjson.loads(cached)
        if d:
            return date.fromisoformat(d)
        return None

    from core.config import settings
    if not settings.FMP_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/earning_calendar",
                params={
                    "from": today.isoformat(),
                    "to": (today + timedelta(days=60)).isoformat(),
                    "apikey": settings.FMP_API_KEY,
                },
            )
            data = resp.json()

        if not isinstance(data, list):
            return None

        matching = [e for e in data if e.get("symbol") == symbol]
        if not matching:
            import orjson
            await cache_set(cache_key, orjson.dumps(None).decode(), ttl=86400)
            return None

        nearest = min(matching, key=lambda e: e.get("date", "9999-01-01"))
        earns_date = date.fromisoformat(nearest["date"])

        import orjson
        await cache_set(cache_key, orjson.dumps(earns_date.isoformat()).decode(), ttl=86400)
        return earns_date

    except Exception as e:
        logger.debug(f"Earnings date lookup failed for {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"
    today = date.today()

    month = today.month
    dow = today.weekday()

    month_bias = MONTHLY_BIAS.get(month, 0)
    _ = dow  # reserved for per-name DoW signal in Phase C; no global bias applied

    signals.append({"name": "month_seasonality", "month": month, "bias": month_bias})

    if month_bias > 0.5:
        score += 1
        direction = "bullish"
        signals.append({"name": "favorable_month", "direction": "bullish"})
    elif month_bias < -0.5:
        score -= 1
        direction = "bearish"
        signals.append({"name": "unfavorable_month", "direction": "bearish"})

    # Options expiration week (3rd Friday of month) — Vanna/Charm flows
    cal = monthcalendar(today.year, today.month)
    third_friday = None
    fridays = [week[4] for week in cal if week[4] != 0]
    if len(fridays) >= 3:
        third_friday = fridays[2]
    if third_friday:
        days_to_opex = third_friday - today.day
        if 0 <= days_to_opex <= 5:
            signals.append({"name": "opex_week", "days_to_opex": days_to_opex,
                             "note": "Options expiration — Vanna/Charm flows active"})
            score -= 0.5

    # Q earnings season check (Jan, Apr, Jul, Oct)
    if month in (1, 4, 7, 10):
        signals.append({"name": "earnings_season", "note": "Q earnings season in progress"})
        score += 0.5

    # ── Earnings proximity (FMP) ───────────────────────────────────────────
    earnings_date = await _get_earnings_date(symbol, today)
    if earnings_date:
        days_to_earnings = (earnings_date - today).days
        signals.append({"name": "earnings_date", "date": earnings_date.isoformat(),
                         "days_away": days_to_earnings})

        if days_to_earnings <= 0:
            # Earnings today or just passed
            signals.append({"name": "earnings_imminent", "direction": "event_risk",
                             "note": "Earnings today — IV crush likely"})
            score -= 1.5  # IV crush risk
        elif days_to_earnings <= 5:
            signals.append({"name": "earnings_risk", "direction": "event_risk",
                             "note": f"Earnings in {days_to_earnings}d — avoid new entries"})
            score -= 1.0
        elif 14 <= days_to_earnings <= 30:
            # Sweet spot: IV expansion window approaching
            signals.append({"name": "earnings_iv_expansion", "direction": "iv_expanding",
                             "note": f"Earnings in {days_to_earnings}d — IV expansion window: buy vol now if IVR <30"})
            score += 0.5

    # ── FOMC and macro events ──────────────────────────────────────────────
    upcoming_events = await _find_upcoming_events(today, lookahead_days=21)
    for event in upcoming_events:
        days = event["days_away"]
        etype = event["type"]

        signals.append({
            "name": f"{etype.lower()}_upcoming",
            "date": event["date"],
            "days_away": days,
            "note": f"{etype} release in {days} days",
        })

        if days <= 2:
            # Event day / day before: IV at peak, good to sell premium if IVR >60
            score -= 0.5
            signals.append({"name": f"{etype.lower()}_imminent", "direction": "event_risk",
                             "note": f"{etype} in {days}d — elevated vol, good to sell if IVR rich"})
        elif 7 <= days <= 21:
            # 1-3 weeks out: pre-event IV expansion trade window
            signals.append({"name": f"{etype.lower()}_expansion_window", "direction": "iv_expanding",
                             "note": f"{etype} in {days}d — buy vol if IVR <30 (ride expansion, exit before event)"})

    if upcoming_events:
        nearest = upcoming_events[0]
        nearest_days = nearest["days_away"]
        # If any high-impact event within 7 days, reduce score (uncertainty)
        if nearest_days <= 7:
            score -= 0.5

    score = max(0.0, min(10.0, score))

    summary_parts = [f"Month bias={month_bias}"]
    if earnings_date:
        days_to_e = (earnings_date - today).days
        summary_parts.append(f"Earnings in {days_to_e}d")
    if upcoming_events:
        e = upcoming_events[0]
        summary_parts.append(f"{e['type']} in {e['days_away']}d")

    weight = 7.0
    return CategoryScore("calendar", weight, score, weight * score / 10, direction, signals,
                        " | ".join(summary_parts))
