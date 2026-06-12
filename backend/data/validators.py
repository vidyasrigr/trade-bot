"""
Data quality validators — freshness, range sanity, completeness.
Every data ingestion path runs through these before passing to analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from loguru import logger


@dataclass
class DataQuality:
    symbol: str
    is_valid: bool = True
    completeness: float = 1.0   # 0-1, fraction of expected fields present
    freshness_ok: bool = True    # True if data is not stale
    range_ok: bool = True        # True if values are in expected ranges
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "is_valid": self.is_valid,
            "completeness": self.completeness,
            "freshness_ok": self.freshness_ok,
            "range_ok": self.range_ok,
            "issues": self.issues,
        }


def validate_ohlcv(symbol: str, df: pd.DataFrame, max_stale_days: int = 3) -> DataQuality:
    q = DataQuality(symbol=symbol)

    if df.empty:
        q.is_valid = False
        q.completeness = 0.0
        q.issues.append("Empty OHLCV dataframe")
        return q

    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        q.issues.append(f"Missing columns: {missing}")
        q.completeness = 1 - len(missing) / len(required_cols)

    # Freshness: last row should be within max_stale_days market days
    last_date = df.index[-1]
    if isinstance(last_date, pd.Timestamp):
        days_stale = (pd.Timestamp.now() - last_date).days
        if days_stale > max_stale_days:
            q.freshness_ok = False
            q.issues.append(f"OHLCV stale: last date {last_date.date()}, {days_stale}d ago")

    # Range sanity
    last = df.iloc[-1]
    if "close" in df.columns:
        price = float(last["close"])
        if price <= 0:
            q.range_ok = False
            q.issues.append(f"Nonsensical price: {price}")
        if price > 100_000:
            q.issues.append(f"Price seems extreme: {price}")

    if df.isnull().any().any():
        null_pct = df.isnull().sum().sum() / df.size
        if null_pct > 0.05:
            q.issues.append(f"High null rate: {null_pct:.1%}")

    if q.issues:
        q.is_valid = len([i for i in q.issues if "stale" in i.lower() or "missing" in i.lower()]) == 0

    return q


def validate_options_chain(symbol: str, chain: list[dict]) -> DataQuality:
    q = DataQuality(symbol=symbol)

    if not chain:
        q.is_valid = False
        q.completeness = 0.0
        q.issues.append("Empty options chain")
        return q

    required = {"strike", "bid", "ask", "open_interest", "volume"}
    total_fields = len(required) * len(chain)
    missing_count = 0

    iv_missing = 0
    for contract in chain:
        for field in required:
            if contract.get(field) is None:
                missing_count += 1
        if not contract.get("greeks", {}).get("mid_iv") and not contract.get("iv"):
            iv_missing += 1

    q.completeness = 1 - (missing_count / max(total_fields, 1))

    if iv_missing / len(chain) > 0.5:
        q.issues.append(f"IV missing on {iv_missing}/{len(chain)} contracts")

    if q.completeness < 0.5:
        q.is_valid = False
        q.issues.append("Too many missing fields in options chain")

    return q


def validate_quote(symbol: str, quote: dict) -> DataQuality:
    q = DataQuality(symbol=symbol)

    if not quote:
        q.is_valid = False
        q.completeness = 0.0
        q.issues.append("Empty quote")
        return q

    price = quote.get("last") or quote.get("close") or quote.get("bid")
    if not price or float(price) <= 0:
        q.is_valid = False
        q.issues.append("No valid price in quote")

    return q


def check_freshness(fetched_at: datetime, max_age_minutes: int = 30) -> bool:
    """Returns False if data is older than max_age_minutes."""
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched_at
    return age.total_seconds() / 60 <= max_age_minutes
