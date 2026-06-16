"""
Pre-FOMC drift overlay (Lucca & Moench 2015, "The Pre-FOMC Announcement Drift",
*Journal of Finance*).

The original paper documented sizable equity returns in the 24h before scheduled
FOMC announcements (1994–2011 sample). Post-publication, the effect has weakened
but persists conditional on a low-vol regime (Wachter 2019; replications by AQR,
NBER). We adopt the *gated* version:

  - bullish_bias fires for the 24h window before a scheduled FOMC date
  - ONLY when SPX 20-day realized vol is below the trailing-1yr median
  - Decays to neutral outside the window

Output:
  catalyst_flags["pre_fomc_window"] = bool
  catalyst_flags["pre_fomc_bias"]    = "bullish" | "neutral"
  catalyst_flags["pre_fomc_eta_h"]   = hours until FOMC

Consumed by agents/graph.py (passed through analysis.catalyst_flags) and the
nightly briefing (Phase F).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger


PRE_FOMC_WINDOW_HOURS = 24


def _spx_realized_vol_band(df: pd.DataFrame, window: int = 20) -> tuple[float, float] | None:
    """Returns (current_rv, trailing_yr_median) or None if insufficient data."""
    if df is None or df.empty or len(df) < 252 + window:
        return None
    rets = np.log(df["close"].values[1:] / df["close"].values[:-1])
    rolling = pd.Series(rets).rolling(window).std() * math.sqrt(252)
    rolling = rolling.dropna()
    if len(rolling) < 252:
        return None
    current = float(rolling.iloc[-1])
    median = float(np.median(rolling.iloc[-252:-1]))
    return current, median


async def _next_fomc(today: date | None = None) -> date | None:
    from analysis.calendar import get_fomc_dates
    today = today or date.today()
    dates = await get_fomc_dates()
    upcoming = sorted(d for d in dates if d >= today)
    return upcoming[0] if upcoming else None


async def compute_pre_fomc_state(now: datetime | None = None) -> dict:
    """
    Returns the canonical state dict consumed by catalyst_flags. Always returns a
    valid dict — missing data => pre_fomc_window=False, bias='neutral'.
    """
    from data.market import get_ohlcv_yfinance

    now = now or datetime.utcnow()
    today = now.date()
    next_meeting = await _next_fomc(today)
    out = {
        "pre_fomc_window": False,
        "pre_fomc_bias": "neutral",
        "pre_fomc_eta_h": None,
        "pre_fomc_gate_passed": False,
        "pre_fomc_next_meeting": next_meeting.isoformat() if next_meeting else None,
    }
    if next_meeting is None:
        return out

    # FOMC statements are released at 14:00 ET. The 24h window opens at 14:00 ET
    # the prior US business day. We treat the meeting day at 18:00 UTC as the close.
    meeting_dt = datetime.combine(next_meeting, datetime.min.time()).replace(hour=18)
    eta = meeting_dt - now
    eta_h = eta.total_seconds() / 3600
    out["pre_fomc_eta_h"] = round(eta_h, 1)
    if not (0 < eta_h <= PRE_FOMC_WINDOW_HOURS):
        return out
    out["pre_fomc_window"] = True

    # Vol-regime gate (Lucca-Moench): only fire bullish bias when SPX RV is below
    # its trailing-1yr median.
    try:
        spx = get_ohlcv_yfinance("SPY", period="2y")
        band = _spx_realized_vol_band(spx)
    except Exception as e:
        logger.debug(f"pre_fomc: SPX RV fetch failed: {e}")
        band = None

    if band is None:
        # Insufficient data — surface the window but don't claim a bias.
        return out
    current_rv, median_rv = band
    if current_rv <= median_rv:
        out["pre_fomc_gate_passed"] = True
        out["pre_fomc_bias"] = "bullish"
    return out


async def apply_pre_fomc_overlay(catalyst_flags: dict) -> dict:
    """Merge the pre-FOMC state into an existing catalyst_flags dict in place."""
    state = await compute_pre_fomc_state()
    catalyst_flags.update(state)
    return catalyst_flags
