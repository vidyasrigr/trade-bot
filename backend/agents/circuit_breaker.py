"""
Failsafe circuit breakers — checked before every new trade is approved.

Breakers:
  DAILY_LOSS_CAP   : today's realized + unrealized PnL < -5% of portfolio value → halt
  MAX_DRAWDOWN     : portfolio value < 85% of all-time peak → halt
  POSITION_LIMIT   : >= 10 concurrent open positions → halt
  KILL_SWITCH      : manual override via POST /api/admin/kill-switch → halt
  SECTOR_CONCENTRATION : single sector > 35% of deployed risk → warn
"""

from datetime import date
from dataclasses import dataclass, field

from loguru import logger

from core.config import settings

# Redis key for kill switch
_KILL_SWITCH_KEY = "circuit_breaker:kill_switch"
_DAILY_HALT_KEY  = "circuit_breaker:daily_halt"


@dataclass
class BreakerStatus:
    halted: bool
    active_breakers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "halted": self.halted,
            "active_breakers": self.active_breakers,
            "warnings": self.warnings,
            "reason": self.reason,
        }


async def check_all_breakers(portfolio_state: dict | None = None) -> BreakerStatus:
    """
    Run all circuit breakers. Returns BreakerStatus with halted=True if any hard
    breaker is triggered. Must pass before any new trade is approved.

    Args:
        portfolio_state: dict with keys:
            - portfolio_value: float (current total value)
            - peak_value: float (all-time high)
            - daily_realized_pnl: float
            - daily_unrealized_pnl: float
            - open_position_count: int
            - sector_exposure: dict[sector_name, pct_of_deployed_risk]
    """
    from core.redis_client import get_redis

    status = BreakerStatus(halted=False)

    # ── 1. Kill switch (manual override) ─────────────────────────────────────
    try:
        redis = get_redis()
        kill_active = await redis.get(_KILL_SWITCH_KEY)
        if kill_active:
            status.halted = True
            status.active_breakers.append("KILL_SWITCH")
            status.reason = "Manual kill switch is active. POST /api/admin/kill-switch {\"active\": false} to reset."
            return status  # Short-circuit — no point checking further
    except Exception as e:
        logger.warning(f"Circuit breaker Redis check failed: {e}")

    if portfolio_state is None:
        portfolio_state = await _load_portfolio_state()

    portfolio_value    = float(portfolio_state.get("portfolio_value") or 0)
    peak_value         = float(portfolio_state.get("peak_value") or portfolio_value)
    daily_realized     = float(portfolio_state.get("daily_realized_pnl") or 0)
    daily_unrealized   = float(portfolio_state.get("daily_unrealized_pnl") or 0)
    open_count         = int(portfolio_state.get("open_position_count") or 0)
    sector_exposure    = portfolio_state.get("sector_exposure") or {}

    # ── 2. Daily loss cap ─────────────────────────────────────────────────────
    if portfolio_value > 0:
        daily_pnl_total = daily_realized + daily_unrealized
        daily_loss_pct  = daily_pnl_total / portfolio_value

        if daily_loss_pct <= -settings.DAILY_LOSS_CAP_PCT:
            status.halted = True
            status.active_breakers.append("DAILY_LOSS_CAP")
            loss_str = f"{round(daily_loss_pct * 100, 1)}% (${round(-daily_pnl_total, 0):,.0f})"
            status.reason = (
                f"Daily loss cap hit: {loss_str} today exceeds "
                f"{round(settings.DAILY_LOSS_CAP_PCT * 100, 0):.0f}% limit. "
                f"No new trades until market open tomorrow."
            )
            # Persist daily halt in Redis (expires at midnight)
            try:
                from datetime import datetime, timezone
                seconds_to_midnight = (
                    86400 - (datetime.now(timezone.utc).hour * 3600
                             + datetime.now(timezone.utc).minute * 60
                             + datetime.now(timezone.utc).second)
                )
                await redis.setex(_DAILY_HALT_KEY, int(seconds_to_midnight) + 300, "1")
            except Exception:
                pass
            logger.warning(f"CIRCUIT BREAKER: Daily loss cap — {loss_str}")

    # ── 3. Max drawdown from peak ─────────────────────────────────────────────
    if peak_value > 0:
        drawdown_pct = (portfolio_value - peak_value) / peak_value
        if drawdown_pct <= -settings.MAX_DRAWDOWN_PCT:
            status.halted = True
            status.active_breakers.append("MAX_DRAWDOWN")
            dd_str = f"{round(drawdown_pct * 100, 1)}%"
            status.reason = status.reason or (
                f"Max drawdown hit: portfolio is {dd_str} from peak "
                f"(limit: -{round(settings.MAX_DRAWDOWN_PCT * 100, 0):.0f}%). "
                f"Review and reset manually via /api/admin/reset-drawdown."
            )
            logger.warning(f"CIRCUIT BREAKER: Max drawdown {dd_str} from peak")

    # ── 4. Position limit ─────────────────────────────────────────────────────
    if open_count >= settings.MAX_OPEN_POSITIONS:
        status.halted = True
        status.active_breakers.append("POSITION_LIMIT")
        status.reason = status.reason or (
            f"Position limit reached: {open_count}/{settings.MAX_OPEN_POSITIONS} open positions. "
            f"Close an existing position before adding new ones."
        )

    # ── 5. Sector concentration warning (soft — doesn't halt, just warns) ────
    for sector, exposure_pct in sector_exposure.items():
        if exposure_pct > settings.MAX_SECTOR_CONCENTRATION:
            status.warnings.append(
                f"{sector} sector at {round(exposure_pct * 100, 1)}% of deployed risk "
                f"(limit: {round(settings.MAX_SECTOR_CONCENTRATION * 100, 0):.0f}%)"
            )

    if status.active_breakers and not status.reason:
        status.reason = f"Breakers active: {', '.join(status.active_breakers)}"

    return status


