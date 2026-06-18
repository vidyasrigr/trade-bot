"""
Insider opportunistic-buy cluster generator (Cohen, Malloy & Pomorski 2012).

Opportunistic (non-routine) insider buy CLUSTERS predict ~6%/yr abnormal returns;
routine buys predict nothing. We reuse analysis.insider_flow.detect_cluster (the
same classifier the live job uses) and go long when a cluster fires, holding
`hold_days`.

Data: FMP v4/insider-trading per symbol (fetched directly here — no Redis
dependency, so the backtest runs whether or not the cache server is up).

Point-in-time: detect_cluster(trades, today=d) only looks at the trailing
30-day window ending at d, so evaluating it as-of each historical date uses no
future information. Entry is the first trading day strictly after the cluster
date; exit hold_days later. One trade per (symbol, cluster_date).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import httpx
import pandas as pd
from loguru import logger

from core.config import settings
from analysis.insider_flow import detect_cluster, _is_open_market_buy, _parse_date
from backtest.equity_engine import EquityTrade

FMP_INSIDER = "https://financialmodelingprep.com/api/v4/insider-trading"


async def _fetch_insider(symbol: str, sem: asyncio.Semaphore, limit: int = 1000) -> list[dict]:
    if not settings.FMP_API_KEY:
        return []
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(FMP_INSIDER, params={
                    "symbol": symbol, "page": 0, "limit": limit,
                    "apikey": settings.FMP_API_KEY,
                })
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception as e:
            logger.debug(f"insider bt: FMP fetch failed {symbol}: {e}")
            return []
    return data if isinstance(data, list) else []


async def generate_insider_trades(
    universe: list[str],
    start: date,
    end: date,
    *,
    hold_days: int = 60,
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

    sem = asyncio.Semaphore(8)
    syms = list(panel.columns)
    all_trades = await asyncio.gather(*[_fetch_insider(s, sem) for s in syms])

    raw: list[EquityTrade] = []
    for sym, trades in zip(syms, all_trades):
        if not trades:
            continue
        col = panel[sym]
        # Candidate evaluation dates = opportunistic buy dates inside the window.
        buy_dates = sorted({
            _parse_date(t.get("transactionDate") or t.get("filingDate"))
            for t in trades if _is_open_market_buy(t)
        } - {None})
        seen_cluster_dates: set[date] = set()
        for d in buy_dates:
            if not (start <= d <= end):
                continue
            cluster = detect_cluster(trades, today=d)
            if cluster is None:
                continue
            cd = cluster["cluster_date"]
            if cd in seen_cluster_dates:
                continue
            seen_cluster_dates.add(cd)
            entry_day = next((td for td in trading_days if td > cd), None)
            if entry_day is None or not (start <= entry_day <= end):
                continue
            ep = pos_of[entry_day]
            if ep + hold_days >= len(idx):
                continue
            entry_px, exit_px = float(col.iloc[ep]), float(col.iloc[ep + hold_days])
            if not (entry_px > 0 and exit_px > 0):
                continue
            raw.append(EquityTrade(
                symbol=sym, direction=1,  # opportunistic buys -> long
                entry_date=entry_day, exit_date=idx[ep + hold_days].date(),
                entry_price=entry_px, exit_price=exit_px, weight=1.0,
                signal=f"insider_cluster_n{cluster['n_opportunistic']}",
            ))

    by_day: dict[date, int] = {}
    for t in raw:
        by_day[t.entry_date] = by_day.get(t.entry_date, 0) + 1
    return [
        EquityTrade(**{**t.__dict__, "weight": 1.0 / by_day[t.entry_date]})
        for t in raw
    ]
