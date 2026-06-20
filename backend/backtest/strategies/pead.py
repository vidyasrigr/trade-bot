"""
Post-Earnings-Announcement Drift (Bernard & Thomas 1989) generator.

Prices drift in the DIRECTION of the earnings surprise for weeks after the
announcement. We go long after a beat, short after a miss, when the EPS surprise
exceeds a threshold, and hold `hold_days` trading days.

Data:
  - FMP /stable/earnings?symbol=X: full history of actual vs estimate EPS.
    (The legacy /v3/earnings-surprises endpoint 403s since FMP's Aug-2025 API
    migration — see pc/log.md FMP finding. The stable endpoint replaces it.)
  - yfinance daily closes for entry/exit prices.

Point-in-time discipline:
  The surprise is only known after the report. We enter at the close of the FIRST
  trading day STRICTLY AFTER the announcement date and exit `hold_days` later.
  No same-day entry (would use information released intraday).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import httpx
import pandas as pd
from loguru import logger

from core.config import settings
from backtest.equity_engine import EquityTrade

FMP_EARNINGS = "https://financialmodelingprep.com/stable/earnings"

# Process-level cache: the generic dispatch calls the generator twice (train then
# wf). Without this, the second pass re-hits FMP for ~150 symbols back-to-back and
# trips the rate limit -> empty -> 0 trades (the wf=0 bug). Cache by symbol.
_SURPRISE_CACHE: dict[str, list] = {}


def _pdate(raw) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


async def _fetch_surprises(symbol: str, sem: asyncio.Semaphore) -> list[dict]:
    if symbol in _SURPRISE_CACHE:
        return _SURPRISE_CACHE[symbol]
    # disk-first: the FMP daemon banks /stable/earnings (same epsActual/epsEstimated/date
    # shape). Read it so a sweep never re-fetches per fold.
    from data import fmp_cache
    banked = fmp_cache.read("earnings", symbol)
    if banked is not None:
        out = banked if isinstance(banked, list) else []
        _SURPRISE_CACHE[symbol] = out
        return out
    if not settings.FMP_API_KEY:
        return []
    async with sem:
        if symbol in _SURPRISE_CACHE:
            return _SURPRISE_CACHE[symbol]
        data = None
        # FMP rate-limits bursts (429). Back off and retry instead of silently
        # treating a throttle as "no earnings" (which fabricated 0-trade verdicts).
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(
                        FMP_EARNINGS,
                        params={"symbol": symbol.upper(), "apikey": settings.FMP_API_KEY},
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    break
                if resp.status_code == 429:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                return []  # 402/403/404 etc — a real "not available", don't retry
            except Exception as e:
                logger.debug(f"pead: FMP surprises failed {symbol} (try {attempt}): {e}")
                await asyncio.sleep(1.5)
        if data is None:
            return []
    out = data if isinstance(data, list) else []
    if out:  # only cache real responses, so a rate-limited empty can be retried
        _SURPRISE_CACHE[symbol] = out
    return out


async def generate_pead_trades(
    universe: list[str],
    start: date,
    end: date,
    *,
    hold_days: int = 5,
    min_eps_surprise_pct: float = 5.0,
    panel: pd.DataFrame | None = None,
    **_ignored,
) -> list[EquityTrade]:
    from backtest.strategies.momentum_xs_v2 import _close_panel
    if panel is None:
        panel = _close_panel(universe)
    if panel.empty:
        return []
    idx = panel.index
    pos_of = {ts.date(): i for i, ts in enumerate(idx)}
    trading_days = [ts.date() for ts in idx]

    sem = asyncio.Semaphore(3)  # FMP rate-limits bursts; keep concurrency low
    syms = [s for s in panel.columns]
    surprises = await asyncio.gather(*[_fetch_surprises(s, sem) for s in syms])

    raw: list[EquityTrade] = []
    for sym, events in zip(syms, surprises):
        col = panel[sym]
        for e in events:
            d = _pdate(e.get("date"))
            actual, est = e.get("epsActual"), e.get("epsEstimated")
            if d is None or actual is None or est is None or est == 0:
                continue
            surprise_pct = (actual - est) / abs(est) * 100.0
            if abs(surprise_pct) < min_eps_surprise_pct:
                continue
            # First trading day STRICTLY after the announcement.
            entry_day = next((td for td in trading_days if td > d), None)
            if entry_day is None or not (start <= entry_day <= end):
                continue
            ep = pos_of[entry_day]
            if ep + hold_days >= len(idx):
                continue
            entry_px = float(col.iloc[ep])
            exit_px = float(col.iloc[ep + hold_days])
            if not (entry_px > 0 and exit_px > 0):
                continue
            raw.append(EquityTrade(
                symbol=sym, direction=(1 if surprise_pct > 0 else -1),
                entry_date=entry_day, exit_date=idx[ep + hold_days].date(),
                entry_price=entry_px, exit_price=exit_px, weight=1.0,
                signal=f"pead_surprise{surprise_pct:+.0f}pct",
            ))

    # Equal-weight within each entry-date cohort so a busy reporting day doesn't
    # dominate the portfolio return series.
    by_day: dict[date, int] = {}
    for t in raw:
        by_day[t.entry_date] = by_day.get(t.entry_date, 0) + 1
    return [
        EquityTrade(**{**t.__dict__, "weight": 1.0 / by_day[t.entry_date]})
        for t in raw
    ]
