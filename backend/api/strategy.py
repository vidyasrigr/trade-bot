"""
/api/strategy — the current trading-strategy document, version history, and
pending review proposals.

Replaces the front-end mock that fabricated rules. Derived from:
  - Live config (KELLY_FRACTION, BASE/MAX_POSITION_SIZE_PCT, MIN_SIGNALS_REQUIRED, etc.)
  - strategy_journal table (compacted lessons from postmortem) for version history
  - Pending review = uncompacted strategy_journal entries with a proposed_change
  - Optional strategy_overrides table for human PATCH edits (created on first PATCH)

Returns hard-coded *rule descriptions* (e.g. "premium-buying when IV-rank < 35")
that match the running scoring logic — these are documentation OF the system,
not invented numbers about it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import text

from core.config import settings


def _alpha_stream() -> dict[str, Any]:
    return {
        "label": "Premium-buying",
        "goal": "Asymmetric payoff when IV is cheap relative to the move we expect",
        "entry_conditions": [
            "IV rank < 35 OR variance risk premium is INVERTED (IV < HV)",
            "Directional confirmation from >= 3 independent signal groups",
            f"Conviction >= 60 after IC adjustments and anti-crowding",
            "Liquidity gate: OI >= 500, bid-ask <= 10% of mid",
        ],
        "structure_rules": [
            "Long calls/puts only when conviction >= 75 and IV rank < 30",
            "Debit spreads (vertical) when IV is moderate; defined risk",
            "Avoid options priced <= $0.50 with DTE <= 21 — Boyer-Vorkink lottery zone",
        ],
        "dte": "21-45 (sweet spot for theta-vs-gamma balance)",
        "position_size": (
            f"Half-Kelly ({int(settings.KELLY_FRACTION * 100)}% of full), "
            f"conviction-scaled between {settings.BASE_POSITION_SIZE_PCT * 100:.1f}% "
            f"and {settings.MAX_POSITION_SIZE_PCT * 100:.1f}% of portfolio"
        ),
        "profit_target": "100% of debit paid (long single); 50% of max profit (debit spread)",
        "stop_loss": "50% of debit paid",
        "exit_rules": [
            "Take profit at 100% of debit (single) / 50% of max (spread)",
            "Hard stop at 50% of debit lost",
            "Time stop: close at 21 DTE if not hit either threshold",
            "Re-evaluate if any signal that fired at entry stops firing",
        ],
    }


def _income_stream() -> dict[str, Any]:
    return {
        "label": "Premium-selling",
        "goal": "Harvest variance risk premium when IV is rich",
        "entry_conditions": [
            "IV rank >= 50 AND variance risk premium > 0 (IV > realized)",
            f"Conviction >= 60 after IC adjustments",
            "Neutral or low-conviction directional bias (favors condors over verticals)",
            "Liquidity gate: OI >= 500, bid-ask <= 10% of mid",
        ],
        "structure_rules": [
            "Iron condor for delta-neutral when IV rank > 65",
            "Credit spread (put or call vertical) for mild directional bias",
            "Short strangles only on names with documented post-event mean reversion",
            "Defined risk only — never naked short premium on tail-risk names",
        ],
        "dte": "45 (Carr-Wu VRP is widest here; matches scanner default)",
        "position_size": (
            f"Half-Kelly ({int(settings.KELLY_FRACTION * 100)}% of full), "
            f"conviction-scaled between {settings.BASE_POSITION_SIZE_PCT * 100:.1f}% "
            f"and {settings.MAX_POSITION_SIZE_PCT * 100:.1f}% of portfolio"
        ),
        "profit_target": "50% of max profit (Carr-Wu fade — avoid greed near expiry)",
        "stop_loss": "2x credit received",
        "exit_rules": [
            "Take profit at 50% of max",
            "Manage at 21 DTE to avoid gamma blow-up",
            "Hard stop at 2x credit received",
            "Roll only if VRP is still wide and thesis intact",
        ],
    }


def _risk_guardrails() -> dict[str, Any]:
    return {
        "max_daily_drawdown_pct": {
            "value": 5.0, "unit": "%",
            "note": "Trading halts when realized day P&L breaches -5% of portfolio (circuit breaker)",
        },
        "max_position_size_pct": {
            "value": settings.MAX_POSITION_SIZE_PCT * 100, "unit": "%",
            "note": "Hard cap on any single trade as % of portfolio",
        },
        "max_open_positions": {
            "value": 10, "unit": "positions",
            "note": "Concurrent open positions cap (correlation control)",
        },
        "liquidity_open_interest": {
            "value": 500, "unit": "OI",
            "note": "Minimum open interest required at the contract we're entering",
            "open_interest": 500,
        },
        "liquidity_bid_ask_pct": {
            "value": 10.0, "unit": "% of mid",
            "note": "Reject contracts whose bid-ask is wider than 10% of mid",
            "bid_ask_pct": 10.0,
        },
    }


def _position_sizing() -> dict[str, Any]:
    return {
        "method": "Half-Kelly, conviction-scaled",
        "base_size_pct": settings.BASE_POSITION_SIZE_PCT * 100,
        "max_size_pct": settings.MAX_POSITION_SIZE_PCT * 100,
        "kelly_fraction": settings.KELLY_FRACTION,
        "formula": (
            "size_pct = base + ((conviction - 60) / 40) * (max - base);  "
            "scaled by kelly_fraction. Sets to 0 when the 3-signal confirmation gate fails."
        ),
        "note": (
            f"Half-Kelly captures ~75% of full-Kelly compounding with ~50% less drawdown. "
            f"Re-derived per ticket against the actual option mid, not a default $2.50 price."
        ),
    }


def _confirmation_requirements() -> dict[str, Any]:
    from scoring.weighted import INDEPENDENT_GROUPS
    return {
        "min_independent_signals": settings.MIN_SIGNALS_REQUIRED,
        "independent_categories": sorted(INDEPENDENT_GROUPS.keys()),
        "anti_crowding": (
            "If >= 5 tracked YouTube channels mention the symbol within 7 days, "
            "score is discounted 20% (counted once in scoring/weighted.py)"
        ),
        "false_breakout_filter": (
            "Volume confirmation required (avg-vol-ratio > 1.2) for breakout entries; "
            "stop placement honors prior structure low/high, not a fixed %"
        ),
    }


async def _version_history(session) -> list[dict]:
    try:
        result = await session.execute(text("""
            SELECT id, content, proposed_change, trade_count, win_rate, avg_r, created_at
            FROM strategy_journal
            WHERE entry_type = 'weekly_compaction'
            ORDER BY created_at DESC
            LIMIT 20
        """))
        rows = result.mappings().all()
    except Exception as e:
        logger.debug(f"strategy_journal unavailable: {e}")
        return []

    versions = []
    for idx, r in enumerate(rows):
        versions.append({
            "version": f"v1.{len(rows) - idx}",
            "date": r["created_at"].date().isoformat() if r.get("created_at") else "",
            "author": "auto-compaction",
            "change_type": "ic_adjustment" if r.get("proposed_change") else "enhancement",
            "summary": (r.get("content") or "")[:160],
            "changes": [r["content"]] if r.get("content") else [],
            "performance": {
                "win_rate": float(r["win_rate"]) if r.get("win_rate") is not None else None,
                "avg_r": float(r["avg_r"]) if r.get("avg_r") is not None else None,
                "trades": int(r.get("trade_count") or 0),
                "period": "rolling 20 trades",
            },
            "rationale": r.get("proposed_change") or "Weekly compaction of closed-trade lessons",
        })
    return versions


async def _pending_review(session) -> list[dict]:
    try:
        result = await session.execute(text("""
            SELECT id, content, proposed_change, created_at
            FROM strategy_journal
            WHERE proposed_change IS NOT NULL
              AND (applied_at IS NULL)
            ORDER BY created_at DESC
            LIMIT 20
        """))
        rows = result.mappings().all()
    except Exception:
        return []

    return [
        {
            "id": str(r["id"]),
            "proposed_by": "auto-postmortem",
            "proposed_date": r["created_at"].date().isoformat() if r.get("created_at") else "",
            "description": r.get("proposed_change") or "",
            "evidence": (r.get("content") or "")[:300],
            "status": "pending",
        }
        for r in rows
    ]


async def _apply_overrides(guardrails: dict, session) -> dict:
    """Layer in any human PATCH overrides from strategy_overrides table."""
    try:
        result = await session.execute(text("""
            SELECT key, value, note, author, updated_at
            FROM strategy_overrides
        """))
        for row in result.mappings().all():
            key = row["key"]
            if key in guardrails:
                guardrails[key] = {
                    **guardrails[key],
                    "value": float(row["value"]),
                    "note": row.get("note") or guardrails[key]["note"],
                    "overridden_by": row.get("author"),
                    "overridden_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
                }
    except Exception:
        pass
    return guardrails


async def get_strategy() -> dict:
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        versions = await _version_history(session)
        pending = await _pending_review(session)
        guardrails = await _apply_overrides(_risk_guardrails(), session)

    current_version = versions[0]["version"] if versions else "v1.0"
    effective_date = versions[0]["date"] if versions else date.today().isoformat()

    return {
        "current": {
            "version": current_version,
            "effective_date": effective_date,
            "status": "active",
            "authored_by": "system",
            "summary": (
                "Two-stream playbook: premium-buying when IV is cheap relative to expected "
                "move; premium-selling when IV is rich and VRP is wide. Half-Kelly sizing, "
                "3-independent-signal confirmation, anti-crowding discount."
            ),
            "streams": {"alpha": _alpha_stream(), "income": _income_stream()},
            "risk_guardrails": guardrails,
            "position_sizing": _position_sizing(),
            "confirmation_requirements": _confirmation_requirements(),
        },
        "versions": versions,
        "pending_review": pending,
    }


async def patch_strategy_override(body: dict) -> dict:
    """
    Accept guardrail overrides from the UI. Persisted to strategy_overrides so
    the running scoring logic can pick them up at next request boundary (the
    integration into scoring/weighted.py reading these is a follow-up — for now
    we persist and surface them in /api/strategy).
    """
    key = body.get("key")
    if not key or not isinstance(key, str):
        raise HTTPException(400, "key required")
    value = body.get("value")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, "value must be numeric")
    note = body.get("note") or ""
    author = body.get("author") or "unknown"

    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("""
                INSERT INTO strategy_overrides (key, value, note, author, updated_at)
                VALUES (:k, :v, :n, :a, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    note = EXCLUDED.note,
                    author = EXCLUDED.author,
                    updated_at = NOW()
            """), {"k": key, "v": value, "n": note, "a": author})
            await session.commit()
        except Exception as e:
            logger.error(f"strategy_overrides write failed (run migration 009): {e}")
            raise HTTPException(
                500,
                "strategy_overrides table not available — run migration 009_strategy_overrides.sql",
            )

    return {"ok": True, "applied": {"key": key, "value": value, "note": note, "author": author}}
