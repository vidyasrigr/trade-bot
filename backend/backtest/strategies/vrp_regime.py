"""
Regime-gated VRP harvest — the tail fix that the iron condor and tighter stops
both failed to deliver.

Findings that motivate this (pc/journal 2026-06-17):
  - Naked VRP edge is real (train DSR 0.90 / wf 0.31) but carries a ~51% wf
    drawdown.
  - Iron-condor wings at EVERY distance (1.5-3.0 sigma) turn it net-negative.
  - Tighter stops (1.0x/1.5x) don't help: identical trade count and the drawdown
    even worsens slightly -> the EOD stop never binds; the damage is concentrated
    in correlated vol-spike days. And % drawdown is scale-invariant, so smaller
    size can't fix it either.
  - The remaining lever is ENTRY TIMING: don't open new short vol into an
    accelerating-vol regime.

Filter (point-in-time, market-level):
  Using SPY daily closes up to (and including) the entry date, compute annualized
  realized vol over 5d and 20d. "Stress" = rv5 > stress_ratio * rv20 (vol
  accelerating). Candidates whose entry date is in a stress regime are dropped.
  All data used is <= entry date, so no lookahead.

This is a research-backed strategy VARIATION (entry filter), not a new signal. It
is POST-HOC: added after seeing the drawdown problem in the first sweep. Flagged
as such in the journal and report.
"""

from __future__ import annotations

import asyncio
from datetime import date

import numpy as np
import pandas as pd
from loguru import logger

from backtest.engine import BacktestConfig, BacktestReport, Trade, OptionsSource, run_backtest
from backtest.strategies.vrp_harvest import (
    VrpConfig, VrpCandidate, generate_vrp_candidates, _resolve_candidate,
)


def _stress_dates(spy_close: pd.Series, stress_ratio: float = 1.3) -> set[date]:
    """Dates where SPY 5d realized vol exceeds stress_ratio x its 20d realized vol."""
    lr = np.log(spy_close / spy_close.shift(1))
    rv5 = lr.rolling(5).std() * np.sqrt(252)
    rv20 = lr.rolling(20).std() * np.sqrt(252)
    mask = rv5 > (stress_ratio * rv20)
    out: set[date] = set()
    for ts, flag in mask.items():
        if bool(flag):
            d = ts.date() if isinstance(ts, pd.Timestamp) else ts
            out.add(d)
    return out


async def run_vrp_regime_backtest(
    symbols: list[str],
    source: OptionsSource,
    start: date,
    end: date,
    config: VrpConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    *, stress_ratio: float = 1.3,
) -> BacktestReport:
    """Naked VRP strangle, but skip entries on market vol-acceleration days."""
    from data.market import get_multi_ohlcv_yfinance
    prices = get_multi_ohlcv_yfinance(list(dict.fromkeys(symbols + ["SPY"])), period="10y")
    config = config or VrpConfig()

    spy = prices.get("SPY")
    stress = _stress_dates(spy["close"], stress_ratio) if spy is not None and not spy.empty else set()

    candidates: list[VrpCandidate] = []
    for sym in symbols:
        df = prices.get(sym)
        if df is None or df.empty:
            continue
        for c in generate_vrp_candidates(sym, df["close"], config,
                                         entry_start=start, entry_end=end):
            if c.entry_date in stress:
                continue  # skip entries into an accelerating-vol regime
            candidates.append(c)
    logger.info(f"VRP-regime: {len(candidates)} candidates after dropping "
                f"{len(stress)} stress days (ratio {stress_ratio})")

    sem = asyncio.Semaphore(6)

    async def _resolve(c: VrpCandidate) -> Trade | None:
        async with sem:
            try:
                return await _resolve_candidate(source, c, config)
            except Exception:
                return None

    resolved = await asyncio.gather(*[_resolve(c) for c in candidates])
    trades = [t for t in resolved if t is not None]
    logger.info(f"VRP-regime: {len(trades)}/{len(candidates)} resolved to real contracts")

    return await run_backtest(trades=trades, source=source,
                              config=backtest_config, num_trials=20)
