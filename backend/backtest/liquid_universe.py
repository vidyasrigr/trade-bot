"""
ADV-ranked liquid universe from the banked FMP profile cache (0619.3 Track B/C).

Builds a real liquidity ranking for free: averageVolume * price from the ~6,800
banked FMP profiles (data/cache/fmp/profile/<SYM>.json). Replaces the alphabetical
directory head (illiquid junk) and the frozen hand-list. Exposes top-N slices and a
sector map (for sector_dispersion).

Caveat (documented): averageVolume is the CURRENT trailing average, so universe
SELECTION carries mild look-ahead (a name liquid today may not have been in 2021).
That is standard for liquid-universe backtests and far better than alphabetical; the
signal logic itself remains point-in-time. Results stay SANDBOX-capped regardless.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

FMP_PROFILE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "fmp" / "profile"

# plain common-stock symbols only (mirrors data.universe filter)
import re
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


@lru_cache(maxsize=1)
def _ranked() -> list[dict]:
    """All profiled names with computed ADV, sorted desc. Cached per process."""
    rows: list[dict] = []
    if not FMP_PROFILE_DIR.exists():
        logger.warning("FMP profile cache absent — ADV universe empty")
        return rows
    for p in FMP_PROFILE_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text())
            r = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else None)
            if not r:
                continue
            sym = str(r.get("symbol") or "")
            if not _SYMBOL_RE.match(sym):
                continue
            if r.get("isActivelyTrading") is False:
                continue
            price = float(r.get("price") or 0)
            avgvol = float(r.get("averageVolume") or 0)
            adv = price * avgvol
            if adv <= 0:
                continue
            rows.append({
                "symbol": sym, "adv": adv, "price": price,
                "is_etf": bool(r.get("isEtf")),
                "sector": r.get("sector") or "Unknown",
                "industry": r.get("industry") or "Unknown",
                "market_cap": float(r.get("marketCap") or 0),
            })
        except Exception as e:
            logger.debug(f"profile parse failed {p.name}: {e}")
    rows.sort(key=lambda x: x["adv"], reverse=True)
    return rows


def liquid_top(n: int, include_etf: bool = False) -> list[str]:
    """Top-n most liquid symbols by ADV (equities only unless include_etf)."""
    out = [r["symbol"] for r in _ranked() if include_etf or not r["is_etf"]]
    return out[:n]


def full_ranked_symbols(include_etf: bool = True) -> list[str]:
    """Every profiled, actively-trading name, ADV-desc (for the chain daemon work-list)."""
    return [r["symbol"] for r in _ranked() if include_etf or not r["is_etf"]]


def sector_map() -> dict[str, str]:
    return {r["symbol"]: r["sector"] for r in _ranked()}


def coverage() -> dict:
    rows = _ranked()
    return {
        "profiled_ranked": len(rows),
        "equities": sum(1 for r in rows if not r["is_etf"]),
        "etfs": sum(1 for r in rows if r["is_etf"]),
    }
