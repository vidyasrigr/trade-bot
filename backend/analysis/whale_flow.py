"""
Whale flow detector — Pan & Poteshman (2006) implementation, DIY on MarketData.

Research backing:
  Pan & Poteshman (2006, *RFS*) — open-buy put/call volume ratios predict
  stock returns, strongest in names with high information asymmetry. They
  found that on days where institutions opened large put positions, the
  underlying stock subsequently underperformed by ~40 bps over 5 days; the
  reverse for call open-buys. The edge is in the *informed* flow.

What we compute per symbol (cheap, from MarketData chains alone):
  - sweep_score:    sum of premium-weighted volume on contracts where
                    volume > 2× open interest (proxy for "new aggressive
                    positions" since vol >> OI means the activity isn't
                    closing existing positions)
  - directional_imbalance: (call_sweep_$ − put_sweep_$) / total_sweep_$
                            in [-1, +1]. Positive = bullish whale lean.
  - whale_signal:   max(0, sweep_score) × abs(directional_imbalance)
                    — high only when premium is large AND directionally lopsided

Output:
  - Persisted per-symbol to whale_flow_signals (migration 016)
  - Cross-section ranked nightly into signal_ranks (type='whale_flow')
  - Surfaced as a tail signal in weighted._detect_tail_alignment

This is the DIY path. Replace with Unusual Whales' cleaned sweep feed (~$48/mo)
when the budget allows — the interface stays the same, only _fetch_chain_for_flow
changes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from loguru import logger


PREMIUM_FLOOR = 25_000           # ignore contracts with < $25k premium (noise)
VOL_OI_MULT = 2.0                # vol > 2x OI = aggressive new positioning
MIN_OI_FOR_RATIO = 10            # tiny-OI contracts make the ratio meaningless
DEEP_OTM_DELTA = 0.10            # ignore deep OTM lottery tickets (Boyer-Vorkink)


@dataclass
class WhaleFlow:
    symbol: str
    sweep_score: float            # premium-weighted; raw dollars of new flow
    call_sweep_usd: float
    put_sweep_usd: float
    directional_imbalance: float  # in [-1, +1]
    whale_signal: float           # the headline number consumed downstream
    sample_contracts: int


def _classify_chain(chain: list[dict]) -> WhaleFlow | None:
    """
    Pure function: given a MarketData/Tradier-shaped chain, return the
    aggregated whale-flow metrics. Easy to unit-test without I/O.
    """
    if not chain:
        return None
    call_usd, put_usd, sampled = 0.0, 0.0, 0
    for c in chain:
        vol = int(c.get("volume") or 0)
        oi = int(c.get("open_interest") or 0)
        ask = float(c.get("ask") or 0)
        otype = (c.get("option_type") or "").upper()
        greeks = c.get("greeks") or {}
        delta = greeks.get("delta")
        if oi < MIN_OI_FOR_RATIO or vol == 0 or ask <= 0:
            continue
        if vol / max(1, oi) < VOL_OI_MULT:
            continue
        if delta is not None and abs(float(delta)) < DEEP_OTM_DELTA:
            continue
        premium = vol * ask * 100  # dollar premium
        if premium < PREMIUM_FLOOR:
            continue
        sampled += 1
        if otype.startswith("C"):
            call_usd += premium
        elif otype.startswith("P"):
            put_usd += premium
    total = call_usd + put_usd
    if total == 0:
        return None
    imbalance = (call_usd - put_usd) / total
    whale_signal = total * abs(imbalance)
    return WhaleFlow(
        symbol="",  # filled by caller
        sweep_score=round(total, 2),
        call_sweep_usd=round(call_usd, 2),
        put_sweep_usd=round(put_usd, 2),
        directional_imbalance=round(imbalance, 4),
        whale_signal=round(whale_signal, 2),
        sample_contracts=sampled,
    )


async def evaluate_symbol(symbol: str) -> WhaleFlow | None:
    from data.tradier import get_tradier
    client = get_tradier()
    try:
        chain = await client.get_best_chain(symbol, min_dte=7, max_dte=45)
    except Exception as e:
        logger.debug(f"whale_flow chain fetch failed for {symbol}: {e}")
        return None
    metrics = _classify_chain(chain)
    if metrics is None:
        return None
    metrics.symbol = symbol
    return metrics


async def _persist(metrics: list[WhaleFlow], as_of: date) -> int:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    written = 0
    async with AsyncSessionLocal() as session:
        for m in metrics:
            try:
                await session.execute(text("""
                    INSERT INTO whale_flow_signals
                        (symbol, as_of_date, sweep_score, call_sweep_usd,
                         put_sweep_usd, directional_imbalance, whale_signal,
                         sample_contracts)
                    VALUES
                        (:sym, :d, :sweep, :call_usd, :put_usd, :imb, :signal, :n)
                    ON CONFLICT (symbol, as_of_date) DO UPDATE SET
                        sweep_score = EXCLUDED.sweep_score,
                        call_sweep_usd = EXCLUDED.call_sweep_usd,
                        put_sweep_usd = EXCLUDED.put_sweep_usd,
                        directional_imbalance = EXCLUDED.directional_imbalance,
                        whale_signal = EXCLUDED.whale_signal,
                        sample_contracts = EXCLUDED.sample_contracts
                """), {
                    "sym": m.symbol, "d": as_of, "sweep": m.sweep_score,
                    "call_usd": m.call_sweep_usd, "put_usd": m.put_sweep_usd,
                    "imb": m.directional_imbalance, "signal": m.whale_signal,
                    "n": m.sample_contracts,
                })
                written += 1
            except Exception as e:
                logger.debug(f"whale_flow upsert failed for {m.symbol}: {e}")
        await session.commit()
    return written


async def run_whale_flow_job(symbols: Iterable[str] | None = None,
                              max_symbols: int = 400,
                              concurrency: int = 12) -> int:
    """Nightly: scan the universe for whale flow, persist + cross-section rank."""
    from data.scanner import get_scan_universe
    from scoring.cross_section import rank_values, persist_ranks
    from core.database import AsyncSessionLocal

    if symbols is None:
        symbols = await get_scan_universe()
    symbols = list(symbols)[:max_symbols]
    logger.info(f"whale_flow job: scanning {len(symbols)} symbols")

    sem = asyncio.Semaphore(concurrency)

    async def _one(sym: str) -> WhaleFlow | None:
        async with sem:
            return await evaluate_symbol(sym)

    results = await asyncio.gather(*[_one(s) for s in symbols])
    flows = [r for r in results if r is not None]

    today = date.today()
    written = await _persist(flows, today)

    # Cross-sectional rank by whale_signal (magnitude). Direction comes through
    # via directional_imbalance which the strategist prompt sees directly.
    scores = {f.symbol: float(f.whale_signal) for f in flows if f.whale_signal > 0}
    if scores:
        ranks = rank_values(scores)
        async with AsyncSessionLocal() as session:
            await persist_ranks("whale_flow", ranks, today, session)

    logger.info(f"whale_flow job: {written} symbols persisted, {len(scores)} ranked")
    return written
