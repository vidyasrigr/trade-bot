"""
Options backtest engine — multi-leg positions priced from historical EOD quotes.

Fills: mid ± slippage × half-spread (buys pay up, sells receive less) + commission
per contract per side. Exits: profit target / stop loss (as fractions of the
entry basis), expiry, or forced exit at max_exit_date.

Data sources implement OptionsSource (async):
  - DataFrameOptionsSource: long DataFrame (offline files, tests)
  - ThetaDataOptionsSource: live pull from local ThetaTerminal (data/thetadata.py)

No historical chains → no backtest. This engine never invents prices.

ASYNC: all source methods are async because production source (ThetaData) must
not block the event loop on per-contract HTTP requests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd
from loguru import logger

CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class OptionQuote:
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class Leg:
    right: str          # "C" | "P"
    strike: float
    expiry: date
    qty: int            # +N long, -N short (contracts)


@dataclass(frozen=True)
class Trade:
    underlying: str
    legs: tuple[Leg, ...]
    entry_date: date
    max_exit_date: date
    profit_target: float | None = 0.5   # fraction of entry basis, e.g. 0.5 = +50%
    stop_loss: float | None = 2.0       # fraction of entry basis lost, e.g. 2.0 = -200%
    signal: str = ""                    # provenance: which signal generated this


@dataclass
class TradeResult:
    trade: Trade
    entry_date: date
    exit_date: date
    exit_reason: str        # profit_target | stop_loss | forced_exit | data_end
    entry_value: float      # signed structure cost per share (debit > 0, credit < 0)
    exit_value: float
    pnl: float              # dollars, after slippage + commissions
    days_held: int
    marks: dict = field(default_factory=dict)  # day -> unrealized $ while open (MTM)


@dataclass
class BacktestConfig:
    slippage: float = 0.5                  # fraction of half-spread paid beyond mid
    commission_per_contract: float = 0.65  # per contract per side
    starting_equity: float = 100_000.0


@dataclass
class BacktestReport:
    results: list[TradeResult]
    equity_curve: pd.Series          # indexed by date
    metrics: dict = field(default_factory=dict)


class OptionsSource(Protocol):
    async def eod_quote(self, underlying: str, leg: "Leg", day: date) -> OptionQuote | None: ...
    async def trading_days(self, underlying: str, start: date, end: date) -> list[date]: ...


class DataFrameOptionsSource:
    """
    Long-format EOD quotes: columns
    [underlying, quote_date, expiry, strike, right, bid, ask].
    Load from parquet/CSV for offline testing and validation runs.

    Methods are async to match the OptionsSource protocol — the lookups are
    in-memory so they return immediately, but the interface uniformity matters.
    """

    def __init__(self, df: pd.DataFrame):
        df = df.copy()
        df["quote_date"] = pd.to_datetime(df["quote_date"]).dt.date
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
        df["right"] = df["right"].str.upper()
        self._idx = df.set_index(
            ["underlying", "quote_date", "expiry", "strike", "right"]
        ).sort_index()
        self._days: dict[str, list[date]] = {
            und: sorted(g["quote_date"].unique())
            for und, g in df.groupby("underlying")
        }

    @classmethod
    def from_parquet(cls, path: str) -> "DataFrameOptionsSource":
        return cls(pd.read_parquet(path))

    async def eod_quote(self, underlying: str, leg: Leg, day: date) -> OptionQuote | None:
        key = (underlying, day, leg.expiry, float(leg.strike), leg.right.upper())
        try:
            row = self._idx.loc[key]
        except KeyError:
            return None
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        bid, ask = float(row["bid"]), float(row["ask"])
        if ask <= 0:
            return None
        return OptionQuote(bid=max(0.0, bid), ask=ask)

    async def trading_days(self, underlying: str, start: date, end: date) -> list[date]:
        return [d for d in self._days.get(underlying, []) if start <= d <= end]


class ThetaDataOptionsSource:
    """
    Adapter over data/thetadata.py with per-contract caching.

    Per-contract series are fetched once on first reference (lazily) and reused
    across every (day) call for the same Leg. Concurrent first-touch is guarded
    by a per-key asyncio.Lock so we never duplicate HTTP calls under gather().
    """

    def __init__(self, client=None):
        if client is None:
            from data.thetadata import get_thetadata
            client = get_thetadata()
        self.client = client
        self._cache: dict[tuple, pd.DataFrame] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}

    async def _series(self, underlying: str, leg: Leg) -> pd.DataFrame:
        key = (underlying, leg.expiry, leg.strike, leg.right.upper())
        if key in self._cache:
            return self._cache[key]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key not in self._cache:
                self._cache[key] = await self.client.option_eod(
                    root=underlying, exp=leg.expiry, strike=leg.strike,
                    right=leg.right, start=date(2018, 1, 1), end=leg.expiry,
                )
        return self._cache[key]

    async def eod_quote(self, underlying: str, leg: Leg, day: date) -> OptionQuote | None:
        df = await self._series(underlying, leg)
        if df.empty or "quote_date" not in df.columns:
            return None
        row = df[df["quote_date"] == day]
        if row.empty:
            return None
        r = row.iloc[0]
        bid = float(r.get("bid", 0) or 0)
        ask = float(r.get("ask", 0) or 0)
        if ask <= 0:
            return None
        return OptionQuote(bid=max(0.0, bid), ask=ask)

    async def trading_days(self, underlying: str, start: date, end: date) -> list[date]:
        # Use the densest cached series as the calendar
        best: list[date] = []
        for df in self._cache.values():
            if "quote_date" in df.columns and len(df) > len(best):
                best = sorted(df["quote_date"].tolist())
        return [d for d in best if start <= d <= end]


# ---------------------------------------------------------------------------
# Pricing helpers
# ---------------------------------------------------------------------------

def _exec_price(q: OptionQuote, qty: int, slippage: float, closing: bool) -> float:
    """Buys pay mid + slip×half-spread; sells receive mid − slip×half-spread."""
    half_spread = max(0.0, (q.ask - q.bid) / 2.0)
    buying = (qty > 0) != closing
    return q.mid + half_spread * slippage * (1.0 if buying else -1.0)


async def _structure_exec_value(source: OptionsSource, trade: Trade, day: date,
                                 slippage: float, closing: bool) -> float | None:
    total = 0.0
    quotes = await asyncio.gather(*[
        source.eod_quote(trade.underlying, leg, day) for leg in trade.legs
    ])
    for leg, q in zip(trade.legs, quotes):
        if q is None:
            return None
        total += leg.qty * _exec_price(q, leg.qty, slippage, closing)
    return total


async def _structure_mark(source: OptionsSource, trade: Trade, day: date) -> float | None:
    quotes = await asyncio.gather(*[
        source.eod_quote(trade.underlying, leg, day) for leg in trade.legs
    ])
    total = 0.0
    for leg, q in zip(trade.legs, quotes):
        if q is None:
            return None
        total += leg.qty * q.mid
    return total


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

async def simulate_trade(trade: Trade, source: OptionsSource,
                          config: BacktestConfig) -> TradeResult | None:
    days = await source.trading_days(trade.underlying, trade.entry_date, trade.max_exit_date)
    if not days:
        logger.debug(f"No trading days for {trade.underlying} {trade.entry_date}")
        return None

    entry_value = await _structure_exec_value(source, trade, days[0], config.slippage, closing=False)
    if entry_value is None:
        return None
    basis = abs(entry_value)
    if basis <= 0:
        return None

    n_contracts = sum(abs(leg.qty) for leg in trade.legs)
    commissions = config.commission_per_contract * n_contracts * 2  # entry + exit

    last_mark = entry_value
    last_mark_day = days[0]
    exit_reason = "forced_exit"
    exit_day = days[-1]
    # Daily unrealized PnL ($) while the trade is open (P0 Stage 3.0). Entry day
    # is flat. run_backtest aggregates these across trades into a mark-to-market
    # equity curve so intratrade drawdown is no longer invisible.
    marks: dict[date, float] = {days[0]: 0.0}

    for day in days[1:]:
        mark = await _structure_mark(source, trade, day)
        if mark is None:
            continue
        last_mark, last_mark_day = mark, day
        unrealized = mark - entry_value
        marks[day] = round(unrealized * CONTRACT_MULTIPLIER, 2)
        if trade.profit_target is not None and unrealized >= trade.profit_target * basis:
            exit_reason, exit_day = "profit_target", day
            break
        if trade.stop_loss is not None and unrealized <= -trade.stop_loss * basis:
            exit_reason, exit_day = "stop_loss", day
            break

    exit_value = await _structure_exec_value(source, trade, exit_day, config.slippage, closing=True)
    if exit_value is None:
        # Quotes vanished near the end (delisting/expiry gap) — close at last mark
        exit_value, exit_day, exit_reason = last_mark, last_mark_day, "data_end"

    pnl = (exit_value - entry_value) * CONTRACT_MULTIPLIER - commissions
    # Drop marks at/after the exit day — those days carry realized PnL instead.
    marks = {d: v for d, v in marks.items() if d < exit_day}
    return TradeResult(
        trade=trade,
        entry_date=days[0],
        exit_date=exit_day,
        exit_reason=exit_reason,
        entry_value=round(entry_value, 4),
        exit_value=round(exit_value, 4),
        pnl=round(pnl, 2),
        days_held=(exit_day - days[0]).days,
        marks=marks,
    )


async def run_backtest(trades: list[Trade], source: OptionsSource,
                        config: BacktestConfig | None = None,
                        num_trials: int = 1,
                        concurrency: int = 8) -> BacktestReport:
    """
    num_trials: the honest count of strategy variants you tried before this one —
    feeds the deflated Sharpe so multiple testing is penalized, not hidden.

    concurrency: how many trades to simulate in parallel. Each contract's
    historical series is cached per source, so parallelism mostly matters
    on the cold-cache leading edge of a batch.
    """
    from backtest.metrics import summarize

    config = config or BacktestConfig()
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _run(trade: Trade) -> TradeResult | None:
        async with sem:
            try:
                return await simulate_trade(trade, source, config)
            except Exception as e:
                logger.warning(f"Backtest trade failed ({trade.underlying} {trade.entry_date}): {e}")
                return None

    sim_results = await asyncio.gather(*[_run(t) for t in trades])
    results: list[TradeResult] = [r for r in sim_results if r is not None]

    if not results:
        return BacktestReport(results=[], equity_curve=pd.Series(dtype=float),
                              metrics={"num_trades": 0})

    # Daily equity curve from realized PnL on exit dates
    pnl_by_day: dict[date, float] = {}
    for r in results:
        pnl_by_day[r.exit_date] = pnl_by_day.get(r.exit_date, 0.0) + r.pnl
    all_days = sorted(pnl_by_day)
    equity_vals, eq = [], config.starting_equity
    for d in all_days:
        eq += pnl_by_day[d]
        equity_vals.append(eq)
    equity = pd.Series(equity_vals, index=pd.to_datetime(all_days))
    daily_returns = equity.pct_change().dropna().to_numpy() if len(equity) > 1 else np.array([])

    metrics = summarize(
        trade_pnls=[r.pnl for r in results],
        equity=equity.to_numpy(),
        daily_returns=daily_returns,
        num_trials=num_trials,
    )

    # Daily mark-to-market equity curve (P0 Stage 3.0). Portfolio value on each
    # day = starting + sum over trades of (realized pnl if closed, else current
    # unrealized mark). This exposes intratrade drawdown the realized-exit curve
    # hides — e.g. a short strangle deeply underwater before it recovers. DSR /
    # Sharpe stay on the realized curve (comparable to prior reports); only the
    # drawdown is replaced with the honest MTM figure.
    from backtest.metrics import max_drawdown as _max_dd
    mark_days = sorted({d for r in results for d in r.marks} | {r.exit_date for r in results})
    mtm_vals = []
    for d in mark_days:
        total = 0.0
        for r in results:
            if d >= r.exit_date:
                total += r.pnl
            elif d in r.marks:
                total += r.marks[d]
        mtm_vals.append(config.starting_equity + total)
    mtm_equity = pd.Series(mtm_vals, index=pd.to_datetime(mark_days))
    if len(mtm_equity) > 1:
        metrics["max_drawdown_realized"] = metrics.get("max_drawdown")
        metrics["max_drawdown"] = float(_max_dd(mtm_equity.to_numpy()))
        metrics["equity_curve_method"] = "daily_mtm"

    return BacktestReport(results=results, equity_curve=mtm_equity, metrics=metrics)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

async def save_backtest_run(report: BacktestReport, strategy: str, symbol: str,
                            start_date: date, end_date: date, params: dict) -> int | None:
    """Persist a run to backtest_runs (migration 007) for /api/backtest/results."""
    import orjson
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    m = report.metrics
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            INSERT INTO backtest_runs
                (strategy, symbol, start_date, end_date, num_trades, win_rate,
                 total_pnl, sharpe, deflated_sharpe, max_drawdown, params)
            VALUES
                (:strategy, :symbol, :start, :end, :n, :wr, :pnl, :sharpe, :dsr, :mdd, :params::jsonb)
            RETURNING id
        """), {
            "strategy": strategy, "symbol": symbol, "start": start_date, "end": end_date,
            "n": m.get("num_trades", 0), "wr": m.get("win_rate", 0.0),
            "pnl": m.get("total_pnl", 0.0), "sharpe": m.get("sharpe", 0.0),
            "dsr": m.get("deflated_sharpe", 0.0), "mdd": m.get("max_drawdown", 0.0),
            "params": orjson.dumps(params).decode(),
        })
        run_id = result.fetchone()[0]
        await session.commit()
    return run_id
