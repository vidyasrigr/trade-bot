"""
Short-squeeze generator (Drechsler & Drechsler 2014) — DATA BLOCKED for backtest.

The squeeze setup needs short interest as a percent of float, by historical date.
FMP's short-interest endpoint:
  - legacy /v4/short-interest now 403s (FMP Aug-2025 API migration), and
  - it only ever returned the LATEST snapshot, not a point-in-time time series.
There is no free historical short-interest feed available on V's current tier, so
a point-in-time squeeze backtest cannot be constructed without fabricating SI —
which the no-mock-data rule forbids.

This returns no trades so the runner records the signal as BLOCKED (honest), not
as "no edge". Unblock paths (V's budget call): FMP tier with historical SI,
Ortex, or S3 Partners. Tracked in MASTER_REPORT + pc/log.md.
"""

from __future__ import annotations

from datetime import date

from loguru import logger

from backtest.equity_engine import EquityTrade


async def generate_squeeze_trades(
    universe: list[str], start: date, end: date, **_ignored,
) -> list[EquityTrade]:
    logger.warning("squeeze: BLOCKED — no historical short-interest data on current tier")
    return []
