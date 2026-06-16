"""
Nightly cross-sectional ranking job.

Computes 6 universe-wide signal ranks from Tradier chains + yfinance bars,
persists to signal_ranks (migration 011). Scheduled at 6:30 PM ET in main.py
right after the scanner finishes (so the universe is fresh in cache).

Signals computed:
  1. vrp_z              — IV vs HV20 variance risk premium z-score (1yr lookback)
  2. skew_25d           — 25Δ put IV − 25Δ call IV (Xing-Zhang-Zhao 2010 smirk)
  3. iv_call_put_spread — call IV − put IV at matched delta (Cremers-Weinbaum 2010)
  4. iv_term_slope      — IV(longer dte) − IV(shorter dte) (Vasquez 2015)
  5. momentum_12_1      — 12-month return excluding most recent month, crash-filtered
  6. vrp_level          — IV − HV20 raw level (rank separately from z)
"""

from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
from loguru import logger


SIGNAL_TYPES = (
    "vrp_z",
    "vrp_level",
    "skew_25d",
    "iv_call_put_spread",
    "iv_term_slope",
    "momentum_12_1",
)


# ---------------------------------------------------------------------------
# Per-symbol signal computations
# ---------------------------------------------------------------------------

def _hv20(df: pd.DataFrame) -> float | None:
    if df is None or df.empty or len(df) < 21:
        return None
    rets = np.log(df["close"].values[1:] / df["close"].values[:-1])
    return float(np.std(rets[-20:]) * math.sqrt(252))


def _hv20_series(df: pd.DataFrame, lookback: int = 252) -> list[float]:
    if df is None or df.empty or len(df) < 30:
        return []
    rets = np.log(df["close"].values[1:] / df["close"].values[:-1])
    out: list[float] = []
    for i in range(20, len(rets)):
        out.append(float(np.std(rets[i - 20:i]) * math.sqrt(252)))
    return out[-lookback:]


