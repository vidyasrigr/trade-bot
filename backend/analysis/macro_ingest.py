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

# series_id -> friendly_name. FRED is free/unlimited so we bank a broad macro panel
# (30+ series) for the regime classifier, macro overlay, stock_climate, and
# calibration. Expanded 2026-06-19 (Track 4a) from 11 -> 33.
SERIES: dict[str, str] = {
    # --- rates / curve ---
    "DFF": "fed_funds",              # policy rate
    "SOFR": "sofr",                  # secured overnight rate
    "DGS3MO": "y3m",                 # 3m treasury
    "DGS2": "y2",                    # 2y
    "DGS10": "y10",                  # 10y
    "DGS30": "y30",                  # 30y
    "T10Y2Y": "y10y2_spread",        # 10y-2y (recession indicator)
    "T10Y3M": "y10y3m_spread",       # 10y-3m (preferred recession indicator)
    # --- inflation / breakevens ---
    "CPIAUCSL": "cpi",               # headline CPI
    "CPILFESL": "core_cpi",          # core CPI
    "PCEPILFE": "core_pce",          # core PCE (Fed's target)
    "T5YIE": "breakeven_5y",         # 5y inflation breakeven
    "T10YIE": "breakeven_10y",       # 10y inflation breakeven
    "T5YIFR": "fwd_5y5y",            # 5y5y forward inflation
    # --- vol / financial conditions / stress ---
    "VIXCLS": "vix",                 # regime vol bucket
    "VXVCLS": "vix_3m",              # 3m VIX (term structure)
    "NFCI": "fin_conditions",        # Chicago Fed financial conditions
    "STLFSI4": "fin_stress",         # St Louis financial stress
    # --- credit ---
    "BAMLH0A0HYM2": "hy_credit_oas", # HY OAS (risk-on/off)
    "BAMLC0A0CM": "ig_credit_oas",   # IG OAS
    "BAA10Y": "baa_10y_spread",      # Baa corporate spread
    # --- growth / labor ---
    "UNRATE": "unemployment",
    "ICSA": "jobless_claims",        # recession lead
    "PAYEMS": "nonfarm_payrolls",
    "INDPRO": "industrial_production",
    "UMCSENT": "consumer_sentiment",
    "HOUST": "housing_starts",
    "RSAFS": "retail_sales",
    # --- money / liquidity ---
    "WALCL": "fed_balance_sheet",
    "M2SL": "m2_money_supply",
    "RRPONTSYD": "reverse_repo",
    # --- fx / commodities ---
    "DTWEXBGS": "dollar_index",
    "DCOILWTICO": "oil_wti",
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
