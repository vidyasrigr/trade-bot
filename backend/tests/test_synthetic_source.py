"""Black-Scholes synthetic options source — engine plumbing smoke test."""

import asyncio
from datetime import date, timedelta

import pandas as pd

from backtest.engine import BacktestConfig, Leg, Trade, run_backtest
from backtest.synthetic_source import BlackScholesOptionsSource


def _ramp_series(start: date, prices: list[float]) -> pd.Series:
    days = [start + timedelta(days=i) for i in range(len(prices))]
    return pd.Series(prices, index=pd.to_datetime(days))


def test_long_call_profits_on_rally():
    start = date(2024, 1, 2)
    rally = [100.0 + i * 0.5 for i in range(120)]
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
    report = asyncio.run(run_backtest([trade], source))
    assert report.results, "no result"
    r = report.results[0]
    assert r.pnl > 0


def test_short_strangle_decays_on_flat_spot():
    start = date(2024, 1, 2)
    flat = [100.0] * 120
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
    report = asyncio.run(run_backtest([trade], source))
    r = report.results[0]
    assert r.entry_value < 0  # credit
    assert r.pnl > 0           # decay should profit


def test_underlying_with_no_history_returns_no_quote():
    source = BlackScholesOptionsSource(spot_history={})
    expiry = date(2024, 3, 15)

    async def _check():
        return await source.eod_quote("MISSING",
                                       Leg(right="C", strike=100, expiry=expiry, qty=1),
                                       date(2024, 1, 5))

    assert asyncio.run(_check()) is None
