"""
Iron-condor variant of the VRP harvest — defined-risk version of vrp_harvest.

Motivation (V's directive, 2026-06-17):
  The naked short-strangle VRP harvest PASSED the validation gate (train DSR
  0.904, walk-forward 0.317) but carried a 51% out-of-sample max drawdown — the
  fat-left-tail of naked short vol, and the backtest never even saw a real vol
  crisis (MarketData Starter caps history at ~5y, so no 2020/2018). Adding long
  wings caps that tail. If the iron condor keeps walk-forward DSR > 0.3 AND
  drops max drawdown below 25%, the IC becomes the production path for VRP.

Apples-to-apples by construction:
  - SAME entry gate          → reuse generate_vrp_candidates (iv_rank>50, vrp_z>1)
  - SAME short strikes       → reuse _strangle_strikes (16Δ proxy), snap to listed
  - SAME expiry              → resolved from the on-disk cache, so the IC trades
                               the exact chain the naked run already paid for
  - ADD long wings 1σ further OTM (≈5Δ at 45 DTE / 30% vol), snapped to a real
    listed strike strictly beyond the short. No wing strike beyond the short on
    a given side → drop the trade (can't form a defined-risk condor).

Why wings are placed by moneyness, not real 5Δ:
  The cached historical chains carry delta == 0.0 (MarketData Starter doesn't
  return greeks on historical chains). The naked run already selected strikes by
  the spot-based _strangle_strikes formula, never by real delta. To stay
  comparable, the wings use the same moneyness language: one_sigma = spot * vol *
  sqrt(dte/365), wing = short_strike ∓ wing_sigma_mult * one_sigma.

Cost:
  Zero new MarketData credits in the common case — expiry is resolved by reading
  the cache directory and the chain (all strikes, incl. wings) is already on disk
  from the naked run. The only way to incur fetches is holding days the naked run
  exited before reaching; run_vrp_ic_backtest reports source.stats so the actual
  credit cost is never hidden.
"""

from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta

from loguru import logger

from backtest.engine import (
    BacktestConfig, BacktestReport, Leg, Trade,
    OptionsSource, run_backtest,
)
from backtest.marketdata_source import _safe
from backtest.strategies.vrp_harvest import (
    VrpConfig, VrpCandidate, generate_vrp_candidates, _strangle_strikes,
)

# Wing placement. wings_sigma is the wing distance FROM SPOT in units of one
# standard deviation, one_sigma = spot * WING_VOL * sqrt(dte/365). At 45 DTE /
# 30% vol one_sigma ≈ 0.105*spot. The _strangle_strikes short sits at ~1.6σ OTM
# (16.8% via the 1.05*0.16 rule), so wings_sigma must exceed ~1.6 to be OTM of
# the short; the sweep brackets it 1.5σ (tight) → 3.0σ (wide tail insurance).
WING_VOL = 0.30
WINGS_SIGMA = 2.5


def _cached_expiries_for(source, symbol: str, day: date) -> list[date]:
    """
    Expiries whose chain for `day` is already on disk — read from the cache
    directory layout data/marketdata_cache/{symbol}/{expiry}/{day}.parquet.

    Using the cache as the expiry oracle (instead of get_expirations) means the
    IC trades the exact expiry the naked run resolved and cached, for $0.
    """
    base = source.cache_root / _safe(symbol)
    if not base.exists():
        return []
    out: list[date] = []
    for expdir in base.iterdir():
        if not expdir.is_dir():
            continue
        if (expdir / f"{day.isoformat()}.parquet").exists():
            try:
                out.append(date.fromisoformat(expdir.name))
            except ValueError:
                continue
    return sorted(out)


def _nearest(strikes: list[float], target: float) -> float:
    return min(strikes, key=lambda s: abs(s - target))


