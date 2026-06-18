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
    """
    Third Friday of the month ~45 days out — i.e. the standard monthly expiry.

    Earlier this rounded to the nearest Friday, but weekly expiries didn't exist
    historically for many liquid names (IWM, sector ETFs, mid-caps), so those
    chains 404 with "no_data" and the trade silently drops. Monthly (3rd-Friday)
    contracts have existed for every optionable name for decades, so snapping to
    them maximizes real-chain hit rate in the backtest.
    """
    target = d + timedelta(days=45)
    first = target.replace(day=1)
    offset = (4 - first.weekday()) % 7       # days from the 1st to the 1st Friday
    return first + timedelta(days=offset + 14)  # +2 weeks → 3rd Friday


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

@dataclass(frozen=True)
class VrpCandidate:
    """A date on which the VRP entry gate fired — expiry/strikes not yet resolved."""
    symbol: str
    entry_date: date
    spot: float
    signal: str


def generate_vrp_candidates(
    symbol: str,
    closes: pd.Series,
    config: VrpConfig | None = None,
    *,
    every_n_days: int = 7,
    entry_start: date | None = None,
    entry_end: date | None = None,
) -> list[VrpCandidate]:
    """
    Walk daily prices; emit a VrpCandidate every time the entry gate fires.

    Indicators (`iv_rank`, `vrp_z`) are computed over the FULL `closes` series so
    the rolling warmup uses pre-window history (legitimate point-in-time: past
    data informing the current indicator). `entry_start`/`entry_end` then gate
    which dates may OPEN a position — so the window isn't eaten by ~1yr warmup.

    This is the single source of truth for the entry gate. Both the offline
    `generate_vrp_trades` (formula strikes) and the live `run_vrp_backtest`
    (real-chain resolved strikes) build on it.
    """
    config = config or VrpConfig()
    if closes is None or closes.empty or len(closes) < 260:
        return []

    iv_rank = _rolling_hv_rank(closes)
    vrp_z = _vrp_z_series(closes)
    closes = closes.sort_index()

    out: list[VrpCandidate] = []
    last_entry: date | None = None
    for ts, spot in closes.items():
        d = ts.date() if isinstance(ts, pd.Timestamp) else ts
        if entry_start is not None and d < entry_start:
            continue
        if entry_end is not None and d > entry_end:
            continue
        if pd.isna(spot) or spot <= 0:
            continue
        if pd.isna(iv_rank.get(ts, np.nan)) or pd.isna(vrp_z.get(ts, np.nan)):
            continue
        if iv_rank[ts] < config.iv_rank_min or vrp_z[ts] < config.vrp_z_min:
            continue
        if last_entry is not None and (d - last_entry).days < every_n_days:
            continue
        out.append(VrpCandidate(
            symbol=symbol, entry_date=d, spot=float(spot),
            signal=f"vrp_harvest_iv{int(iv_rank[ts])}_z{vrp_z[ts]:+.1f}",
        ))
        last_entry = d
    return out


def generate_vrp_trades(
    symbol: str,
    closes: pd.Series,
    config: VrpConfig | None = None,
    *,
    every_n_days: int = 7,
    entry_start: date | None = None,
    entry_end: date | None = None,
) -> list[Trade]:
    """
    Offline trade generation with FORMULA expiry/strikes (3rd-Friday monthly,
    delta-rule strikes). Used by tests and the synthetic-source path where exact
    listed contracts don't matter. The live MarketData path uses
    `run_vrp_backtest`, which resolves expiry + strikes against the real chain.
    """
    config = config or VrpConfig()
    candidates = generate_vrp_candidates(
        symbol, closes, config, every_n_days=every_n_days,
        entry_start=entry_start, entry_end=entry_end,
    )
    trades: list[Trade] = []
    for c in candidates:
        expiry = _next_45_dte_expiry(c.entry_date)
        put_strike, call_strike = _strangle_strikes(c.spot, config.target_short_delta)
        trades.append(Trade(
            underlying=symbol,
            legs=(
                Leg(right="P", strike=put_strike, expiry=expiry, qty=-1),
                Leg(right="C", strike=call_strike, expiry=expiry, qty=-1),
            ),
            entry_date=c.entry_date,
            max_exit_date=c.entry_date + timedelta(days=45 - config.target_dte_exit),
            profit_target=config.profit_target,
            stop_loss=config.stop_loss,
            signal=c.signal,
        ))
    return trades


