"""
Backtest engine self-test on synthetic data — runs with zero external dependencies.

Verifies: profit-target exit, stop-loss exit, forced exit, credit-structure PnL,
slippage and commission accounting. Run: python3 -m backtest.selftest
"""

import asyncio
from datetime import date, timedelta

import pandas as pd

from backtest.engine import (
    BacktestConfig, DataFrameOptionsSource, Leg, Trade, run_backtest,
)

EXPIRY = date(2026, 3, 20)


def _quotes(symbol: str, mids_by_contract: dict[tuple[float, str], list[float]],
            start: date, spread: float = 0.10) -> pd.DataFrame:
    rows = []
    for (strike, right), mids in mids_by_contract.items():
        d = start
        for mid in mids:
            while d.weekday() >= 5:
                d += timedelta(days=1)
            rows.append({
                "underlying": symbol, "quote_date": d, "expiry": EXPIRY,
                "strike": strike, "right": right,
                "bid": round(mid - spread / 2, 2), "ask": round(mid + spread / 2, 2),
            })
            d += timedelta(days=1)
    return pd.DataFrame(rows)


async def test_long_call_profit_target():
    start = date(2026, 3, 2)  # Monday
    df = _quotes("TEST", {(100.0, "C"): [1.00, 1.20, 1.60, 2.00, 2.40]}, start)
    source = DataFrameOptionsSource(df)
    trade = Trade(
        underlying="TEST",
        legs=(Leg(right="C", strike=100.0, expiry=EXPIRY, qty=1),),
        entry_date=start, max_exit_date=start + timedelta(days=10),
        profit_target=0.5, stop_loss=None,
    )
    report = await run_backtest([trade], source, BacktestConfig(slippage=0.5, commission_per_contract=0.65))
    r = report.results[0]
    # Entry: mid 1.00 + 0.5×0.05 slip = 1.025 → +50% target hits at mark ≥ 1.5375 → day3 (1.60)
    assert r.exit_reason == "profit_target", r.exit_reason
    expected_pnl = (1.575 - 1.025) * 100 - 2 * 0.65  # exit exec 1.60 − 0.025 slip
    assert abs(r.pnl - expected_pnl) < 0.01, (r.pnl, expected_pnl)
    print(f"  long-call profit target: exit day {r.exit_date}, pnl=${r.pnl:.2f} ✓")


async def test_long_call_stop_loss():
    start = date(2026, 3, 2)
    df = _quotes("TEST", {(100.0, "C"): [2.00, 1.50, 0.80, 0.40, 0.20]}, start)
    source = DataFrameOptionsSource(df)
    trade = Trade(
        underlying="TEST",
        legs=(Leg(right="C", strike=100.0, expiry=EXPIRY, qty=1),),
        entry_date=start, max_exit_date=start + timedelta(days=10),
        profit_target=0.5, stop_loss=0.5,  # stop at −50% of debit
    )
    r = (await run_backtest([trade], source)).results[0]
    assert r.exit_reason == "stop_loss", r.exit_reason
    assert r.pnl < 0
    print(f"  long-call stop loss: exit day {r.exit_date}, pnl=${r.pnl:.2f} ✓")


async def test_credit_spread_decay():
    """Short 100C / long 105C for a credit; both legs decay → profit target on the credit."""
    start = date(2026, 3, 2)
    df = _quotes("TEST", {
        (100.0, "C"): [2.00, 1.60, 1.20, 0.80, 0.60],
        (105.0, "C"): [0.80, 0.60, 0.45, 0.30, 0.20],
    }, start)
    source = DataFrameOptionsSource(df)
    trade = Trade(
        underlying="TEST",
        legs=(
            Leg(right="C", strike=100.0, expiry=EXPIRY, qty=-1),
            Leg(right="C", strike=105.0, expiry=EXPIRY, qty=1),
        ),
        entry_date=start, max_exit_date=start + timedelta(days=10),
        profit_target=0.5, stop_loss=2.0,
    )
    r = (await run_backtest([trade], source)).results[0]
    assert r.entry_value < 0, "credit structure must have negative entry value"
    assert r.exit_reason == "profit_target", r.exit_reason
    assert r.pnl > 0
    print(f"  credit spread 50% target: exit day {r.exit_date}, pnl=${r.pnl:.2f} ✓")


async def test_forced_exit_and_metrics():
    start = date(2026, 3, 2)
    df = _quotes("TEST", {(100.0, "P"): [1.00, 1.02, 0.98, 1.01, 0.99]}, start)
    source = DataFrameOptionsSource(df)
    trade = Trade(
        underlying="TEST",
        legs=(Leg(right="P", strike=100.0, expiry=EXPIRY, qty=1),),
        entry_date=start, max_exit_date=start + timedelta(days=10),
        profit_target=0.5, stop_loss=0.5,
    )
    report = await run_backtest([trade], source, num_trials=10)
    r = report.results[0]
    assert r.exit_reason == "forced_exit", r.exit_reason
    assert "deflated_sharpe" in report.metrics
    print(f"  forced exit + metrics: pnl=${r.pnl:.2f}, metrics keys={sorted(report.metrics)} ✓")


async def _main():
    print("Backtest engine self-test (synthetic data):")
    await test_long_call_profit_target()
    await test_long_call_stop_loss()
    await test_credit_spread_decay()
    await test_forced_exit_and_metrics()
    print("ALL PASSED")


if __name__ == "__main__":
    asyncio.run(_main())
