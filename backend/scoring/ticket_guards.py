"""
Ticket guards — last-mile sanity checks applied before a recommendation lands.

Catches simple but catastrophic mistakes the LLM/scoring layer may miss:
  - Earnings within DTE for options (could vaporize the premium)
  - Same-symbol duplicate within 24h window (avoid stacking)
  - Cross-stream conflict (options bull + LT bear on same name)
  - Symbol already has an open position (don't pyramid uncontrolled)

Used by `agents/graph.py::_build_order_ticket` (options) and by the briefing
job for swing/LT streams.

Each guard returns:
  {"name": str, "severity": "info|warning|critical", "message": str}

Critical = block the ticket. Warning = surface to LLM and UI. Info = log only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable


@dataclass
class GuardFlag:
    name: str
    severity: str   # 'info' | 'warning' | 'critical'
    message: str

    def to_dict(self) -> dict:
        return {"name": self.name, "severity": self.severity, "message": self.message}


# ---------------------------------------------------------------------------
# Earnings-in-DTE
# ---------------------------------------------------------------------------

async def check_earnings_in_dte(symbol: str, dte: int) -> GuardFlag | None:
    """Critical if earnings falls within DTE; warning if within 1.5x DTE."""
    if dte <= 0:
        return None
    earnings_date = await _next_earnings_date(symbol)
    if earnings_date is None:
        return None
    days_until = (earnings_date - date.today()).days
    if days_until < 0:
        return None
    if days_until <= dte:
        return GuardFlag(
            name="earnings_in_dte",
            severity="critical",
            message=(f"{symbol} reports earnings on {earnings_date} "
                     f"({days_until}d), inside the {dte}-DTE window. "
                     "Option price will face IV crush + binary move risk."),
        )
    if days_until <= int(dte * 1.5):
        return GuardFlag(
            name="earnings_near_dte",
            severity="warning",
            message=(f"{symbol} reports earnings on {earnings_date} "
                     f"({days_until}d), just past the {dte}-DTE window. "
                     "Pre-earnings IV expansion may affect the position."),
        )
    return None


async def _next_earnings_date(symbol: str) -> date | None:
    try:
        from analysis.calendar import _get_earnings_date
        return await _get_earnings_date(symbol, date.today())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Same-symbol duplicate within window
# ---------------------------------------------------------------------------

async def check_recent_duplicate(
    symbol: str,
    direction: str,
    window_hours: int = 24,
    *,
    session=None,
) -> GuardFlag | None:
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await check_recent_duplicate(symbol, direction, window_hours, session=s)
    from sqlalchemy import text
    try:
        result = await session.execute(text("""
            SELECT id, recommended_at, stream, direction, status
            FROM recommendations
            WHERE symbol = :sym
              AND direction = :dir
              AND status IN ('open', 'paper_filled', 'live_filled')
              AND recommended_at >= NOW() - make_interval(hours => :h)
            ORDER BY recommended_at DESC LIMIT 1
        """), {"sym": symbol, "dir": direction, "h": window_hours})
        row = result.fetchone()
        if row is None:
            return None
        return GuardFlag(
            name="recent_duplicate",
            severity="warning",
            message=(f"{symbol} {direction} already recommended within "
                     f"{window_hours}h (rec id={row[0]}, stream={row[2]}). "
                     "Skipping likely the right call — stacking same setup "
                     "multiplies risk without independent edge."),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cross-stream conflict
# ---------------------------------------------------------------------------

async def check_cross_stream_conflict(
    symbol: str,
    this_direction: str,
    this_stream: str,
    *,
    session=None,
) -> GuardFlag | None:
    """Warning when another stream has the opposite open direction."""
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await check_cross_stream_conflict(
                symbol, this_direction, this_stream, session=s,
            )
    from sqlalchemy import text
    opposite = {"bullish": "bearish", "bearish": "bullish"}.get(this_direction)
    if not opposite:
        return None
    try:
        result = await session.execute(text("""
            SELECT id, stream, direction, recommended_at
            FROM recommendations
            WHERE symbol = :sym
              AND direction = :opp
              AND stream <> :this
              AND status IN ('open', 'paper_filled', 'live_filled')
              AND recommended_at >= NOW() - INTERVAL '14 days'
            ORDER BY recommended_at DESC LIMIT 1
        """), {"sym": symbol, "opp": opposite, "this": this_stream})
        row = result.fetchone()
        if row is None:
            return None
        return GuardFlag(
            name="cross_stream_conflict",
            severity="warning",
            message=(f"{symbol}: {this_stream} stream says {this_direction}, "
                     f"but {row[1]} stream has open {opposite} position "
                     f"(rec id={row[0]}). One of these views is wrong. "
                     "Reconcile before placing both."),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Already-open position on same symbol
# ---------------------------------------------------------------------------

async def check_existing_position(symbol: str, *, session=None) -> GuardFlag | None:
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await check_existing_position(symbol, session=s)
    from sqlalchemy import text
    try:
        result = await session.execute(text("""
            SELECT id, strategy, direction, expiry FROM paper_trades
            WHERE symbol = :sym AND status = 'open'
            ORDER BY opened_at DESC LIMIT 1
        """), {"sym": symbol})
        row = result.fetchone()
        if row is None:
            return None
        return GuardFlag(
            name="existing_position",
            severity="warning",
            message=(f"{symbol}: already have an open {row[1]} {row[2]} "
                     f"(expiry={row[3]}) — pyramiding without explicit intent "
                     "is rarely the right call."),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_all_guards(
    symbol: str,
    direction: str,
    stream: str,
    dte: int | None = None,
) -> list[GuardFlag]:
    """All guards in parallel. Returns the list of flags (empty = clean)."""
    import asyncio
    tasks = [
        check_recent_duplicate(symbol, direction),
        check_cross_stream_conflict(symbol, direction, stream),
        check_existing_position(symbol),
    ]
    if dte and dte > 0:
        tasks.append(check_earnings_in_dte(symbol, dte))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[GuardFlag] = []
    for r in results:
        if isinstance(r, GuardFlag):
            out.append(r)
    return out


def block_on_critical(flags: Iterable[GuardFlag]) -> tuple[bool, list[GuardFlag]]:
    """Returns (should_block, list_of_critical_flags)."""
    critical = [f for f in flags if f.severity == "critical"]
    return (len(critical) > 0, critical)
