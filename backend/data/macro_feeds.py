"""
Macro feeds — FRED + CBOE + FINRA, all free.

Provides a single cached interface to the macro overlays we'd otherwise have
to scrape one at a time:

  Liquidity & credit (FRED):
    - 10y-2y, 10y-3m yield curve slopes        (T10Y2Y, T10Y3M)
    - HY OAS credit spreads                    (BAMLH0A0HYM2)
    - Treasury TGA balance                     (WTREGEN)
    - Reverse repo daily balance               (RRPONTSYD)
    - DXY                                      (DTWEXBGS)
    - TIPS 10y breakeven inflation             (T10YIE)

  Volatility term structure (CBOE delayed):
    - VIX9D / VIX / VIX3M / VIX6M
    - Reflects vol risk premium across horizons
    - Free CSV feed updated nightly

  FINRA short sale daily volume (free CSV):
    - Daily short vol per symbol, OTC + Reg SHO consolidated tape

All values are cached in Redis with day-grained TTLs and persisted snapshots
go to the point-in-time feature store on demand.
"""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

import httpx
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
CACHE_TTL_S = 21600  # 6h — macro updates daily, but be tolerant of intraday checks

FRED_SERIES = {
    "yield_curve_10y2y": "T10Y2Y",
    "yield_curve_10y3m": "T10Y3M",
    "hy_oas": "BAMLH0A0HYM2",
    "tga_balance": "WTREGEN",        # weekly Wed
    "reverse_repo": "RRPONTSYD",     # daily
    "dxy": "DTWEXBGS",
    "breakeven_10y": "T10YIE",
}


# ---------------------------------------------------------------------------
# FRED
# ---------------------------------------------------------------------------

async def _fred_latest(series_id: str) -> tuple[date, float] | None:
    if not settings.FRED_API_KEY:
        return None
    cache_key = f"fred:{series_id}:latest"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        d, v = orjson.loads(cached)
        return date.fromisoformat(d), float(v)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(FRED_BASE, params={
                "series_id": series_id,
                "api_key": settings.FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,  # tolerate the latest few in case of holiday gaps
            })
        if resp.status_code != 200:
            logger.debug(f"FRED {series_id}: status={resp.status_code}")
            return None
        observations = resp.json().get("observations") or []
        for obs in observations:
            try:
                d = date.fromisoformat(obs.get("date"))
                v = float(obs.get("value"))
                import orjson
                await cache_set(cache_key, orjson.dumps([d.isoformat(), v]).decode(),
                                 ttl=CACHE_TTL_S)
                return d, v
            except (ValueError, TypeError):
                continue
    except Exception as e:
        logger.debug(f"FRED {series_id} fetch failed: {e}")
    return None


async def fred_snapshot() -> dict[str, float | None]:
    """All FRED series we track, latest available value."""
    results = await asyncio.gather(
        *[_fred_latest(sid) for sid in FRED_SERIES.values()],
        return_exceptions=True,
    )
    out: dict[str, float | None] = {}
    for name, res in zip(FRED_SERIES.keys(), results):
        if isinstance(res, Exception) or res is None:
            out[name] = None
        else:
            _, v = res
            out[name] = v
    return out


# ---------------------------------------------------------------------------
# VIX term structure (CBOE delayed CSV — free)
# ---------------------------------------------------------------------------

CBOE_VIX_INDEX_URLS = {
    "vix9d": "https://cdn.cboe.com/data/us/indices/index_csv/VIX9D_History.csv",
    "vix":   "https://cdn.cboe.com/data/us/indices/index_csv/VIX_History.csv",
    "vix3m": "https://cdn.cboe.com/data/us/indices/index_csv/VIX3M_History.csv",
    "vix6m": "https://cdn.cboe.com/data/us/indices/index_csv/VIX6M_History.csv",
}


@dataclass
class VixTermStructure:
    vix9d: float | None = None
    vix: float | None = None
    vix3m: float | None = None
    vix6m: float | None = None
    as_of: date | None = None

    @property
    def contango(self) -> float | None:
        """vix3m - vix. Positive = normal regime; negative = stress/backwardation."""
        if self.vix is None or self.vix3m is None:
            return None
        return self.vix3m - self.vix

    @property
    def short_term_spread(self) -> float | None:
        """vix - vix9d. Negative = near-term stress vs medium-term complacency."""
        if self.vix is None or self.vix9d is None:
            return None
        return self.vix - self.vix9d