async def _resolve_candidate(
    source, candidate: VrpCandidate, config: VrpConfig,
) -> Trade | None:
    """
    Turn a gate-fired candidate into a real Trade by snapping expiry + strikes to
    what MarketData actually listed on the entry date. Returns None when no real
    chain exists (the trade is legitimately undatable, not silently mispriced).

    Resolves BOTH handoff issues #3 (strike mismatch) and #4 (non-existent
    expiry — weeklies that never existed, 3rd-Fridays shifted by holidays).
    """
    client = getattr(source, "client", None)
    if client is None:
        return None
    sym, d, spot = candidate.symbol, candidate.entry_date, candidate.spot
    target = d + timedelta(days=config.target_dte_entry)

    # 1. Resolve expiry. Use the disk-cached FULL expirations list (faithful: same
    #    nearest-target selection as a live API call, but free after the first
    #    populate — this is the credit-leak fix). Fall back to the chain-cache dir
    #    (banked expiries only) when the expirations API is unavailable, e.g. the
    #    daily limit is hit. Both paths cost ZERO credits on a re-run.
    candidate_expiries: list = []
    if hasattr(source, "expirations"):
        exps = await source.expirations(sym, d)
        candidate_expiries = [date.fromisoformat(e[:10]) for e in exps]
    if not candidate_expiries and hasattr(source, "cached_expiries"):
        candidate_expiries = source.cached_expiries(sym, d)
    if not candidate_expiries:
        try:
            exps = await client.get_expirations(sym, as_of=d.isoformat())
        except Exception:
            return None
        candidate_expiries = [date.fromisoformat(e[:10]) for e in exps]
    if not candidate_expiries:
        return None
    expiry = min(candidate_expiries, key=lambda e: abs((e - target).days))
    # Guard against a degenerate nearest-expiry (already expired / 0 DTE).
    if (expiry - d).days < config.target_dte_exit:
        return None

    # 2. Snap strikes to the real chain on the entry date (cached load).
    chain = await source._load_chain(sym, expiry, d)
    if not chain:
        return None
    put_strikes = sorted(s for (s, r) in chain if r == "P")
    call_strikes = sorted(s for (s, r) in chain if r == "C")
    if not put_strikes or not call_strikes:
        return None
    put_t, call_t = _strangle_strikes(spot, config.target_short_delta)
    put_strike = min(put_strikes, key=lambda s: abs(s - put_t))
    call_strike = min(call_strikes, key=lambda s: abs(s - call_t))

    return Trade(
        underlying=sym,
        legs=(
            Leg(right="P", strike=put_strike, expiry=expiry, qty=-1),
            Leg(right="C", strike=call_strike, expiry=expiry, qty=-1),
        ),
        entry_date=d,
        max_exit_date=d + timedelta(days=config.target_dte_entry - config.target_dte_exit),
        profit_target=config.profit_target,
        stop_loss=config.stop_loss,
        signal=candidate.signal,
    )


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
    # 10y of history so indicator warmup uses pre-window bars; entry dates are
    # gated to [start, end] inside generate_vrp_trades (true PIT, no truncation).
    # NB: period="max" makes yfinance's *bulk* download flaky (1927 start →
    # spurious "possibly delisted" empties); 10y is a sane bounded range that
    # still gives >1yr warmup before any 2021+ backtest window.
    prices = get_multi_ohlcv_yfinance(symbols, period="10y")

    config = config or VrpConfig()

    # 1. Gate-fired candidates per symbol (sync, cheap).
    candidates: list[VrpCandidate] = []
    for sym, df in prices.items():
        if df is None or df.empty:
            continue
        candidates.extend(generate_vrp_candidates(
            sym, df["close"], config, entry_start=start, entry_end=end,
        ))
    logger.info(f"VRP backtest: {len(candidates)} gate-fired candidates across {len(symbols)} names")

    # 2. Resolve each candidate's real expiry + strikes against MarketData
    #    (bounded concurrency to stay polite to the API). Drops candidates with
    #    no real chain — those are honestly unpriceable, not silently mispriced.
    resolve_sem = asyncio.Semaphore(6)

    async def _resolve(c: VrpCandidate) -> Trade | None:
        async with resolve_sem:
            try:
                return await _resolve_candidate(source, c, config)
            except Exception as e:
                logger.debug(f"resolve failed {c.symbol} {c.entry_date}: {e}")
                return None

    resolved = await asyncio.gather(*[_resolve(c) for c in candidates])
    trades: list[Trade] = [t for t in resolved if t is not None]
    logger.info(
        f"VRP backtest: {len(trades)}/{len(candidates)} candidates resolved to real "
        f"contracts ({len(candidates) - len(trades)} dropped — no listed chain)"
    )

    if not trades:
        logger.warning("VRP backtest: zero trades resolved for the requested window")

    report = await run_backtest(
        trades=trades, source=source, config=backtest_config,
        num_trials=20,  # honest count of strangle-variant trials over the years
    )
    return report
