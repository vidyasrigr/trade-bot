"""
Macro indicators — FRED API + Alpha Vantage economic indicators.
Used by: analysis/macro.py (Category 1, 8% weight), volatility_regime.py
"""

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings
from core.redis_client import cache_get, cache_set


FRED_BASE = "https://api.stlouisfed.org/fred"
AV_BASE = "https://www.alphavantage.co/query"


class FredClient:
    """Fetch economic series from St. Louis FRED."""

    # Key series IDs
    SERIES = {
        "vix": "VIXCLS",
        "dxy": "DTWEXBGS",
        "fed_funds": "FEDFUNDS",
        "cpi": "CPIAUCSL",
        "gdp": "GDP",
        "unemployment": "UNRATE",
        "retail_sales": "RSXFS",
        "t10y2y": "T10Y2Y",          # 10Y-2Y yield spread (recession signal)
        "t10y3m": "T10Y3M",          # 10Y-3M spread
        "pmi_manufacturing": "MANEMP",
        "geopolitical_risk": "GEPUCURRENT",
    }

    def __init__(self):
        self.api_key = settings.FRED_API_KEY

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_series(self, series_id: str, limit: int = 50) -> pd.Series:
        cache_key = f"fred:{series_id}:{limit}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            data = orjson.loads(cached)
            s = pd.Series(data["values"], index=pd.to_datetime(data["dates"]))
            return s

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{FRED_BASE}/series/observations", params=params)
            resp.raise_for_status()
            data = resp.json()

        obs = data.get("observations", [])
        values, dates = [], []
        for o in obs:
            if o["value"] != ".":
                dates.append(o["date"])
                values.append(float(o["value"]))

        series = pd.Series(values, index=pd.to_datetime(dates)).sort_index()

        import orjson
        await cache_set(cache_key, orjson.dumps({
            "values": series.tolist(),
            "dates": [str(d.date()) for d in series.index],
        }).decode(), ttl=3600)

        return series

    async def get_vix(self) -> float | None:
        try:
            s = await self.get_series(self.SERIES["vix"], limit=5)
            return float(s.iloc[-1]) if not s.empty else None
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")
            return None

    async def get_yield_spread(self) -> float | None:
        """10Y-2Y spread. Negative = inverted = recession warning."""
        try:
            s = await self.get_series(self.SERIES["t10y2y"], limit=5)
            return float(s.iloc[-1]) if not s.empty else None
        except Exception as e:
            logger.warning(f"Yield spread fetch failed: {e}")
            return None

    async def get_macro_snapshot(self) -> dict:
        """Fetch all key macro indicators and return as flat dict for analysis."""
        import asyncio
        results = {}
        tasks = {
            name: self.get_series(sid, limit=3)
            for name, sid in self.SERIES.items()
        }
        for name, coro in tasks.items():
            try:
                series = await coro
                results[name] = float(series.iloc[-1]) if not series.empty else None
            except Exception as e:
                logger.warning(f"Macro {name} failed: {e}")
                results[name] = None
        return results


class AlphaVantageMacro:
    """Alpha Vantage economic indicators endpoint."""

    AV_INDICATORS = {
        "real_gdp": "REAL_GDP",
        "cpi": "CPI",
        "inflation": "INFLATION",
        "retail_sales": "RETAIL_SALES",
        "unemployment": "UNEMPLOYMENT",
        "fed_funds": "FEDERAL_FUNDS_RATE",
        "treasury_yield_10y": "TREASURY_YIELD",
    }

    def __init__(self):
        self.api_key = settings.ALPHA_VANTAGE_API_KEY

    async def get_indicator(self, function: str, **kwargs) -> pd.DataFrame:
        cache_key = f"av_macro:{function}:{kwargs}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            return pd.DataFrame(orjson.loads(cached))

        params = {"function": function, "apikey": self.api_key, **kwargs}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(AV_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        entries = data.get("data", [])
        if not entries:
            return pd.DataFrame()

        df = pd.DataFrame(entries)
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.set_index("date").sort_index()

        import orjson
        await cache_set(cache_key, orjson.dumps(df.reset_index().to_dict("records")).decode(), ttl=86400)
        return df


_fred: FredClient | None = None
_av_macro: AlphaVantageMacro | None = None


def get_fred() -> FredClient:
    global _fred
    if _fred is None:
        _fred = FredClient()
    return _fred


def get_av_macro() -> AlphaVantageMacro:
    global _av_macro
    if _av_macro is None:
        _av_macro = AlphaVantageMacro()
    return _av_macro
