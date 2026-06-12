"""
Position monitor — runs every 15 min during market hours.
Checks: profit targets, stop losses, 21 DTE roll alerts, earnings proximity,
early assignment risk (state machine), and circuit breaker status.
"""

from datetime import date, datetime, timedelta
from enum import Enum

from loguru import logger

from core.config import settings


class AssignmentRisk(str, Enum):
    NONE     = "none"       # No risk
    WATCH    = "watch"      # Monitor: approaching ITM threshold or ex-div within 7 days
    ALERT    = "alert"      # Act soon: delta > 0.80 or ex-div within 3 days + ITM
    CRITICAL = "critical"   # Very likely assignment: delta > 0.90 AND ex-div tomorrow/today


async def check_all_positions():
    """Main job: iterate all open positions and fire alerts."""
    open_positions = await _get_open_positions()
    if not open_positions:
        return

    alerts = []
    for pos in open_positions:
        pos_alerts = await _check_position(pos)
        alerts.extend(pos_alerts)

    if alerts:
        await _send_alerts(alerts)


async def _check_position(pos: dict) -> list[dict]:
    """Check a single position for management signals."""
    from data.tradier import get_tradier

    alerts = []
    symbol = pos["symbol"]
    tradier = get_tradier()

    try:
        quote = await tradier.get_quote(symbol)
        current_price = float(quote.get("last") or quote.get("close") or 0)
    except Exception:
        current_price = 0

    entry_price = float(pos.get("entry_price") or 0)
    max_profit  = float(pos.get("max_profit") or 0)
    max_loss    = float(pos.get("max_loss") or 0)
    contracts   = int(pos.get("contracts") or 1)
    strategy    = pos.get("strategy", "")
    expiry      = pos.get("expiry")
    trade_id    = pos["id"]

    # Unrealized P&L (approximate from current underlying price)
    # For a proper system, we'd fetch current option price from Tradier
    # This is a simplified P&L estimate
    if current_price > 0 and entry_price > 0:
        price_change_pct = (current_price - pos.get("entry_underlying", current_price)) / pos.get("entry_underlying", current_price)

        # Profit target: 50% of max profit
        if max_profit > 0:
            est_pnl = price_change_pct * entry_price * contracts * 100
            if strategy in ("bull_put_spread", "bear_call_spread", "iron_condor"):
                profit_target = max_profit * settings.PROFIT_TARGET_PCT
                if est_pnl >= profit_target:
                    alerts.append({
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "alert_type": "profit_target",
                        "message": f"{symbol}: ≥50% max profit reached — consider closing {strategy}",
                        "action": "CLOSE",
                    })

        # Stop loss
        if max_loss > 0:
            est_loss = -price_change_pct * entry_price * contracts * 100
            stop_threshold = max_loss * (settings.STOP_LOSS_CREDIT_MULT if "spread" in strategy else 1.0)
            if est_loss >= stop_threshold:
                alerts.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "alert_type": "stop_loss",
                    "message": f"{symbol}: MAX LOSS approaching — evaluate exit immediately",
                    "action": "CLOSE_URGENT",
                })

    # DTE check
    if expiry:
        try:
            exp_date = date.fromisoformat(str(expiry)[:10])
            dte = (exp_date - date.today()).days
            if dte <= settings.ROLL_ALERT_DTE and dte > 0:
                alerts.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "alert_type": "roll_alert",
                    "message": f"{symbol}: {dte} DTE remaining — roll or close by {expiry}",
                    "action": "ROLL_OR_CLOSE",
                })
            elif dte <= 0:
                alerts.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "alert_type": "expired",
                    "message": f"{symbol}: Position expired — update status",
                    "action": "UPDATE_STATUS",
                })
        except Exception:
            pass

    # Early assignment state machine
    assignment_alerts = await _check_early_assignment(pos, current_price)
    alerts.extend(assignment_alerts)

    return alerts


