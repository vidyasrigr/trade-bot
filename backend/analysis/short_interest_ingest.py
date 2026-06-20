"""
FINRA consolidated biweekly short-interest ingester (0619.3 Track E).

Free source: FINRA otcMarket consolidatedShortInterest (JSON; CSV has unquoted commas).
Biweekly settlement snapshots from 2020. Distinct from the FINRA daily short *volume*
in macro_feeds — this is short *interest* (position + days-to-cover) for squeeze logic.

Banks rows >= START to one parquet: data/feature_store/short_interest/consolidated.parquet
(symbol, settlement_date, short_position, prev_short_position, days_to_cover, adv, change_pct).
Idempotent overwrite. read_symbol() returns a date-indexed series for the adapter.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger

FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
SI_DIR = Path(__file__).resolve().parents[2] / "data" / "feature_store" / "short_interest"
SI_FILE = SI_DIR / "consolidated.parquet"
START = "2021-01-01"
PAGE = 5000


def _universe() -> list[str]:
    """Liquid universe to bank SI for (per-symbol query; the full OTC set is huge
    and not date-sorted, so per-symbol POST filtering is the efficient path)."""
    syms: list[str] = []
    try:
        from backtest.liquid_universe import liquid_top
        syms += liquid_top(500)
    except Exception:
        pass
    try:
        from backtest.marketdata_source import DEFAULT_CACHE_ROOT
        syms += [d.name for d in DEFAULT_CACHE_ROOT.iterdir()
                 if d.is_dir() and not d.name.startswith("_")]
    except Exception:
        pass
    return list(dict.fromkeys(syms))


def _fetch_symbol(c, sym: str, start: str) -> list[dict]:
    body = {"limit": 500, "compareFilters": [
        {"compareType": "equal", "fieldName": "symbolCode", "fieldValue": sym}]}
    try:
        r = c.post(FINRA_URL, json=body,
                   headers={"Accept": "application/json", "Content-Type": "application/json"})
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    out = []
    for d in data if isinstance(data, list) else []:
        sd = str(d.get("settlementDate") or "")[:10]
        if sd < start:
            continue
        try:
            out.append({
                "symbol": sym.upper(), "settlement_date": sd,
                "short_position": float(d.get("currentShortPositionQuantity") or 0),
                "prev_short_position": float(d.get("previousShortPositionQuantity") or 0),
                "days_to_cover": float(d.get("daysToCoverQuantity") or 0),
                "adv": float(d.get("averageDailyVolumeQuantity") or 0),
                "change_pct": float(d.get("changePercent") or 0),
            })
        except (TypeError, ValueError):
            continue
    return out


def ingest(start: str = START, universe: list[str] | None = None) -> dict:
    syms = universe or _universe()
    rows: list[dict] = []
    with httpx.Client(timeout=40, follow_redirects=True) as c:
        for i, sym in enumerate(syms, 1):
            rows.extend(_fetch_symbol(c, sym, start))
            if i % 100 == 0:
                logger.info(f"FINRA SI: {i}/{len(syms)} symbols, {len(rows)} rows")
    if not rows:
        return {"rows": 0}
    df = pd.DataFrame(rows)
    df = df[df.symbol.str.match(r"^[A-Z]{1,5}$")]
    SI_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SI_FILE, index=False)
    return {"rows": len(df), "symbols": df.symbol.nunique(),
            "dates": df.settlement_date.nunique(),
            "range": (df.settlement_date.min(), df.settlement_date.max())}


_CACHE: dict[str, pd.DataFrame] | None = None


def _load() -> dict[str, pd.DataFrame]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    _CACHE = {}
    if SI_FILE.exists():
        df = pd.read_parquet(SI_FILE)
        df["settlement_date"] = pd.to_datetime(df["settlement_date"])
        for sym, g in df.groupby("symbol"):
            _CACHE[sym] = g.sort_values("settlement_date").set_index("settlement_date")
    return _CACHE


def read_symbol(symbol: str) -> pd.DataFrame | None:
    return _load().get(symbol.upper())


def coverage() -> dict:
    d = _load()
    return {"symbols": len(d), "file": str(SI_FILE), "exists": SI_FILE.exists()}


if __name__ == "__main__":
    print(ingest())
