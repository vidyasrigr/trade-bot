"""
FRED macro history ingest (NEXT_RUNBOOK Phase 2).

Banks full daily history for the macro series the regime classifier + calibration
need, to data/feature_store/macro/<series_id>.parquet. FRED is free with no
meaningful quota, so we pull complete history (most series 1970+) in one pass and
read from disk thereafter — the regime classifier never hits the live API.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger

from core.config import settings

FRED_BASE = "https://api.stlouisfed.org/fred"
MACRO_DIR = Path(__file__).resolve().parents[2] / "data" / "feature_store" / "macro"

# series_id -> (friendly_name, use)
SERIES: dict[str, str] = {
    "VIXCLS": "vix",                 # regime vol bucket
    "DFF": "fed_funds",              # macro overlay
    "DGS10": "y10",                  # yield curve
    "DGS2": "y2",                    # yield curve
    "T10Y2Y": "y10y2_spread",        # recession indicator
    "UNRATE": "unemployment",        # macro overlay
    "CPIAUCSL": "cpi",               # inflation regime
    "DTWEXBGS": "dollar_index",      # dollar proxy
    "DCOILWTICO": "oil_wti",         # sector regime
    "BAMLH0A0HYM2": "hy_credit_oas", # risk-on/off
    "ICSA": "jobless_claims",        # recession lead
}


async def ingest_fred_history(series: list[str] | None = None) -> dict:
    """Pull full history for each series → parquet. Returns {sid: (rows, start, end)}."""
    series = series or list(SERIES)
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    async with httpx.AsyncClient(timeout=40.0) as client:
        for sid in series:
            try:
                resp = await client.get(
                    f"{FRED_BASE}/series/observations",
                    params={"series_id": sid, "api_key": settings.FRED_API_KEY,
                            "file_type": "json"},
                )
                if resp.status_code != 200:
                    out[sid] = ("ERR", resp.status_code)
                    logger.warning(f"FRED {sid}: HTTP {resp.status_code}")
                    continue
                obs = resp.json().get("observations", [])
                rows = [(o["date"], float(o["value"])) for o in obs
                        if o.get("value") not in (".", "", None)]
                if not rows:
                    out[sid] = ("EMPTY", 0)
                    continue
                df = pd.DataFrame(rows, columns=["date", "value"])
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                df.to_parquet(MACRO_DIR / f"{sid}.parquet", index=False)
                out[sid] = (len(df), str(df["date"].min().date()), str(df["date"].max().date()))
            except Exception as e:
                out[sid] = ("EXC", str(e)[:60])
                logger.warning(f"FRED {sid} ingest failed: {e}")
    return out


def load_series(series_id: str) -> pd.Series:
    """Load a banked FRED series as a date-indexed pd.Series (empty if absent)."""
    path = MACRO_DIR / f"{series_id}.parquet"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_parquet(path)
    return pd.Series(df["value"].values, index=pd.to_datetime(df["date"]))