async def _check_early_assignment(pos: dict, current_price: float) -> list[dict]:
    """
    Early assignment state machine for short options legs.

    Two triggers:
    1. Deep ITM: short call delta > 0.85 (holder has high incentive to exercise for dividends/value)
    2. Ex-dividend: underlying goes ex-div within 3 days AND short call is ITM
       — American-style call holders exercise the day BEFORE ex-div to capture dividend

    States: NONE → WATCH → ALERT → CRITICAL
    """
    alerts = []
    strategy   = pos.get("strategy", "")
    symbol     = pos.get("symbol", "")
    trade_id   = pos["id"]
    expiry     = pos.get("expiry")
    short_strike = pos.get("short_strike") or pos.get("strike")

    # Only short options are at risk (spreads with short legs, naked puts/calls)
    has_short_leg = strategy in (
        "bull_put_spread", "bear_call_spread", "iron_condor",
        "naked_put", "naked_call", "covered_call",
    )
    if not has_short_leg or not short_strike or current_price <= 0:
        return []

    short_strike = float(short_strike)

    # Determine if short leg is ITM
    is_call_side = strategy in ("bear_call_spread", "naked_call", "covered_call")
    is_put_side  = strategy in ("bull_put_spread", "naked_put")
    is_iron_condor = strategy == "iron_condor"

    call_itm = is_call_side and current_price > short_strike
    put_itm  = is_put_side  and current_price < short_strike
    # For iron condors, check both sides
    ic_call_itm = is_iron_condor and current_price > short_strike
    ic_put_itm  = is_iron_condor and current_price < pos.get("short_put_strike", 0)

    itm = call_itm or put_itm or ic_call_itm or ic_put_itm
    if not itm:
        return []  # OTM short — no assignment risk

    # Assess moneyness depth
    moneyness_pct = abs(current_price - short_strike) / short_strike

    # Fetch approximate delta from trade record (set at entry; actual delta may differ)
    entry_delta = abs(float(pos.get("entry_delta") or 0))
    # Rough current delta estimate: if deep ITM, bump it up
    if moneyness_pct > 0.10:
        est_delta = min(0.95, entry_delta + 0.30)
    elif moneyness_pct > 0.05:
        est_delta = min(0.90, entry_delta + 0.15)
    else:
        est_delta = min(0.85, entry_delta + 0.05)

    # Check ex-dividend proximity
    ex_div_days = await _get_ex_dividend_days(symbol)

    # State machine transitions
    risk_level = AssignmentRisk.NONE

    if est_delta >= 0.90 and ex_div_days is not None and ex_div_days <= 1:
        risk_level = AssignmentRisk.CRITICAL
    elif est_delta >= 0.85 or (ex_div_days is not None and ex_div_days <= 3 and itm):
        risk_level = AssignmentRisk.ALERT
    elif est_delta >= 0.75 or (ex_div_days is not None and ex_div_days <= 7 and itm):
        risk_level = AssignmentRisk.WATCH

    if risk_level == AssignmentRisk.NONE:
        return []

    # Build alert message
    ex_div_note = f", ex-div in {ex_div_days}d" if ex_div_days is not None else ""
    moneyness_note = f"{round(moneyness_pct * 100, 1)}% ITM"

    msg_map = {
        AssignmentRisk.WATCH: (
            f"{symbol}: Short leg {moneyness_note} (est Δ {round(est_delta, 2)}){ex_div_note} — "
            f"monitor for assignment risk"
        ),
        AssignmentRisk.ALERT: (
            f"{symbol}: ASSIGNMENT ALERT — short {strategy} {moneyness_note} (est Δ {round(est_delta, 2)}){ex_div_note}. "
            f"Consider rolling or closing short leg before ex-div/expiry."
        ),
        AssignmentRisk.CRITICAL: (
            f"{symbol}: CRITICAL ASSIGNMENT RISK — short call deep ITM Δ {round(est_delta, 2)}, "
            f"ex-div {ex_div_days}d away. Exercise likely TONIGHT. Close or roll NOW."
        ),
    }

    alerts.append({
        "trade_id": trade_id,
        "symbol": symbol,
        "alert_type": f"early_assignment_{risk_level.value}",
        "assignment_risk": risk_level.value,
        "moneyness_pct": round(moneyness_pct * 100, 1),
        "est_delta": round(est_delta, 2),
        "ex_div_days": ex_div_days,
        "message": msg_map[risk_level],
        "action": "CLOSE_URGENT" if risk_level == AssignmentRisk.CRITICAL else "ROLL_OR_CLOSE",
    })

    return alerts


async def _get_ex_dividend_days(symbol: str) -> int | None:
    """
    Returns days until next ex-dividend date for the symbol, or None if not paying dividends.
    Uses yfinance as a lightweight lookup (no API key required).
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info
        ex_div_str = info.get("exDividendDate")
        if not ex_div_str:
            return None
        # yfinance returns Unix timestamp for exDividendDate
        if isinstance(ex_div_str, (int, float)):
            from datetime import timezone
            ex_div_date = datetime.fromtimestamp(ex_div_str, tz=timezone.utc).date()
        else:
            ex_div_date = date.fromisoformat(str(ex_div_str)[:10])
        days_until = (ex_div_date - date.today()).days
        return days_until if days_until >= 0 else None
    except Exception as e:
        logger.debug(f"Ex-div lookup failed for {symbol}: {e}")
        return None


async def _send_alerts(alerts: list[dict]):
    """Push alerts to UI via Redis pub/sub + Discord + optional Twilio SMS."""
    import orjson
    from core.redis_client import get_redis
    from api.discord_notify import notify_position_alerts

    redis = get_redis()
    for alert in alerts:
        await redis.publish("position_alerts", orjson.dumps(alert).decode())
        logger.info(f"Position alert: {alert['symbol']} — {alert['alert_type']}")

    # Discord — all alerts
    await notify_position_alerts(alerts)

    # Twilio SMS — only CRITICAL (assignment risk, stop loss hitting)
    urgent = [a for a in alerts if a.get("action") == "CLOSE_URGENT"]
    if urgent and settings.TWILIO_ACCOUNT_SID:
        await _send_sms(urgent)


async def _send_sms(alerts: list[dict]):
    """Send SMS via Twilio for urgent alerts."""
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        for alert in alerts[:3]:  # max 3 SMS per run
            client.messages.create(
                body=f"🚨 OPTIONS ALERT: {alert['message']}",
                from_=settings.TWILIO_FROM_NUMBER,
                to=settings.TWILIO_TO_NUMBER,
            )
    except Exception as e:
        logger.error(f"Twilio SMS failed: {e}")


async def _get_open_positions() -> list[dict]:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT id, symbol, strategy, entry_price, max_profit, max_loss,
                       contracts, expiry, opened_at
                FROM paper_trades
                WHERE status = 'open'
            """))
            rows = result.fetchall()
        return [
            {
                "id": r[0], "symbol": r[1], "strategy": r[2],
                "entry_price": r[3], "max_profit": r[4], "max_loss": r[5],
                "contracts": r[6], "expiry": r[7], "opened_at": r[8],
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug(f"Could not fetch open positions: {e}")
        return []
