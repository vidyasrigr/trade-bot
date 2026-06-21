"""
Persistent equity OHLCV cache for the backtest engine (CONSTRAINT_RUNBOOK Track 3).

yfinance BULK downloads rate-limit / IP-ban partway through large universes, handing
later equity variants empty panels (false 0-trade verdicts). This module persists
per-symbol daily OHLCV to data/feature_store/equity/<SYM>.parquet so:
  - the free-signal sweep reads close panels from disk (fast, no throttle, repeatable)
  - a paced single-name backfill daemon fills the cache once, then every backtest is free

_close_panel reads here first and only falls back to yfinance for misses (write-through).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd
from loguru import logger

EQUITY_DIR = Path(__file__).resolve().parents[1].parent / "data" / "feature_store" / "equity"


def _path(symbol: str) -> Path:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in symbol)
    return EQUITY_DIR / f"{safe}.parquet"


def fresh(symbol: str, max_age_days: float = 1.5) -> bool:
    p = _path(symbol)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) / 86400.0 < max_age_days


def load_close(symbol: str) -> pd.Series | None:
    """Date-indexed close series from the cache, or None if absent/too short."""
    p = _path(symbol)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]))
        return s.sort_index()
    except Exception as e:
        logger.debug(f"equity cache read failed {symbol}: {e}")
        return None


def write_ohlcv(symbol: str, df: pd.DataFrame) -> None:
    """Persist a yfinance-shaped OHLCV frame (index=date) to the cache."""
    if df is None or df.empty:
        return
    try:
        EQUITY_DIR.mkdir(parents=True, exist_ok=True)
        out = pd.DataFrame({
            "date": pd.to_datetime(df.index),
            "open": df.get("open"),
            "high": df.get("high"),
            "low": df.get("low"),
            "close": df["close"],
            "volume": df.get("volume"),
        })
        tmp = _path(symbol).with_suffix(".tmp")
        out.to_parquet(tmp, index=False)
        tmp.replace(_path(symbol))
    except Exception as e:
        logger.debug(f"equity cache write failed {symbol}: {e}")


def cached_panel(universe: list[str], min_len: int = 260) -> tuple[pd.DataFrame, list[str]]:
    """
    Build a close panel from the cache for the names present. Returns
    (panel, missing) where missing are names with no/short cached history.
    """
    cols: dict[str, pd.Series] = {}
    missing: list[str] = []
    for sym in dict.fromkeys(universe):
        s = load_close(sym)
        if s is not None and len(s) > min_len:
            cols[sym] = s
        else:
            missing.append(sym)
    if not cols:
        return pd.DataFrame(), missing
    panel = pd.DataFrame(cols)
    panel.index = pd.to_datetime(panel.index)
    return panel.sort_index(), missing


def backfill_symbol(symbol: str, period: str = "10y", prefer_marketdata: bool = False) -> bool:
    """Pull one symbol's OHLCV into the cache.

    yfinance first (free); on empty/throttle, fall back to MarketData get_history
    (reliable, ~1 credit/name — negligible vs the 10k chain budget). Returns True
    if anything was cached. prefer_marketdata=True skips yfinance (use when yfinance
    is throttled to avoid slow retry timeouts).
    """
    if prefer_marketdata:
        return _backfill_marketdata(symbol)
    from data.market import get_multi_ohlcv_yfinance
    try:
        got = get_multi_ohlcv_yfinance([symbol], period=period)
        df = got.get(symbol)
        if df is not None and not df.empty and len(df) > 260:
            write_ohlcv(symbol, df)
            return True
    except Exception as e:
        logger.debug(f"backfill_symbol yfinance {symbol} failed: {e}")
    # fallback: MarketData daily bars
    return _backfill_marketdata(symbol)


def backfill_symbol_deep_yf(symbol: str, start_year: int = 2009) -> bool:
    """0620.3 Phase 5b: deep history via yfinance per-Ticker .history(period=max).
    The per-Ticker API serves full history (1980s+) reliably; only the bulk yf.download
    throttles. Filters to >= start_year and overwrites the cache. Falls back to MarketData
    (5y) on failure."""
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period="max", auto_adjust=True)
        if df is None or df.empty or len(df) < 260:
            return _backfill_marketdata(symbol)
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                "Close": "close", "Volume": "volume"})
        df = df[df.index.year >= start_year]
        if len(df) < 260:
            return _backfill_marketdata(symbol)
        df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
        write_ohlcv(symbol, df)
        return True
    except Exception as e:
        logger.debug(f"deep yf backfill {symbol} failed: {e}")
        return _backfill_marketdata(symbol)


def _backfill_marketdata(symbol: str, start_year: int = 2009) -> bool:
    # 0620.3 Phase 5b: MarketData serves DEEP equity history (the 5y cap is options-only),
    # so pull from ~2009 to give the regime sweep multiple regime instances (GFC-recovery,
    # 2015/2018/2020/2022 stress, 2021/2023-26 bull).
    import asyncio
    from datetime import date
    try:
        from data.marketdata import MarketDataClient
        start = f"{start_year}-01-01"
        end = date.today().isoformat()
        client = MarketDataClient()
        bars = asyncio.run(client.get_history(symbol, interval="daily",
                                              start=start, end=end))
        if not bars or len(bars) < 260:
            return False
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        write_ohlcv(symbol, df)
        return True
    except Exception as e:
        logger.debug(f"backfill_symbol marketdata {symbol} failed: {e}")
        return False