async def activate_kill_switch(reason: str = "Manual override") -> None:
    """Activate the kill switch — halts all new trades immediately."""
    from core.redis_client import get_redis
    from api.discord_notify import notify_circuit_breaker

    redis = get_redis()
    await redis.setex(_KILL_SWITCH_KEY, 86400, reason)
    logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
    await notify_circuit_breaker(reason, ["KILL_SWITCH"])


async def deactivate_kill_switch() -> None:
    """Deactivate kill switch — allows trading to resume."""
    from core.redis_client import get_redis
    redis = get_redis()
    await redis.delete(_KILL_SWITCH_KEY)
    logger.info("Kill switch deactivated — trading resumed")


async def get_kill_switch_status() -> dict:
    """Returns current kill switch state."""
    try:
        from core.redis_client import get_redis
        redis = get_redis()
        reason = await redis.get(_KILL_SWITCH_KEY)
        return {
            "active": bool(reason),
            "reason": reason.decode() if reason else None,
        }
    except Exception:
        return {"active": False, "reason": None}


async def _load_portfolio_state() -> dict:
    """Load current portfolio state from DB for circuit breaker evaluation."""
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'open') AS open_count,
                    COALESCE(SUM(realized_pnl) FILTER (WHERE closed_at::date = CURRENT_DATE), 0) AS daily_realized,
                    COALESCE(SUM(unrealized_pnl) FILTER (WHERE status = 'open'), 0) AS daily_unrealized
                FROM paper_trades
            """))
            row = result.fetchone()
            open_count, daily_realized, daily_unrealized = row if row else (0, 0, 0)

            # Peak value from settings (could be stored in a portfolio_meta table)
            portfolio_value = settings.PAPER_PORTFOLIO_VALUE
            return {
                "portfolio_value": portfolio_value,
                "peak_value": portfolio_value,  # TODO: track peak in DB
                "daily_realized_pnl": float(daily_realized or 0),
                "daily_unrealized_pnl": float(daily_unrealized or 0),
                "open_position_count": int(open_count or 0),
                "sector_exposure": {},
            }
    except Exception as e:
        logger.debug(f"Could not load portfolio state for circuit breaker: {e}")
        return {}
