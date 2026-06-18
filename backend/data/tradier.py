"""
Compatibility shim — the options data client now lives in data/marketdata.py.

MarketData replaced Tradier as the historical/quote source, but ~10 modules
still import `from data.tradier import get_tradier` (the old name stuck). Rather
than a rename sweep that risks churn, re-export the real symbols here so every
caller keeps working. This removes a whole class of import-time crashes on the
live options path (audit finding, 2026-06-17).
"""

from data.marketdata import (  # noqa: F401
    get_tradier,
    MarketDataClient,
    NullMarketDataClient,
)
