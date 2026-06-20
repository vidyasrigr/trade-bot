"""
Disk-first reader for the FMP daemon's bank (data/cache/fmp/<endpoint>/<symbol>.json).

Backtest generators (pead/insider/analyst/fundamental) read here FIRST so a sweep never
re-fetches FMP per fold (the per-fold re-fetch bug must not recur). Returns None on a
cache miss so the caller can decide to fall back to a live fetch or skip.
"""

from __future__ import annotations

import json
from pathlib import Path

FMP_CACHE_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "fmp"


def _path(endpoint: str, symbol: str) -> Path:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in symbol)
    return FMP_CACHE_ROOT / endpoint / f"{safe}.json"


def read(endpoint: str, symbol: str):
    """Banked JSON for (endpoint, symbol), or None if not banked / unreadable."""
    p = _path(endpoint, symbol)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def has(endpoint: str, symbol: str) -> bool:
    return _path(endpoint, symbol).exists()


def coverage(endpoint: str) -> int:
    d = FMP_CACHE_ROOT / endpoint
    return sum(1 for _ in d.glob("*.json")) if d.exists() else 0
