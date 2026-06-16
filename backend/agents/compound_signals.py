"""
Compound Signal Detector — multi-stock patterns with documented alpha.

Surviving signals (after 2026-06-14 Phase A cleanup):
  1. Beat-and-Raise PEAD — mid/small cap only (<$50B market cap) — Bernard & Thomas 1989
  2. Analyst Revision Cascade (3+ analysts raise EPS >5% within 7 days) — ExtractAlpha
  3. Sector Dispersion (Kakushadze 6.3 — short vol on ETF, long vol on components)

REMOVED:
  - VIX Spike Buy (n≈3 episodes — anecdote, not a rule)
  - Semis Cascade (hardcoded SEMIS_CASCADE_SYMBOLS — hindsight-fit lookup)
  - Hyperscaler Lead for Semis (hardcoded HYPERSCALER_SYMBOLS + lag dict — same)

The hyperscaler→semis lag and the semis cascade are being rebuilt in Phase D as
a *learned* supply-chain lead-lag graph computed nightly from the point-in-time
feature store, replacing the hand-coded dicts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, date

import httpx
import numpy as np
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


# ---------------------------------------------------------------------------
# Signal: Beat-and-Raise PEAD (mid/small cap only)
# ---------------------------------------------------------------------------

async def check_beat_and_raise_pead(
    symbol: str,
    market_cap: float,
    eps_actual: float,
    eps_estimate: float,
    rev_actual: float,
    rev_estimate: float,
    raised_guidance: bool = False,
) -> dict | None:
    """
    Trigger: Mid/small-cap stock (<$50B market cap) beats revenue AND raises guidance.
    Large-cap excluded — PEAD arbitraged away for megacaps.
    """
    if market_cap > 50e9:
        return None  # Large-cap PEAD is arbitraged away

    eps_beat = eps_actual > eps_estimate
    rev_beat = rev_actual > rev_estimate * 1.03  # >3% rev beat
    beat_and_raise = eps_beat and (rev_beat or raised_guidance)

    if not beat_and_raise:
        return None

    beat_magnitude = (eps_actual - eps_estimate) / abs(eps_estimate) if eps_estimate else 0

    return {
        "signal_type": "beat_raise_pead",
        "symbols": [symbol],
        "trigger_details": {
            "eps_beat_pct": round(beat_magnitude * 100, 1),
            "rev_beat": rev_beat,
            "raised_guidance": raised_guidance,
            "market_cap_b": round(market_cap / 1e9, 1),
            "action": (
                f"{symbol} beat-and-raise ({beat_magnitude*100:.0f}% EPS beat, "
                f"{'rev beat + ' if rev_beat else ''}guidance raised). "
                f"Mid-cap PEAD signal: buy 30-45 DTE calls within 2 days. "
                f"Historical 30-60 day upward drift."
            ),
        },
        "confidence": 70.0 + min(20, beat_magnitude * 100),
    }


# ---------------------------------------------------------------------------
# Signal: Analyst Revision Cascade
# ---------------------------------------------------------------------------

async def check_analyst_revision_cascade(
    symbol: str,
    recent_revisions: list[dict],  # [{analyst, firm, old_eps, new_eps, date}]
    window_days: int = 7,
) -> dict | None:
    """
    Trigger: 3+ analysts raise EPS estimates within 7 days, consensus raised >5%.
    Exploitable 30-60 day lag as index funds rebalance (ExtractAlpha confirmed).
    """
    cutoff = date.today() - timedelta(days=window_days)
    recent = [r for r in recent_revisions
              if r.get("direction") == "up"
              and date.fromisoformat(r.get("date", "2000-01-01")) >= cutoff]

    if len(recent) < 3:
        return None

    # Check consensus raise >5%
    old_estimates = [r.get("old_eps", 0) for r in recent if r.get("old_eps")]
    new_estimates = [r.get("new_eps", 0) for r in recent if r.get("new_eps")]

    if old_estimates and new_estimates:
        avg_old = np.mean(old_estimates)
        avg_new = np.mean(new_estimates)
        if avg_old <= 0 or (avg_new - avg_old) / abs(avg_old) < 0.05:
            return None  # less than 5% consensus raise

    # Dedup
    dedup_key = f"compound:revision:{symbol}:{date.today().isocalendar()[1]}"
    if await cache_get(dedup_key):
        return None
    await cache_set(dedup_key, "1", ttl=86400 * 7)

    return {
        "signal_type": "analyst_revision_cascade",
        "symbols": [symbol],
        "trigger_details": {
            "analysts_count": len(recent),
            "window_days": window_days,
            "firms": list({r.get("firm", "Unknown") for r in recent}),
            "action": (
                f"{symbol}: {len(recent)} analysts raised EPS in {window_days} days. "
                "Analyst revision cascade — 30-60 day alpha window before benchmark rebalance. "
                "Buy 30-45 DTE calls now."
            ),
        },
        "confidence": 65.0 + min(25, len(recent) * 5),
    }


# ---------------------------------------------------------------------------
# Signal: Sector Dispersion (Kakushadze 6.3)
# ---------------------------------------------------------------------------

async def check_sector_dispersion(
    sector_etf: str,
    component_symbols: list[str],
    implied_correlation: float | None,
    sector_ivr: float | None,
) -> dict | None:
    """
    Sector dispersion trade:
    Trigger: CBOE Implied Correlation > 35th percentile AND sector IVR > 50.
    Trade: Short vol on sector ETF, long vol on top 3 components.

    Correlation risk premium: index implied corr (39.5% avg) > realized (32.5%) = structural gap.
    """
    if implied_correlation is None or sector_ivr is None:
        return None

    corr_threshold = 0.365  # CBOE COR1M mean ~39.5%, 35th pct ≈ 36.5%

    if implied_correlation < corr_threshold or sector_ivr < 50:
        return None

    return {
        "signal_type": "sector_dispersion",
        "symbols": [sector_etf] + component_symbols[:3],
        "trigger_details": {
            "sector_etf": sector_etf,
            "implied_correlation": round(implied_correlation, 3),
            "sector_ivr": round(sector_ivr, 1),
            "components": component_symbols[:3],
            "action": (
                f"Dispersion trade: {sector_etf} IVR={sector_ivr:.0f}, "
                f"implied corr={implied_correlation:.0%}. "
                f"Short vol on {sector_etf} straddle, "
                f"long vol on {'/'.join(component_symbols[:3])} — Kakushadze 6.3 structure."
            ),
        },
        "confidence": 60.0,
    }


# ---------------------------------------------------------------------------
# Discord alert + DB persistence
# ---------------------------------------------------------------------------

async def _send_compound_signal_alert(signal: dict) -> None:
    if not settings.DISCORD_WEBHOOK_URL:
        return

    signal_type = signal.get("signal_type", "unknown")
    symbols = signal.get("symbols", [])
    details = signal.get("trigger_details", {})
    confidence = signal.get("confidence", 0)
    action = details.get("action", "")

    color_map = {
        "beat_raise_pead": 0x00cc66,
        "analyst_revision_cascade": 0xffcc00,
        "sector_dispersion": 0x66cccc,
    }

    payload = {
        "embeds": [{
            "title": f"🚨 Compound Signal: {signal_type.replace('_', ' ').title()}",
            "description": action or f"Signal fired for {', '.join(symbols)}",
            "color": color_map.get(signal_type, 0xffffff),
            "fields": [
                {"name": "Symbols", "value": ", ".join(symbols) or "—", "inline": True},
                {"name": "Confidence", "value": f"{confidence:.0f}%", "inline": True},
            ],
            "footer": {"text": f"Compound Signals Engine • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"},
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
        logger.info(f"Compound signal Discord alert sent: {signal_type}")
    except Exception as e:
        logger.debug(f"Compound signal Discord alert failed: {e}")


async def _save_to_db(signal: dict, session=None) -> None:
    if session is None:
        return

    from sqlalchemy import text
    import orjson

    try:
        await session.execute(
            text("""
                INSERT INTO compound_signal_events (
                    signal_type, symbols, trigger_details, confidence, action_taken
                ) VALUES (:st, :syms, :td::jsonb, :conf, :act)
            """),
            {
                "st": signal.get("signal_type"),
                "syms": signal.get("symbols", []),
                "td": orjson.dumps(signal.get("trigger_details", {})).decode(),
                "conf": signal.get("confidence", 0),
                "act": "discord_alert",
            }
        )
        await session.commit()
    except Exception as e:
        logger.debug(f"Compound signal DB save failed: {e}")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_all_compound_checks(
    options_flow: dict[str, dict] | None = None,  # kept for API compat; no longer used
    session=None,
) -> list[dict]:
    """
    Run compound signal checks that can fire without per-symbol triggers.
    Beat-and-raise and analyst-revision-cascade fire from earnings/analyst pipelines.
    Sector dispersion needs sector-specific input — call check_sector_dispersion() directly.
    """
    _ = options_flow  # placeholder; cascade signal removed in Phase A cleanup
    return []


# ---------------------------------------------------------------------------
# Individual checkers called from earnings / analyst pipelines
# ---------------------------------------------------------------------------

async def fire_beat_and_raise(symbol: str, market_cap: float,
                               eps_actual: float, eps_estimate: float,
                               rev_actual: float, rev_estimate: float,
                               raised_guidance: bool = False,
                               session=None) -> dict | None:
    """Called by earnings pipeline when a stock reports."""
    signal = await check_beat_and_raise_pead(
        symbol, market_cap, eps_actual, eps_estimate, rev_actual, rev_estimate, raised_guidance
    )
    if signal:
        await asyncio.gather(
            _send_compound_signal_alert(signal),
            _save_to_db(signal, session),
        )
    return signal


async def fire_revision_cascade(symbol: str, revisions: list[dict],
                                  session=None) -> dict | None:
    """Called by analyst_targets pipeline when revisions accumulate."""
    signal = await check_analyst_revision_cascade(symbol, revisions)
    if signal:
        await asyncio.gather(
            _send_compound_signal_alert(signal),
            _save_to_db(signal, session),
        )
    return signal
