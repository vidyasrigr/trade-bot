"""
Black-Scholes synthetic options source — interim substitute for ThetaData.

WHY THIS EXISTS:
  ThetaData ($80/mo) is the only honest source of historical option chains. Until
  the subscription + local ThetaTerminal are running, every options backtest in
  this repo would just raise ThetaTerminalNotRunning. That left vrp_harvest.py
  unable to run end-to-end even though every other piece is in place.

WHAT THIS IS:
  An OptionsSource that prices contracts FROM the underlying's daily history —
  spot from yfinance, sigma from rolling realized vol, theoretical mid via
  Black-Scholes, synthetic bid/ask via a fixed half-spread.

WHAT THIS IS *NOT*:
  - A real IV surface. There is no skew, no smirk, no term structure dynamics.
    25-delta puts are priced at the same vol as 25-delta calls.
  - A model of IV crush. Earnings vol-collapse, post-event compression — gone.
  - A model of real bid-ask. Spreads are heuristic, not market quotes.
  - Adequate for a *promotion* decision. Numbers from this source must not
    cross the promotion ladder gate. It's a smoke test, not a validator.

WHEN TO USE:
  - Verify the engine + strategy generator + exit logic plumbing works
  - Sanity-check the *direction* of expected outcomes (e.g. VRP harvest should
    produce positive expectancy with a fat left tail; if it doesn't here either
    the engine is wrong or our HV proxy is broken)
  - Test new strategy code without paying $80/mo while iterating

WHEN TO SWITCH:
  Replace with `backtest.engine.ThetaDataOptionsSource` the moment the
  subscription is live. The interface is identical; one-line change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from loguru import logger
from scipy.stats import norm

from backtest.engine import Leg, OptionQuote


TRADING_DAYS = 252
RISK_FREE_RATE_DEFAULT = 0.045   # rough 2024-26 short rate; safe enough for synth
HALF_SPREAD_BPS = 0.025          # 2.5% half-spread on mid — wider than reality on
                                 # liquid names, tighter than reality on thin ones
MIN_TICK = 0.05


# ---------------------------------------------------------------------------
# Black-Scholes
# ---------------------------------------------------------------------------

def _bs_price(spot: float, strike: float, t: float, sigma: float, r: float,
              right: str) -> float:
    if t <= 0 or sigma <= 0:
        intrinsic = max(0.0, spot - strike) if right == "C" else max(0.0, strike - spot)
        return intrinsic
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if right == "C":
        return spot * norm.cdf(d1) - strike * math.exp(-r * t) * norm.cdf(d2)
    return strike * math.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def _half_spread(mid: float) -> float:
    return max(MIN_TICK / 2, mid * HALF_SPREAD_BPS)


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

@dataclass
class BlackScholesOptionsSource:
    """
    spot_history: {symbol: pd.Series} closes indexed by date.
    Sigma is computed from rolling 20-day realized vol of log returns; you
    can override via `sigma_series` (per-symbol pd.Series) to swap in any
    forecast (GARCH, IV proxy, etc.) without code changes.
    """
    spot_history: dict[str, pd.Series]
    sigma_series: dict[str, pd.Series] = field(default_factory=dict)
    risk_free_rate: float = RISK_FREE_RATE_DEFAULT

    def __post_init__(self) -> None:
        # Pre-compute sigma where not provided
        for sym, closes in self.spot_history.items():
            if sym in self.sigma_series:
                continue
            log_rets = np.log(closes / closes.shift(1))
            self.sigma_series[sym] = log_rets.rolling(20).std() * math.sqrt(TRADING_DAYS)
        # Normalize index to date objects
        for sym in list(self.spot_history.keys()):
            self.spot_history[sym] = self._to_date_indexed(self.spot_history[sym])
            self.sigma_series[sym] = self._to_date_indexed(self.sigma_series[sym])

    @staticmethod
    def _to_date_indexed(series: pd.Series) -> pd.Series:
        if isinstance(series.index, pd.DatetimeIndex):
            series = series.copy()
            series.index = series.index.date
        return series

    # ---- OptionsSource protocol -------------------------------------------

    async def eod_quote(self, underlying: str, leg: Leg, day: date) -> OptionQuote | None:
        spot = self._lookup(self.spot_history.get(underlying), day)
        sigma = self._lookup(self.sigma_series.get(underlying), day)
        if spot is None or sigma is None or sigma <= 0:
            return None
        t = max(0, (leg.expiry - day).days) / 365.0
        if t == 0 and day != leg.expiry:
            return None
        mid = _bs_price(float(spot), float(leg.strike), t, float(sigma),
                         self.risk_free_rate, leg.right.upper())
        if mid <= 0:
            return None
        h = _half_spread(mid)
        bid = max(0.0, mid - h)
        ask = mid + h
        return OptionQuote(bid=round(bid, 2), ask=round(ask, 2))

    async def trading_days(self, underlying: str, start: date, end: date) -> list[date]:
        series = self.spot_history.get(underlying)
        if series is None or series.empty:
            return []
        return [d for d in series.index if start <= d <= end]

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _lookup(series: pd.Series | None, day: date) -> float | None:
        if series is None or series.empty:
            return None
        if day in series.index:
            return float(series.loc[day])
        # Use the most recent prior trading day (no peeking ahead)
        candidates = [d for d in series.index if d <= day]
        if not candidates:
            return None
        return float(series.loc[max(candidates)])


# ---------------------------------------------------------------------------
# Convenience builder
# ---------------------------------------------------------------------------

def from_yfinance(symbols: list[str], period: str = "5y",
                  sigma_floor: float = 0.05) -> BlackScholesOptionsSource:
    """
    Pull closes for `symbols` via yfinance and build the source. sigma is
    floored at `sigma_floor` to prevent zero-vol contracts at the start of a
    series where the rolling std hasn't filled in yet.
    """
    from data.market import get_multi_ohlcv_yfinance
    data = get_multi_ohlcv_yfinance(symbols, period=period)
    spot_history: dict[str, pd.Series] = {}
    sigma_series: dict[str, pd.Series] = {}
    for sym, df in data.items():
        if df is None or df.empty:
            continue
        closes = df["close"].dropna()
        spot_history[sym] = closes
        log_rets = np.log(closes / closes.shift(1))
        sigma = log_rets.rolling(20).std() * math.sqrt(TRADING_DAYS)
        sigma = sigma.fillna(sigma_floor).clip(lower=sigma_floor)
        sigma_series[sym] = sigma
    if not spot_history:
        logger.warning("BlackScholesOptionsSource: no yfinance data returned for any symbol")
    return BlackScholesOptionsSource(spot_history=spot_history, sigma_series=sigma_series)