def _atm_iv(chain: list[dict], spot: float) -> float | None:
    ivs = []
    for c in chain:
        greeks = c.get("greeks") or {}
        iv = greeks.get("mid_iv") or greeks.get("smv_vol")
        strike = c.get("strike")
        if iv and strike and abs(float(strike) - spot) / spot < 0.05:
            ivs.append(float(iv))
    if not ivs:
        return None
    ivs.sort()
    return ivs[len(ivs) // 2]


def _vrp_signals(df: pd.DataFrame, chain: list[dict]) -> tuple[float | None, float | None]:
    """Returns (vrp_z, vrp_level)."""
    if df is None or df.empty:
        return None, None
    spot = float(df["close"].iloc[-1])
    iv = _atm_iv(chain, spot)
    hv = _hv20(df)
    if iv is None or hv is None:
        return None, None
    level = iv - hv
    # Build rolling VRP series for z-score (proxy: rolling HV vs current IV)
    hv_series = _hv20_series(df, lookback=252)
    if len(hv_series) < 30:
        return None, level
    vrp_series = np.array([iv - h for h in hv_series])
    mean, std = float(np.mean(vrp_series[:-1])), float(np.std(vrp_series[:-1]))
    if std <= 0:
        return None, level
    z = (level - mean) / std
    return z, level


def _delta_iv(chain: list[dict], side: str, target_delta: float, tol: float = 0.05) -> float | None:
    """Median IV of contracts within tol of target_delta on the given side ('C'|'P')."""
    side = side.upper()
    matches = []
    for c in chain:
        if c.get("option_type", "").upper() != side:
            continue
        greeks = c.get("greeks") or {}
        d = greeks.get("delta")
        iv = greeks.get("mid_iv") or greeks.get("smv_vol")
        if d is None or iv is None:
            continue
        d_abs = abs(float(d))
        if abs(d_abs - abs(target_delta)) <= tol:
            matches.append(float(iv))
    if not matches:
        return None
    matches.sort()
    return matches[len(matches) // 2]


def _skew_25d(chain: list[dict]) -> float | None:
    """25Δ put IV − 25Δ call IV. Positive = steep put smirk (bearish on average)."""
    put_iv = _delta_iv(chain, "P", -0.25)
    call_iv = _delta_iv(chain, "C", 0.25)
    if put_iv is None or call_iv is None:
        return None
    return put_iv - call_iv


def _iv_call_put_spread(chain: list[dict]) -> float | None:
    """ATM call IV − ATM put IV (Cremers-Weinbaum 2010)."""
    call_iv = _delta_iv(chain, "C", 0.50, tol=0.10)
    put_iv = _delta_iv(chain, "P", -0.50, tol=0.10)
    if call_iv is None or put_iv is None:
        return None
    return call_iv - put_iv


def _iv_term_slope(chain: list[dict]) -> float | None:
    """ATM IV of a longer expiry minus ATM IV of a shorter expiry — flip sign if backwardation."""
    by_exp: dict[str, list[float]] = {}
    for c in chain:
        greeks = c.get("greeks") or {}
        iv = greeks.get("mid_iv") or greeks.get("smv_vol")
        d = greeks.get("delta")
        exp = c.get("expiration_date") or c.get("expiry")
        if iv is None or d is None or exp is None:
            continue
        if abs(abs(float(d)) - 0.50) <= 0.15:
            by_exp.setdefault(str(exp)[:10], []).append(float(iv))
    if len(by_exp) < 2:
        return None
    keys = sorted(by_exp.keys())
    short_iv = float(np.median(by_exp[keys[0]]))
    long_iv = float(np.median(by_exp[keys[-1]]))
    return long_iv - short_iv


def _momentum_12_1(df: pd.DataFrame) -> float | None:
    """
    12-month return excluding the most recent month (Jegadeesh-Titman 1993).
    Returns None when fewer than 252 bars are available.
    """
    if df is None or df.empty or len(df) < 252:
        return None
    p_now = float(df["close"].iloc[-21])  # 21 trading days ago = ~1 month
    p_then = float(df["close"].iloc[-252])
    if p_then <= 0:
        return None
    return p_now / p_then - 1.0


def _spx_crash_mode(spx_df: pd.DataFrame) -> bool:
    """Daniel-Moskowitz: high recent realized vol indicates a momentum-crash regime."""
    if spx_df is None or spx_df.empty or len(spx_df) < 252 * 5:
        return False
    rets = np.log(spx_df["close"].values[1:] / spx_df["close"].values[:-1])
    rolling = pd.Series(rets).rolling(126).std() * math.sqrt(252)
    rolling = rolling.dropna()
    if len(rolling) < 252:
        return False
    threshold = float(np.percentile(rolling.iloc[:-1], 80))
    current = float(rolling.iloc[-1])
    return current > threshold


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def _gather_symbol(symbol: str, tradier) -> dict:
    """Compute every per-symbol signal in one pass. Returns {signal_type: value}."""
    from data.market import get_ohlcv_yfinance
    out: dict[str, float | None] = {k: None for k in SIGNAL_TYPES}
    try:
        df = get_ohlcv_yfinance(symbol, period="2y")
        if df is None or df.empty:
            return {k: v for k, v in out.items() if v is not None}

        try:
            chain = await tradier.get_best_chain(symbol, min_dte=14, max_dte=60)
        except Exception:
            chain = []

        out["momentum_12_1"] = _momentum_12_1(df)
        if chain:
            vrp_z, vrp_level = _vrp_signals(df, chain)
            out["vrp_z"] = vrp_z
            out["vrp_level"] = vrp_level
            out["skew_25d"] = _skew_25d(chain)
            out["iv_call_put_spread"] = _iv_call_put_spread(chain)
            out["iv_term_slope"] = _iv_term_slope(chain)
    except Exception as e:
        logger.debug(f"cross-section gather failed for {symbol}: {e}")
    return {k: v for k, v in out.items() if v is not None}


async def run_cross_section_job(
    symbols: list[str] | None = None,
    max_symbols: int = 800,
    concurrency: int = 16,
) -> dict[str, int]:
    """
    Compute all 6 cross-sectional ranks across the universe and persist to signal_ranks.

    Limits to top `max_symbols` from the dynamic universe to keep wall time reasonable;
    in production, run nightly after the scanner finishes (post-6pm ET) when Tradier
    rate limits are friendliest.

    Returns {signal_type: row_count_written}.
    """
    from data.scanner import get_scan_universe
    from data.tradier import get_tradier
    from scoring.cross_section import rank_values, persist_ranks
    from core.database import AsyncSessionLocal

    if symbols is None:
        symbols = await get_scan_universe()
    symbols = symbols[:max_symbols]
    logger.info(f"cross_section job: computing 6 signals for {len(symbols)} symbols")

    tradier = get_tradier()
    sem = asyncio.Semaphore(concurrency)

    async def _one(sym: str) -> tuple[str, dict[str, float]]:
        async with sem:
            return sym, await _gather_symbol(sym, tradier)

    results = await asyncio.gather(*[_one(s) for s in symbols])

    # Pivot: dict[signal_type, dict[symbol, value]]
    by_signal: dict[str, dict[str, float]] = {k: {} for k in SIGNAL_TYPES}
    for sym, sig_values in results:
        for signal_type, value in sig_values.items():
            by_signal[signal_type][sym] = value

    # Apply momentum crash filter using SPX as the regime gauge.
    try:
        from data.market import get_ohlcv_yfinance
        spx = get_ohlcv_yfinance("SPY", period="5y")
        if _spx_crash_mode(spx):
            logger.warning("momentum_12_1 zeroed — SPX in crash-vol regime (Daniel-Moskowitz)")
            by_signal["momentum_12_1"] = {s: 0.0 for s in by_signal["momentum_12_1"]}
    except Exception as e:
        logger.debug(f"crash filter check failed: {e}")

    today = date.today()
    counts: dict[str, int] = {}
    async with AsyncSessionLocal() as session:
        for signal_type, values in by_signal.items():
            ranks = rank_values(values)
            counts[signal_type] = await persist_ranks(signal_type, ranks, today, session)
    return counts
