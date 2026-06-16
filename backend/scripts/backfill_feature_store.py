"""
Backfill the point-in-time feature store from yfinance history.

Why: Phase B persists ONE snapshot per nightly scan. With no historical
snapshots, the Phase E LightGBM ranker can't train (needs ≥500 rows per
horizon). This script reconstructs daily snapshots for the past N days so
the ranker has training data on day 1 instead of after 6 months.

What it does:
  - For each symbol in the dynamic universe (capped at MAX_SYMBOLS):
    pull 1y of daily OHLCV via yfinance batch
  - Compute the same scalar features the live scanner persists in
    _persist_feature_snapshot(): ret_20d, vol_ratio, price_pct_52range,
    last_close (no chain-derived features — those need MarketData historical)
  - Write one snapshot per trading day to data/feature_store/{YYYY}/...

Survivorship-bias note:
  yfinance returns only currently-listed tickers. Delisted names won't appear.
  We tag each backfilled snapshot with feature_name='_backfill_yfinance'=1 so
  the ranker can be told to ignore (or down-weight) backfilled data when we
  eventually get a proper survivorship-corrected source.

Usage:
  python3 -m scripts.backfill_feature_store --days 365 --max-symbols 500
"""

from __future__ import annotations

import argparse
import asyncio
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
from loguru import logger


def _compute_daily_features(closes: pd.Series, volumes: pd.Series) -> pd.DataFrame:
    """Returns a daily-indexed DataFrame of the scanner's stage-1 scalar features."""
    if closes is None or closes.empty or len(closes) < 30:
        return pd.DataFrame()

    df = pd.DataFrame({"close": closes, "volume": volumes}).dropna()
    if len(df) < 30:
        return pd.DataFrame()

    df["ret_20d"] = df["close"].pct_change(20)
    avg_vol_20 = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / avg_vol_20.replace(0, np.nan)

    high_52 = df["close"].rolling(252, min_periods=60).max()
    low_52 = df["close"].rolling(252, min_periods=60).min()
    rng = (high_52 - low_52).replace(0, np.nan)
    df["price_pct_52range"] = (df["close"] - low_52) / rng

    df["last_close"] = df["close"]
    df["_backfill_yfinance"] = 1.0
    return df[["ret_20d", "vol_ratio", "price_pct_52range", "last_close",
               "_backfill_yfinance"]].dropna()


async def backfill(days: int, max_symbols: int, chunk_size: int = 200) -> dict:
    from data.scanner import get_scan_universe
    from data.market import get_multi_ohlcv_yfinance
    from store.feature_store import FeatureStore

    store = FeatureStore()
    existing = set(store.available_dates())

    universe = await get_scan_universe()
    universe = universe[:max_symbols]
    logger.info(f"Backfill: {len(universe)} symbols, last {days} days")

    earliest = date.today() - timedelta(days=days)

    # Snapshots indexed by date so we can write one parquet per day at the end.
    by_date: dict[date, list[dict]] = {}

    for i in range(0, len(universe), chunk_size):
        chunk = universe[i:i + chunk_size]
        try:
            ohlcv = get_multi_ohlcv_yfinance(chunk, period=f"{max(days, 252)}d")
        except Exception as e:
            logger.warning(f"yfinance chunk failed: {e}")
            continue

        for sym, df in ohlcv.items():
            if df is None or df.empty:
                continue
            try:
                feats = _compute_daily_features(df["close"], df["volume"])
                if feats.empty:
                    continue
                for ts, row in feats.iterrows():
                    d = ts.date() if hasattr(ts, "date") else ts
                    if d < earliest:
                        continue
                    if d in existing:
                        continue
                    bucket = by_date.setdefault(d, [])
                    for feat_name, value in row.items():
                        if pd.isna(value):
                            continue
                        bucket.append({
                            "symbol": sym, "feature_name": feat_name,
                            "value": float(value),
                        })
            except Exception as e:
                logger.debug(f"backfill compute failed for {sym}: {e}")

        await asyncio.sleep(0.5)  # be polite to yfinance

    written = 0
    for d, rows in sorted(by_date.items()):
        if not rows:
            continue
        try:
            df = pd.DataFrame(rows)
            store.write_snapshot(d, df)
            written += 1
        except FileExistsError:
            logger.debug(f"backfill: snapshot for {d} exists, skipping")
        except Exception as e:
            logger.warning(f"backfill write failed for {d}: {e}")

    summary = {
        "days_requested": days,
        "max_symbols": max_symbols,
        "snapshots_written": written,
        "skipped_existing": sum(1 for d in by_date if d in existing),
    }
    logger.info(f"Backfill complete: {summary}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Feature store backfill from yfinance")
    parser.add_argument("--days", type=int, default=365, help="trailing days to backfill")
    parser.add_argument("--max-symbols", type=int, default=500,
                        help="cap universe size (yfinance batch is slow above ~500)")
    args = parser.parse_args()
    asyncio.run(backfill(args.days, args.max_symbols))


if __name__ == "__main__":
    main()
