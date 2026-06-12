"""Category 2: Seasonality & Calendar (7%)"""

from __future__ import annotations

from datetime import date, timedelta
from calendar import monthcalendar

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

# Day of week return bias (0=Mon, 4=Fri)
DOW_BIAS = {0: -0.1, 1: 0.2, 2: 0.1, 3: 0.1, 4: 0.0}

# FOMC meeting dates 2026 (manually maintained; update annually)
# Source: Federal Reserve (free, public)
FOMC_DATES_2026 = [
    date(2026, 1, 28), date(2026, 1, 29),
    date(2026, 3, 18), date(2026, 3, 19),
    date(2026, 5, 6),  date(2026, 5, 7),
    date(2026, 6, 17), date(2026, 6, 18),
    date(2026, 7, 28), date(2026, 7, 29),
    date(2026, 9, 15), date(2026, 9, 16),
    date(2026, 10, 27), date(2026, 10, 28),
    date(2026, 12, 15), date(2026, 12, 16),
]

# CPI release schedule 2026 (BLS.gov, free)
CPI_DATES_2026 = [
    date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 11),
    date(2026, 4, 10), date(2026, 5, 13), date(2026, 6, 10),
    date(2026, 7, 15), date(2026, 8, 12), date(2026, 9, 11),
    date(2026, 10, 14), date(2026, 11, 12), date(2026, 12, 11),
]

# Combine all macro event dates
ALL_MACRO_EVENTS: list[tuple[date, str]] = (
    [(d, "FOMC") for d in FOMC_DATES_2026] +
    [(d, "CPI") for d in CPI_DATES_2026]
)


# ---------------------------------------------------------------------------
# Event detection helpers
# ---------------------------------------------------------------------------

def _days_to_next_event(event_dates: list[date], today: date) -> int | None:
    upcoming = sorted(d for d in event_dates if d >= today)
    if upcoming:
        return (upcoming[0] - today).days
    return None


def _find_upcoming_events(today: date, lookahead_days: int = 21) -> list[dict]:
    """Find all macro events within the next `lookahead_days`."""
    window_end = today + timedelta(days=lookahead_days)
    events = []
    for event_date, event_type in ALL_MACRO_EVENTS:
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
    dow_bias = DOW_BIAS.get(dow, 0)

    signals.append({"name": "month_seasonality", "month": month, "bias": month_bias})
    signals.append({"name": "day_of_week", "dow": dow, "bias": dow_bias})

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
    upcoming_events = _find_upcoming_events(today, lookahead_days=21)
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

    summary_parts = [f"Month bias={month_bias}, DOW bias={dow_bias}"]
    if earnings_date:
        days_to_e = (earnings_date - today).days
        summary_parts.append(f"Earnings in {days_to_e}d")
    if upcoming_events:
        e = upcoming_events[0]
        summary_parts.append(f"{e['type']} in {e['days_away']}d")

    weight = 7.0
    return CategoryScore("calendar", weight, score, weight * score / 10, direction, signals,
                        " | ".join(summary_parts))
