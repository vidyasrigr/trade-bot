"""
Market data — OHLCV + technical indicators.
Primary source: Alpha Vantage (technical indicators API).
Fallback: yfinance for bulk OHLCV history.
"""

from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd
import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings
from core.redis_client import cache_get, cache_set


AV_BASE = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    """Alpha Vantage wrapper with Redis caching to protect the free tier (25 req/day)."""

    def __init__(self):
        self.api_key = settings.ALPHA_VANTAGE_API_KEY

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _get(self, params: dict, cache_ttl: int = 3600) -> dict:
        cache_key = "av:" + ":".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            return orjson.loads(cached)

        params["apikey"] = self.api_key
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(AV_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        if "Error Message" in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        if "Note" in data:
            logger.warning("Alpha Vantage rate limit hit")

        import orjson
        await cache_set(cache_key, orjson.dumps(data).decode(), ttl=cache_ttl)
        return data

    async def get_daily_adjusted(self, symbol: str, full: bool = False) -> pd.DataFrame:
        data = await self._get({
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": "full" if full else "compact",
        })
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return pd.DataFrame()
        df = pd.DataFrame.from_dict(ts, orient="index").rename(columns={
            "1. open": "open", "2. high": "high", "3. low": "low",
            "4. close": "close", "5. adjusted close": "adj_close",
            "6. volume": "volume",
        })
        df.index = pd.to_datetime(df.index)
        df = df.astype(float).sort_index()
        return df

    async def get_rsi(self, symbol: str, period: int = 14) -> pd.Series:
        data = await self._get({
            "function": "RSI",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
            "series_type": "close",
        })
        series = data.get("Technical Analysis: RSI", {})
        if not series:
            return pd.Series(dtype=float)
        s = pd.Series({pd.Timestamp(k): float(v["RSI"]) for k, v in series.items()})
        return s.sort_index()

    async def get_macd(self, symbol: str) -> pd.DataFrame:
        data = await self._get({
            "function": "MACD",
            "symbol": symbol,
            "interval": "daily",
            "series_type": "close",
        })
        series = data.get("Technical Analysis: MACD", {})
        if not series:
            return pd.DataFrame()
        rows = {pd.Timestamp(k): {
            "macd": float(v["MACD"]),
            "signal": float(v["MACD_Signal"]),
            "hist": float(v["MACD_Hist"]),
        } for k, v in series.items()}
        return pd.DataFrame.from_dict(rows, orient="index").sort_index()

    async def get_bbands(self, symbol: str, period: int = 20) -> pd.DataFrame:
        data = await self._get({
            "function": "BBANDS",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
            "series_type": "close",
        })
        series = data.get("Technical Analysis: BBANDS", {})
        if not series:
            return pd.DataFrame()
        rows = {pd.Timestamp(k): {
            "upper": float(v["Real Upper Band"]),
            "middle": float(v["Real Middle Band"]),
            "lower": float(v["Real Lower Band"]),
        } for k, v in series.items()}
        return pd.DataFrame.from_dict(rows, orient="index").sort_index()

    async def get_atr(self, symbol: str, period: int = 14) -> pd.Series:
        data = await self._get({
            "function": "ATR",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
        })
        series = data.get("Technical Analysis: ATR", {})
        if not series:
            return pd.Series(dtype=float)
        s = pd.Series({pd.Timestamp(k): float(v["ATR"]) for k, v in series.items()})
        return s.sort_index()

    async def get_adx(self, symbol: str, period: int = 14) -> pd.Series:
        data = await self._get({
            "function": "ADX",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
        })
        series = data.get("Technical Analysis: ADX", {})
        if not series:
            return pd.Series(dtype=float)
        s = pd.Series({pd.Timestamp(k): float(v["ADX"]) for k, v in series.items()})
        return s.sort_index()

    async def get_ema(self, symbol: str, period: int = 20) -> pd.Series:
        data = await self._get({
            "function": "EMA",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
            "series_type": "close",
        })
        series = data.get(f"Technical Analysis: EMA", {})
        if not series:
            return pd.Series(dtype=float)
        s = pd.Series({pd.Timestamp(k): float(v["EMA"]) for k, v in series.items()})
        return s.sort_index()

    async def get_overview(self, symbol: str) -> dict:
        """Fundamental overview: PE, EPS, market cap, dividend, etc."""
        return await self._get({"function": "OVERVIEW", "symbol": symbol}, cache_ttl=86400)

    async def get_earnings(self, symbol: str) -> dict:
        return await self._get({"function": "EARNINGS", "symbol": symbol}, cache_ttl=86400)


# ------------------------------------------------------------------
# yfinance fallback (bulk OHLCV, free, no rate limit)
# ------------------------------------------------------------------

def get_ohlcv_yfinance(
    symbol: str,
    period: str = "2y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Returns DataFrame with columns: open, high, low, close, volume, adj_close."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=False)
        if df.empty:
            return df
        df.columns = [c.lower() for c in df.columns]
        df.index = df.index.tz_localize(None)
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.error(f"yfinance failed for {symbol}: {e}")
        return pd.DataFrame()


def get_multi_ohlcv_yfinance(symbols: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Batch fetch multiple symbols via yfinance download (single call)."""
    try:
        raw = yf.download(symbols, period=period, auto_adjust=False, progress=False)
        result: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                df = raw.xs(sym, axis=1, level=1) if len(symbols) > 1 else raw
                df.columns = [c.lower() for c in df.columns]
                df.index = df.index.tz_localize(None)
                result[sym] = df[["open", "high", "low", "close", "volume"]].dropna()
            except Exception:
                result[sym] = pd.DataFrame()
        return result
    except Exception as e:
        logger.error(f"yfinance bulk download failed: {e}")
        return {s: pd.DataFrame() for s in symbols}


def get_iv_history_proxy(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Approximate historical volatility (realized vol) as a proxy for IV history
    when ORATS is not available. Uses 20-day close-to-close HV annualized.
    """
    log_returns = (df["close"] / df["close"].shift(1)).apply(lambda x: __import__("math").log(x))
    hv = log_returns.rolling(window).std() * (252 ** 0.5)
    return hv


_av_client: AlphaVantageClient | None = None


def get_av() -> AlphaVantageClient:
    global _av_client
    if _av_client is None:
        _av_client = AlphaVantageClient()
    return _av_client