async def _resolve_ic_candidate(
    source, candidate: VrpCandidate, config: VrpConfig,
    *, wing_vol: float = WING_VOL, wings_sigma: float = WINGS_SIGMA,
) -> Trade | None:
    """
    Build a 4-leg iron condor from a gate-fired candidate, reusing the naked
    run's cached chain. Short legs identical to the naked strangle; long wings
    placed at `wings_sigma` standard deviations from spot, snapped to a real
    listed strike strictly beyond the short. Returns None when the chain isn't
    cached or no wing strike exists beyond a short (legitimately undatable,
    never silently mispriced).
    """
    sym, d, spot = candidate.symbol, candidate.entry_date, candidate.spot

    # 1. Expiry: nearest the target DTE among the chains already cached for `d`.
    cached = _cached_expiries_for(source, sym, d)
    if not cached:
        return None
    target = d + timedelta(days=config.target_dte_entry)
    expiry = min(cached, key=lambda e: abs((e - target).days))
    if (expiry - d).days < config.target_dte_exit:
        return None

    # 2. Load the (cached) chain → available listed strikes per side.
    chain = await source._load_chain(sym, expiry, d)
    if not chain:
        return None
    put_strikes = sorted(s for (s, r) in chain if r == "P")
    call_strikes = sorted(s for (s, r) in chain if r == "C")
    if not put_strikes or not call_strikes:
        return None

    # 3. Short strikes — identical to the naked strangle.
    put_t, call_t = _strangle_strikes(spot, config.target_short_delta)
    short_put = _nearest(put_strikes, put_t)
    short_call = _nearest(call_strikes, call_t)

    # 4. Wings at wings_sigma σ from spot, snapped to a real strike strictly
    #    beyond the short.
    one_sigma = spot * wing_vol * math.sqrt(config.target_dte_entry / 365.0)
    wing_put_target = spot - wings_sigma * one_sigma
    wing_call_target = spot + wings_sigma * one_sigma

    puts_below = [s for s in put_strikes if s < short_put]
    calls_above = [s for s in call_strikes if s > short_call]
    if not puts_below or not calls_above:
        return None  # no room for a defined-risk wing on one side → drop
    long_put = _nearest(puts_below, wing_put_target)
    long_call = _nearest(calls_above, wing_call_target)

    return Trade(
        underlying=sym,
        legs=(
            Leg(right="P", strike=short_put, expiry=expiry, qty=-1),
            Leg(right="P", strike=long_put, expiry=expiry, qty=+1),
            Leg(right="C", strike=short_call, expiry=expiry, qty=-1),
            Leg(right="C", strike=long_call, expiry=expiry, qty=+1),
        ),
        entry_date=d,
        max_exit_date=d + timedelta(days=config.target_dte_entry - config.target_dte_exit),
        profit_target=config.profit_target,
        stop_loss=config.stop_loss,
        signal=candidate.signal.replace("vrp_harvest", "vrp_harvest_ic"),
    )


async def run_vrp_ic_backtest(
    symbols: list[str],
    source: OptionsSource,
    start: date,
    end: date,
    config: VrpConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    *, wing_vol: float = WING_VOL, wings_sigma: float = WINGS_SIGMA,
) -> BacktestReport:
    """Iron-condor VRP backtest — same gate + shorts as run_vrp_backtest, + wings."""
    from data.market import get_multi_ohlcv_yfinance
    prices = get_multi_ohlcv_yfinance(symbols, period="10y")

    config = config or VrpConfig()

    candidates: list[VrpCandidate] = []
    for sym, df in prices.items():
        if df is None or df.empty:
            continue
        candidates.extend(generate_vrp_candidates(
            sym, df["close"], config, entry_start=start, entry_end=end,
        ))
    logger.info(f"VRP-IC backtest: {len(candidates)} gate-fired candidates across {len(symbols)} names")

    resolve_sem = asyncio.Semaphore(6)

    async def _resolve(c: VrpCandidate) -> Trade | None:
        async with resolve_sem:
            try:
                return await _resolve_ic_candidate(
                    source, c, config,
                    wing_vol=wing_vol, wings_sigma=wings_sigma,
                )
            except Exception as e:
                logger.debug(f"IC resolve failed {c.symbol} {c.entry_date}: {e}")
                return None

    resolved = await asyncio.gather(*[_resolve(c) for c in candidates])
    trades: list[Trade] = [t for t in resolved if t is not None]
    logger.info(
        f"VRP-IC backtest: {len(trades)}/{len(candidates)} candidates resolved to real "
        f"iron condors ({len(candidates) - len(trades)} dropped — no cached chain / no wing)"
    )

    if not trades:
        logger.warning("VRP-IC backtest: zero trades resolved for the requested window")

    report = await run_backtest(
        trades=trades, source=source, config=backtest_config,
        num_trials=20,
    )
    # Surface the real credit cost — wings should be free from cache.
    stats = getattr(source, "stats", None)
    if stats:
        logger.info(f"VRP-IC backtest source stats: {stats}")
        report.metrics["source_stats"] = stats
    return report
