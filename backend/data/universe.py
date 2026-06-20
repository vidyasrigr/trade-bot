"""
Dynamic trading universe from the Nasdaq Trader symbol directory (free, keyless).

Replaces the hardcoded ~150-ticker list as the scan BOUNDARY — the theme lists in
scanner.py remain as a score boost and always-include set, so conviction themes
get priority without blinding the scanner to the other ~5,000 names.
"""

from __future__ import annotations

import io
import re

import httpx
import pandas as pd
from loguru import logger

from core.redis_client import cache_get, cache_set

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_CACHE_KEY = "universe:nasdaqtrader"
_CACHE_TTL = 86400  # 24h — the directory updates nightly

# Plain 1-5 letter symbols only (skips test issues, units, warrants, preferreds —
# and keeps every symbol yfinance/Tradier can handle without translation)
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


def _parse_directory(text: str, symbol_col: str, etf_col: str = "ETF",
                     test_col: str = "Test Issue") -> list[str]:
    body = "\n".join(
        line for line in text.splitlines()
        if line and not line.startswith("File Creation Time")
    )
    df = pd.read_csv(io.StringIO(body), sep="|")
    if symbol_col not in df.columns:
        return []
    if test_col in df.columns:
        df = df[df[test_col] == "N"]
    if etf_col in df.columns:
        df = df[df[etf_col] != "Y"]
    # dropna first: the directory footer row parses as a NaN symbol that astype(str)
    # can leave as a float in some pandas versions, blowing up the regex.
    col = df[symbol_col].dropna().astype(str)
    syms = [s for s in col if _SYMBOL_RE.match(s)]
    return syms


async def fetch_listed_symbols(include_other_listed: bool = True) -> list[str]:
    """
    Keyless, Redis-free fetch+parse of the listed common-stock universe (~5,000+).
    Standalone processes (e.g. the FMP daemon) use this directly so they don't need
    the app's Redis cache to be initialized. Returns [] on total failure.
    """
    symbols: set[str] = set()
    urls = [(NASDAQ_LISTED_URL, "Symbol")]
    if include_other_listed:
        urls.append((OTHER_LISTED_URL, "ACT Symbol"))

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url, col in urls:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                syms = _parse_directory(resp.text, symbol_col=col)
                symbols.update(syms)
                logger.info(f"Universe: {len(syms)} symbols from {url.rsplit('/', 1)[-1]}")
            except Exception as e:
                logger.warning(f"Universe fetch failed for {url}: {e}")

    return sorted(symbols)


async def get_dynamic_universe(include_other_listed: bool = True) -> list[str]:
    """
    Full listed common-stock universe (~5,000+ symbols), cached 24h.
    Returns [] on failure so callers can fall back to the static lists loudly.
    """
    cached = await cache_get(_CACHE_KEY)
    if cached:
        import orjson
        return orjson.loads(cached)

    result = await fetch_listed_symbols(include_other_listed=include_other_listed)
    if result:
        import orjson
        await cache_set(_CACHE_KEY, orjson.dumps(result).decode(), ttl=_CACHE_TTL)
    return result
