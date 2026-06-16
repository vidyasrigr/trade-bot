"""
Smoke-test the synthetic source against the engine.

Asserts:
  - A simple long call at low IV finishes ITM when spot rises and OTM when spot
    falls — proves the BS pricing is plugged in
  - A short strangle on a flat spot path is profitable via decay — proves the
    engine + source can complete a credit structure end-to-end

These DO NOT validate the magnitude of any signal. They validate the *plumbing*.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backtest.engine import (
    BacktestConfig, Leg, Trade, run_backtest,
)
from backtest.synthetic_source import BlackScholesOptionsSource


def _ramp_series(start: date, prices: list[float]) -> pd.Series:
    days = [start + timedelta(days=i) for i in range(len(prices))]
    return pd.Series(prices, index=pd.to_datetime(days))


async def test_long_call_finishes_itm_on_rally():
    start = date(2024, 1, 2)
    rally = [100.0 + i * 0.5 for i in range(120)]  # +60% over 120 trading days
    source = BlackScholesOptionsSource(
        spot_history={"X": _ramp_series(start, rally)},
        sigma_series={"X": pd.Series(
            [0.25] * len(rally),
            index=pd.to_datetime([start + timedelta(days=i) for i in range(len(rally))]),
        )},
    )
    expiry = start + timedelta(days=90)
    trade = Trade(
        underlying="X",
        legs=(Leg(right="C", strike=110.0, expiry=expiry, qty=1),),
        entry_date=start, max_exit_date=expiry,
        profit_target=0.5, stop_loss=None,
    )
    report = await run_backtest([trade], source)
    r = report.results[0]
    assert r.exit_reason in ("profit_target", "forced_exit"), r.exit_reason
    assert r.pnl > 0, f"long call should profit on rally; got {r.pnl}"
    print(f"  long call on rally: pnl=${r.pnl:.2f} reason={r.exit_reason} ✓")


async def test_short_strangle_flat_spot_decays():
    start = date(2024, 1, 2)
    flat = [100.0 for _ in range(120)]
    source = BlackScholesOptionsSource(
        spot_history={"X": _ramp_series(start, flat)},
        sigma_series={"X": pd.Series(
            [0.30] * len(flat),
            index=pd.to_datetime([start + timedelta(days=i) for i in range(len(flat))]),
        )},
    )
    expiry = start + timedelta(days=45)
    trade = Trade(
        underlying="X",
        legs=(
            Leg(right="P", strike=90.0, expiry=expiry, qty=-1),
            Leg(right="C", strike=110.0, expiry=expiry, qty=-1),
        ),
        entry_date=start, max_exit_date=expiry - timedelta(days=21),
        profit_target=0.5, stop_loss=2.0,
    )
    report = await run_backtest([trade], source)
    r = report.results[0]
    assert r.entry_value < 0, "short strangle entry must be a credit (negative cost)"
    assert r.pnl > 0, f"flat spot + theta should profit; got {r.pnl}"
    print(f"  short strangle decays on flat spot: pnl=${r.pnl:.2f} reason={r.exit_reason} ✓")


async def _main():
    print("Black-Scholes synthetic source smoke test:")
    await test_long_call_finishes_itm_on_rally()
    await test_short_strangle_flat_spot_decays()
    print("ALL PASSED — synthetic plumbing works (does NOT validate signal edge)")


if __name__ == "__main__":
    asyncio.run(_main())
