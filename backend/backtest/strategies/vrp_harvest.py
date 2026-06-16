"""
Canonical variance risk premium harvest — short 16Δ strangle, 45 DTE.

Carr & Wu (2009) documented that implied vol exceeds subsequent realized vol
~85-90% of months on the SPX. Per-name VRP is noisier but on liquid optionable
names it remains positive on average. This strategy is the canonical first
backtest because:

  - It must reproduce a *known* result before we trust the engine on novel signals
  - It exercises every code path in backtest/engine.py (multi-leg, credit
    structure, slippage, profit target, time stop)
  - The expected payoff shape (~70% win rate, fat left tail) is well-documented

Entry gate per (symbol, date):
  - IV rank > 50    (use historical-vol rank as fallback until ThetaData wired)
  - VRP z-score > +1 (signal_ranks table from Phase C)
  - DTE = 45 (target)
  - 16Δ on each side (target)

Exits:
  - 50% of credit captured  → profit_target = 0.5
  - 2× credit lost          → stop_loss = 2.0
  - 21 DTE forced exit (managed via max_exit_date)
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from loguru import logger

from backtest.engine import (
    BacktestConfig, BacktestReport, Leg, Trade,
    OptionsSource, run_backtest,
)


@dataclass(frozen=True)
class VrpConfig:
    target_dte_entry: int = 45
    target_dte_exit: int = 21
    target_short_delta: float = 0.16
    iv_rank_min: float = 50.0
    vrp_z_min: float = 1.0
    profit_target: float = 0.5
    stop_loss: float = 2.0


# ---------------------------------------------------------------------------
# Signal preparation
# ---------------------------------------------------------------------------

def _rolling_hv_rank(closes: pd.Series, window: int = 252) -> pd.Series:
    """HV20 percentile rank over `window` trading days — fallback IV rank proxy."""
    log_rets = np.log(closes / closes.shift(1))
    hv20 = log_rets.rolling(20).std() * math.sqrt(252)
    return hv20.rolling(window).apply(
        lambda x: (x.iloc[:-1] < x.iloc[-1]).mean() * 100,
        raw=False,
    )


def _vrp_z_series(closes: pd.Series, window: int = 252) -> pd.Series:
    """
    Proxy VRP-z series: deviation of current HV20 from its trailing-yr mean,
    expressed in std units. Until ThetaData IV is wired this is the best
    backtestable proxy for the cross-section_job VRP-z signal.
    """
    log_rets = np.log(closes / closes.shift(1))
    hv20 = log_rets.rolling(20).std() * math.sqrt(252)
    mean = hv20.rolling(window).mean()
    std = hv20.rolling(window).std()
    return (hv20 - mean) / std


def _next_45_dte_expiry(d: date) -> date:
    """Pick a Friday closest to d + 45 days."""
    target = d + timedelta(days=45)
    days_to_friday = (4 - target.weekday()) % 7
    return target + timedelta(days=days_to_friday)


def _strangle_strikes(spot: float, target_delta: float) -> tuple[float, float]:
    """
    Approximate 16Δ strikes for a strangle. Black-Scholes inversion at sigma=0.30
    gives strikes roughly at ±1 sigma * sqrt(t) for delta ≈ 0.16. We use the
    rule-of-thumb: short_call ≈ spot * 1.10, short_put ≈ spot * 0.90 at 45 DTE
    σ ≈ 30%. The backtest engine will price whatever strike's quotes exist in the
    OptionsSource — this is just the proposal.
    """
    return (
        round(spot * (1.0 - 1.05 * target_delta), 0),  # put
        round(spot * (1.0 + 1.05 * target_delta), 0),  # call
    )


# ---------------------------------------------------------------------------
# Trade generation
# ---------------------------------------------------------------------------

def generate_vrp_trades(
    symbol: str,
    closes: pd.Series,
    config: VrpConfig | None = None,
    *,
    every_n_days: int = 7,
) -> list[Trade]:
    """
    Walk through daily prices; whenever the entry gate fires, emit a short
    strangle Trade for the engine. `every_n_days` prevents stacking >1 position
    per week on the same name.
    """
    config = config or VrpConfig()
    if closes is None or closes.empty or len(closes) < 260:
        return []

    iv_rank = _rolling_hv_rank(closes)
    vrp_z = _vrp_z_series(closes)
    closes = closes.sort_index()

    trades: list[Trade] = []
    last_entry: date | None = None

    for ts, spot in closes.items():
        d = ts.date() if isinstance(ts, pd.Timestamp) else ts
        if pd.isna(spot) or spot <= 0:
            continue
        if pd.isna(iv_rank.get(ts, np.nan)) or pd.isna(vrp_z.get(ts, np.nan)):
            continue
        if iv_rank[ts] < config.iv_rank_min or vrp_z[ts] < config.vrp_z_min:
            continue
        if last_entry is not None and (d - last_entry).days < every_n_days:
            continue

        expiry = _next_45_dte_expiry(d)
        put_strike, call_strike = _strangle_strikes(float(spot), config.target_short_delta)
        max_exit = d + timedelta(days=45 - config.target_dte_exit)

        trades.append(Trade(
            underlying=symbol,
            legs=(
                Leg(right="P", strike=put_strike, expiry=expiry, qty=-1),
                Leg(right="C", strike=call_strike, expiry=expiry, qty=-1),
            ),
            entry_date=d,
            max_exit_date=max_exit,
            profit_target=config.profit_target,
            stop_loss=config.stop_loss,
            signal=f"vrp_harvest_iv{int(iv_rank[ts])}_z{vrp_z[ts]:+.1f}",
        ))
        last_entry = d
    return trades


async def run_vrp_backtest(
    symbols: list[str],
    source: OptionsSource,
    start: date,
    end: date,
    config: VrpConfig | None = None,
    backtest_config: BacktestConfig | None = None,
) -> BacktestReport:
    """End-to-end: pull prices, generate trades per symbol, run the engine."""
    from data.market import get_multi_ohlcv_yfinance
    prices = get_multi_ohlcv_yfinance(symbols, period="5y")

    trades: list[Trade] = []
    for sym, df in prices.items():
        if df is None or df.empty:
            continue
        closes = df["close"].loc[
            (df["close"].index.date >= start) & (df["close"].index.date <= end)
        ] if hasattr(df["close"].index, "date") else df["close"]
        trades.extend(generate_vrp_trades(sym, closes, config))

    if not trades:
        logger.warning("VRP backtest: zero trades generated for the requested window")

    report = await run_backtest(
        trades=trades, source=source, config=backtest_config,
        num_trials=20,  # honest count of strangle-variant trials over the years
    )
    return report
