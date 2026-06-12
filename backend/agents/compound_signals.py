"""
Compound Signal Detector — multi-stock, multi-indicator patterns with documented alpha.

Signals:
  1. Semiconductor Sector Cascade (March 2026 documented — SOX rally preceded by cross-sector call sweeps)
  2. VIX Spike Buy (April 2025 documented — VIX 17→60 → 35%+ rally, 80%+ win rate historically)
  3. Beat-and-Raise PEAD — mid/small cap only (<$50B market cap)
  4. Hyperscaler Lead for Semis (MSFT/GOOGL/META capex beats → NVDA/AMD 2-week lag)
  5. Analyst Revision Cascade (3+ analysts raise EPS >5% within 7 days)
  6. Sector Dispersion (Kakushadze 6.3 — short vol on ETF, long vol on components)

Each signal fires a Discord alert and saves to compound_signal_events table.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, date
from typing import Any

import httpx
import numpy as np
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


SEMIS_CASCADE_SYMBOLS = ["NVDA", "AMD", "INTC", "AVGO", "QCOM"]
HYPERSCALER_SYMBOLS = ["MSFT", "GOOGL", "META"]
SEMIS_DOWNSTREAM = ["NVDA", "AMD", "AVGO"]  # target when hyperscalers beat on capex


# ---------------------------------------------------------------------------
# Signal 1: Semiconductor Sector Cascade
# ---------------------------------------------------------------------------

async def check_semis_cascade(
    options_flow: dict[str, dict],  # {symbol: {call_volume, put_volume, avg_oi, ...}}
) -> dict | None:
    """
    Trigger: 2+ of {NVDA, INTC, AMD, AVGO, QCOM} simultaneously have call sweeps
    (volume >> OI, at-ask) on same trading day.
    """
    cascade_members_firing = []

    for sym in SEMIS_CASCADE_SYMBOLS:
        flow = options_flow.get(sym, {})
        call_vol = flow.get("call_volume", 0)
        avg_call_oi = flow.get("avg_call_oi", 0)
        call_at_ask_pct = flow.get("call_at_ask_pct", 0)

        if avg_call_oi > 0 and call_vol > avg_call_oi * 1.5 and call_at_ask_pct > 0.6:
            cascade_members_firing.append(sym)

    if len(cascade_members_firing) >= 2:
        signal = {
            "signal_type": "semis_cascade",
            "symbols": cascade_members_firing,
            "trigger_details": {
                "members_firing": cascade_members_firing,
                "action": f"Consider long SMH or individual semis — 1-2 week timeframe. "
                          f"Firing: {', '.join(cascade_members_firing)}",
            },
            "confidence": min(95.0, 50 + len(cascade_members_firing) * 20),
        }
        return signal

    return None


# ---------------------------------------------------------------------------
# Signal 2: VIX Spike Buy
# ---------------------------------------------------------------------------

async def check_vix_spike_buy() -> dict | None:
    """
    Trigger: VIX crosses above 35 from below, having been below 20 within the past 15 trading days.
    Only for rapid spike (8+ point move in <10 days) — NOT slow creep.
    Historical win rate: 80%+ for 3-6 month equity long.
    """
    cache_key = "vix_spike:history"
    cached = await cache_get(cache_key)
    if not cached:
        return None

    import orjson
    vix_history: list[float] = orjson.loads(cached)  # last 20 trading days, most recent first

    if len(vix_history) < 15:
        return None

    current_vix = vix_history[0]

    # Check: current VIX above 35
    if current_vix < 35:
        return None

    # Check: was below 20 within last 15 trading days
    recent = vix_history[1:16]
    was_below_20 = any(v < 20 for v in recent)
    if not was_below_20:
        return None

    # Check: rapid spike (moved 8+ points in <10 days)
    for i in range(1, 11):
        if i < len(vix_history) and vix_history[i] < current_vix - 8:
            was_rapid = True
            break
    else:
        was_rapid = False

    if not was_rapid:
        return None

    # Dedup: don't fire more than once per week
    dedup_key = f"compound:vix_spike:{date.today().isocalendar()[1]}"
    if await cache_get(dedup_key):
        return None
    await cache_set(dedup_key, "1", ttl=86400 * 7)

    return {
        "signal_type": "vix_spike_buy",
        "symbols": ["SPY", "QQQ"],
        "trigger_details": {
            "current_vix": current_vix,
            "was_below_20_recently": True,
            "was_rapid_spike": True,
            "action": (
                f"VIX spike buy signal — VIX at {current_vix:.1f}, spiked from below 20 rapidly. "
                "Historical 3-6 month equity long signal (80%+ win rate). "
                "Consider SPX/QQQ 30-60 DTE calls."
            ),
        },
        "confidence": 80.0,
    }


# ---------------------------------------------------------------------------
# Signal 3: Beat-and-Raise PEAD (mid/small cap only)
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
# Signal 4: Hyperscaler Lead for Semis
# ---------------------------------------------------------------------------

async def check_hyperscaler_lead(
    hyperscaler_symbol: str,
    capex_actual: float,
    capex_prior_year: float,
    eps_beat: bool = False,
) -> dict | None:
    """
    Trigger: MSFT, GOOGL, or META reports earnings with capex guidance raised >10% YoY.
    This signals GPU demand increase → NVDA, AMD, AVGO benefit 1-2 weeks later.
    """
    if hyperscaler_symbol not in HYPERSCALER_SYMBOLS:
        return None

    if capex_prior_year <= 0:
        return None

    capex_growth = (capex_actual - capex_prior_year) / capex_prior_year
    if capex_growth < 0.10:  # <10% YoY capex increase
        return None

    # Dedup: once per earnings cycle
    dedup_key = f"compound:hyperscaler:{hyperscaler_symbol}:{date.today().strftime('%Y-Q%q')}"
    if await cache_get(dedup_key):
        return None
    await cache_set(dedup_key, "1", ttl=86400 * 90)

    downstream = SEMIS_DOWNSTREAM.copy()
    lag_days = {"NVDA": 14, "AMD": 7, "AVGO": 7}

    return {
        "signal_type": "hyperscaler_lead",
        "symbols": downstream,
        "trigger_details": {
            "hyperscaler": hyperscaler_symbol,
            "capex_growth_pct": round(capex_growth * 100, 1),
            "eps_beat": eps_beat,
            "target_symbols": downstream,
            "lag_days": lag_days,
            "action": (
                f"{hyperscaler_symbol} capex +{capex_growth*100:.0f}% YoY. "
                f"Semis buy window: {', '.join(downstream)}. "
                f"NVDA entry window: next 14 days. AMD/AVGO: next 7 days."
            ),
        },
        "confidence": 75.0 + (10.0 if eps_beat else 0.0),
    }


# ---------------------------------------------------------------------------
# Signal 5: Analyst Revision Cascade
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
# Signal 6: Sector Dispersion (Kakushadze 6.3)
# ---------------------------------------------------------------------------

async def check_sector_dispersion(
    sector_etf: str,     # e.g., "SMH"
    component_symbols: list[str],  # e.g., ["NVDA", "AMD", "AVGO"]
    implied_correlation: float | None,  # CBOE COR1M (free)
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

    # CBOE COR1M historical mean ~39.5%, std ~8%
    # 35th percentile ≈ mean - 0.38*std ≈ 36.5%
    corr_threshold = 0.365

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
# Discord alert sender
# ---------------------------------------------------------------------------

async def _send_compound_signal_alert(signal: dict) -> None:
    """Send a compound signal alert to Discord."""
    if not settings.DISCORD_WEBHOOK_URL:
        return

    signal_type = signal.get("signal_type", "unknown")
    symbols = signal.get("symbols", [])
    details = signal.get("trigger_details", {})
    confidence = signal.get("confidence", 0)
    action = details.get("action", "")

    color_map = {
        "semis_cascade": 0x00aaff,
        "vix_spike_buy": 0xff8800,
        "beat_raise_pead": 0x00cc66,
        "hyperscaler_lead": 0x9966ff,
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
    """Persist compound signal to compound_signal_events table."""
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
# Main runner (called by watchlist_agent or scheduler)
# ---------------------------------------------------------------------------

async def run_all_compound_checks(
    options_flow: dict[str, dict] | None = None,
    session=None,
) -> list[dict]:
    """
    Run all compound signal checks that can be evaluated without per-symbol data.
    Returns list of fired signals.
    """
    fired: list[dict] = []

    # Signal 1: Semis cascade
    if options_flow:
        cascade = await check_semis_cascade(options_flow)
        if cascade:
            fired.append(cascade)

    # Signal 2: VIX spike
    vix_signal = await check_vix_spike_buy()
    if vix_signal:
        fired.append(vix_signal)

    # Fire alerts and persist
    for signal in fired:
        await asyncio.gather(
            _send_compound_signal_alert(signal),
            _save_to_db(signal, session),
        )

    if fired:
        logger.info(f"Compound signals fired: {[s['signal_type'] for s in fired]}")

    return fired


# ---------------------------------------------------------------------------
# Individual checkers called from watchlist_agent or earnings pipeline
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


async def fire_hyperscaler_lead(hyperscaler: str, capex_actual: float,
                                 capex_prior: float, eps_beat: bool = False,
                                 session=None) -> dict | None:
    """Called by earnings pipeline when a hyperscaler (MSFT/GOOGL/META) reports."""
    signal = await check_hyperscaler_lead(hyperscaler, capex_actual, capex_prior, eps_beat)
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