async def _fetch_vix_csv(url: str) -> tuple[date, float] | None:
    cache_key = f"vix_csv:{url}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        d, v = orjson.loads(cached)
        return date.fromisoformat(d), float(v)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "TradeResearch macro-feed (vidyasrigr@gmail.com)",
            })
        if resp.status_code != 200:
            return None
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        if not rows:
            return None
        last = rows[-1]
        try:
            d_str = last.get("DATE") or last.get("Date") or last.get("date")
            close_str = last.get("CLOSE") or last.get("Close") or last.get("CLOSE\r")
            d = datetime.strptime(d_str.strip(), "%m/%d/%Y").date()
            v = float(close_str)
        except (ValueError, AttributeError, TypeError):
            return None
        import orjson
        await cache_set(cache_key, orjson.dumps([d.isoformat(), v]).decode(), ttl=CACHE_TTL_S)
        return d, v
    except Exception as e:
        logger.debug(f"CBOE VIX CSV fetch failed for {url}: {e}")
        return None


async def vix_term_structure() -> VixTermStructure:
    results = await asyncio.gather(
        *[_fetch_vix_csv(url) for url in CBOE_VIX_INDEX_URLS.values()],
        return_exceptions=True,
    )
    out = VixTermStructure()
    names = list(CBOE_VIX_INDEX_URLS.keys())
    most_recent: date | None = None
    for name, res in zip(names, results):
        if isinstance(res, Exception) or res is None:
            continue
        d, v = res
        setattr(out, name, v)
        if most_recent is None or d > most_recent:
            most_recent = d
    out.as_of = most_recent
    return out


# ---------------------------------------------------------------------------
# FINRA short volume (free daily CSV)
# ---------------------------------------------------------------------------

FINRA_SV_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{yyyymmdd}.txt"


@dataclass
class FinraShortVolume:
    as_of: date
    by_symbol: dict[str, dict] = field(default_factory=dict)

    def for_symbol(self, sym: str) -> dict | None:
        return self.by_symbol.get(sym.upper())


async def finra_short_volume(target: date | None = None) -> FinraShortVolume | None:
    """
    FINRA consolidates the Reg SHO short-sale daily volume.
    File format: pipe-delimited Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market.

    Tries the requested day, falls back up to 5 prior business days (holidays).
    """
    today = target or date.today()
    for delta in range(0, 6):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        url = FINRA_SV_URL.format(yyyymmdd=d.strftime("%Y%m%d"))
        cache_key = f"finra_sv:{d.isoformat()}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            data = orjson.loads(cached)
            return FinraShortVolume(as_of=d, by_symbol=data)
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "TradeResearch finra-sv"})
            if resp.status_code != 200:
                continue
            by_symbol: dict[str, dict] = {}
            for row in csv.DictReader(io.StringIO(resp.text), delimiter="|"):
                sym = (row.get("Symbol") or "").strip().upper()
                if not sym:
                    continue
                try:
                    short_vol = int(row.get("ShortVolume") or 0)
                    total_vol = int(row.get("TotalVolume") or 0)
                except (ValueError, TypeError):
                    continue
                if total_vol == 0:
                    continue
                by_symbol[sym] = {
                    "short_volume": short_vol,
                    "total_volume": total_vol,
                    "short_pct": round(short_vol / total_vol, 4),
                }
            if not by_symbol:
                continue
            import orjson
            await cache_set(cache_key, orjson.dumps(by_symbol).decode(), ttl=86400 * 3)
            return FinraShortVolume(as_of=d, by_symbol=by_symbol)
        except Exception as e:
            logger.debug(f"FINRA SV fetch failed for {d}: {e}")
            continue
    return None


# ---------------------------------------------------------------------------
# Convenience snapshot for the regime sentinel
# ---------------------------------------------------------------------------

async def macro_regime_snapshot() -> dict:
    """One blob the strategist prompt + the LightGBM features layer can both consume."""
    fred_task = fred_snapshot()
    vix_task = vix_term_structure()
    fred_data, vix_ts = await asyncio.gather(fred_task, vix_task)

    return {
        "as_of": date.today().isoformat(),
        "fred": fred_data,
        "vix_term_structure": {
            "vix9d": vix_ts.vix9d,
            "vix": vix_ts.vix,
            "vix3m": vix_ts.vix3m,
            "vix6m": vix_ts.vix6m,
            "contango_vix3m_minus_vix": vix_ts.contango,
            "short_term_spread_vix_minus_vix9d": vix_ts.short_term_spread,
        },
    }
