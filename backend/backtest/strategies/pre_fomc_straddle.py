"""
Pre-FOMC long straddle on SPY.

Distinct from analysis/fomc_drift.py (which biases existing positions). This
strategy *opens* an SPY straddle 24 hours before each scheduled FOMC release
and closes immediately after, capturing the IV expansion + the documented
24h drift (Lucca & Moench 2015 + replications post-2015 weakening).

Mechanics:
  Entry: 24 hours before FOMC release. ATM straddle. ~5 DTE to capture
         vega without paying excessive theta.
  Exit:  next session close after release (vol crush is fast).

This is one of the *few* options strategies with a clean entry/exit calendar —
no signal interpretation needed. Either it works or it doesn't, easy to backtest.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Iterable

import numpy as np
import pandas as pd
from loguru import logger

from backtest.engine import Leg, Trade


PRE_ENTRY_DAYS = 1
POST_EXIT_DAYS = 1
TARGET_DTE = 5


def _next_friday(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7 or 7)


def generate_pre_fomc_trades(
    spy_closes: pd.Series,
    fomc_dates: Iterable[date],
    *,
    symbol: str = "SPY",
) -> list[Trade]:
    """
    For each scheduled FOMC date in `fomc_dates`, propose:
      buy 1 ATM straddle PRE_ENTRY_DAYS prior, exit POST_EXIT_DAYS after.

    spy_closes is used to round to the nearest tradable $1 strike.
    """
    spy_closes = spy_closes.copy()
    if hasattr(spy_closes.index, "date"):
        spy_closes.index = spy_closes.index.date

    trades: list[Trade] = []
    for fomc in fomc_dates:
        entry = fomc - timedelta(days=PRE_ENTRY_DAYS)
        while entry.weekday() >= 5:
            entry -= timedelta(days=1)
        exit_target = fomc + timedelta(days=POST_EXIT_DAYS)
        while exit_target.weekday() >= 5:
            exit_target += timedelta(days=1)
        if entry not in spy_closes.index:
            continue
        spot = float(spy_closes.loc[entry])
        if spot <= 0:
            continue
        strike = round(spot)  # ATM, $1 grid SPY
        expiry = _next_friday(entry + timedelta(days=TARGET_DTE))
        if expiry <= entry:
            continue
        trades.append(Trade(
            underlying=symbol,
            legs=(
                Leg(right="C", strike=strike, expiry=expiry, qty=1),
                Leg(right="P", strike=strike, expiry=expiry, qty=1),
            ),
            entry_date=entry,
            max_exit_date=exit_target,
            profit_target=None,   # forced exit on the date — let the move play
            stop_loss=None,
            signal="pre_fomc_straddle",
        ))
    return trades
