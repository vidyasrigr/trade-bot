"""
Discord webhook notifications — zero bot token required.
Just set DISCORD_WEBHOOK_URL in .env.

Alert severity levels:
  INFO    → blue embed
  SUCCESS → green embed  (profit target hit, trade closed for gain)
  WARNING → yellow embed (roll alert, 21 DTE, early assignment watch)
  DANGER  → red embed    (stop loss, circuit breaker, assignment CRITICAL)
"""

import httpx
from loguru import logger

from core.config import settings


_COLORS = {
    "info":    0x3B82F6,  # blue
    "success": 0x22C55E,  # green
    "warning": 0xF59E0B,  # yellow
    "danger":  0xEF4444,  # red
}

_ALERT_TYPE_SEVERITY: dict[str, str] = {
    "profit_target":              "success",
    "stop_loss":                  "danger",
    "roll_alert":                 "warning",
    "earnings_proximity":         "warning",
    "expired":                    "warning",
    "early_assignment_watch":     "warning",
    "early_assignment_alert":     "danger",
    "early_assignment_critical":  "danger",
    "circuit_breaker":            "danger",
    "kill_switch":                "danger",
    "new_setup":                  "info",
    "scan_complete":              "info",
}


async def send_alert(
    title: str,
    message: str,
    alert_type: str = "info",
    fields: list[dict] | None = None,
    symbol: str | None = None,
) -> bool:
    """
    Send a Discord webhook notification.

    Returns True if sent successfully, False if webhook not configured or failed.
    """
    webhook_url = settings.DISCORD_WEBHOOK_URL
    if not webhook_url:
        return False

    severity = _ALERT_TYPE_SEVERITY.get(alert_type, "info")
    color = _COLORS[severity]

    embed: dict = {
        "title": title,
        "description": message,
        "color": color,
        "footer": {"text": "Options Trading Bot"},
    }

    if symbol:
        embed["author"] = {"name": f"${symbol}"}

    if fields:
        embed["fields"] = fields

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code not in (200, 204):
                logger.warning(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")
                return False
        return True
    except Exception as e:
        logger.warning(f"Discord notification failed: {e}")
        return False


async def notify_position_alerts(alerts: list[dict]) -> None:
    """Send batch position alerts to Discord, grouping by symbol."""
    for alert in alerts:
        alert_type = alert.get("alert_type", "info")
        severity   = _ALERT_TYPE_SEVERITY.get(alert_type, "info")
        symbol     = alert.get("symbol", "")

        title = {
            "profit_target":             f"✅ Profit Target — ${symbol}",
            "stop_loss":                 f"🛑 Stop Loss Alert — ${symbol}",
            "roll_alert":                f"⏰ Roll Alert — ${symbol}",
            "earnings_proximity":        f"📅 Earnings Proximity — ${symbol}",
            "early_assignment_watch":    f"👁 Assignment Watch — ${symbol}",
            "early_assignment_alert":    f"⚠️ Assignment Alert — ${symbol}",
            "early_assignment_critical": f"🚨 CRITICAL Assignment Risk — ${symbol}",
        }.get(alert_type, f"📊 Position Alert — ${symbol}")

        fields = []
        if alert.get("assignment_risk"):
            fields.append({"name": "Assignment Risk", "value": alert["assignment_risk"].upper(), "inline": True})
        if alert.get("est_delta"):
            fields.append({"name": "Est. Delta", "value": str(alert["est_delta"]), "inline": True})
        if alert.get("ex_div_days") is not None:
            fields.append({"name": "Ex-Div Days", "value": str(alert["ex_div_days"]), "inline": True})
        if alert.get("action"):
            fields.append({"name": "Recommended Action", "value": alert["action"], "inline": False})

        await send_alert(
            title=title,
            message=alert.get("message", ""),
            alert_type=alert_type,
            fields=fields or None,
            symbol=symbol,
        )


async def notify_scan_complete(result_count: int, top_symbols: list[str]) -> None:
    await send_alert(
        title="🔍 Scan Complete",
        message=f"Found **{result_count}** setups from tonight's 5-stage funnel.",
        alert_type="scan_complete",
        fields=[{"name": "Top Setups", "value": " · ".join(f"${s}" for s in top_symbols[:5]), "inline": False}],
    )


async def notify_circuit_breaker(reason: str, active_breakers: list[str]) -> None:
    await send_alert(
        title="🚨 CIRCUIT BREAKER ACTIVE",
        message=f"**All new trades halted.**\n{reason}",
        alert_type="circuit_breaker",
        fields=[{"name": "Active Breakers", "value": ", ".join(active_breakers), "inline": False}],
    )


async def notify_new_setup(symbol: str, score: float, direction: str, stream: str, thesis_summary: str) -> None:
    emoji = "🟢" if direction == "bullish" else "🔴" if direction == "bearish" else "⚪"
    stream_emoji = "🎰" if stream == "alpha" else "💰"
    await send_alert(
        title=f"{emoji} New Setup: ${symbol} — {stream_emoji} {stream.title()} Stream",
        message=thesis_summary[:400],
        alert_type="new_setup",
        symbol=symbol,
        fields=[
            {"name": "Score", "value": f"{score:.1f}/100", "inline": True},
            {"name": "Direction", "value": direction.title(), "inline": True},
            {"name": "Stream", "value": stream.title(), "inline": True},
        ],
    )
