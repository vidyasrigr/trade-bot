"""
Robinhood CSV portfolio import.

Robinhood export path:
  Account → Reports and Statements → Generate Report → Download CSV

The CSV contains columns like:
  Symbol, Name, Quantity, Average Cost, Equity, Percent Change, Equity Change, etc.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from sqlalchemy import text

from core.auth import get_current_user
from core.database import get_db

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Robinhood CSV column aliases (they change periodically — handle both)
_SYMBOL_COLS = {"symbol", "ticker", "instrument"}
_SHARES_COLS = {"quantity", "shares", "quantity owned"}
_COST_COLS = {"average cost", "avg cost", "average cost basis", "cost basis per share"}
_TOTAL_COST_COLS = {"total cost basis", "cost basis total", "equity cost basis"}


def _normalize_header(h: str) -> str:
    return h.strip().lower().replace("﻿", "")  # strip BOM


def _find_col(headers: list[str], candidates: set[str]) -> str | None:
    for h in headers:
        if h in candidates:
            return h
    return None


def _parse_float(val: str) -> float | None:
    try:
        return float(val.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def parse_robinhood_csv(content: bytes) -> list[dict[str, Any]]:
    """Parse a Robinhood account CSV export into a list of holding dicts."""
    text_content = content.decode("utf-8-sig").strip()
    reader = csv.DictReader(io.StringIO(text_content))

    raw_headers = reader.fieldnames or []
    headers = [_normalize_header(h) for h in raw_headers]

    # Build a map from normalized → original header
    header_map = dict(zip(headers, raw_headers))

    sym_key = header_map.get(_find_col(headers, _SYMBOL_COLS) or "")
    shares_key = header_map.get(_find_col(headers, _SHARES_COLS) or "")
    cost_key = header_map.get(_find_col(headers, _COST_COLS) or "")
    total_cost_key = header_map.get(_find_col(headers, _TOTAL_COST_COLS) or "")

    if not sym_key or not shares_key:
        raise ValueError(
            f"Could not find required columns in CSV. Found: {raw_headers}. "
            "Expected Symbol and Quantity columns."
        )

    holdings = []
    for row in reader:
        symbol = row.get(sym_key, "").strip().upper()
        if not symbol or symbol in ("", "TOTAL", "CASH"):
            continue

        shares = _parse_float(row.get(shares_key, ""))
        avg_cost = _parse_float(row.get(cost_key or "", "")) if cost_key else None
        total_cost = _parse_float(row.get(total_cost_key or "", "")) if total_cost_key else None

        if not shares or shares <= 0:
            continue

        # Compute missing fields
        if avg_cost and not total_cost:
            total_cost = round(avg_cost * shares, 2)
        elif total_cost and not avg_cost:
            avg_cost = round(total_cost / shares, 4) if shares > 0 else None

        holdings.append({
            "symbol": symbol,
            "shares": shares,
            "avg_cost_basis": avg_cost,
            "total_cost": total_cost,
        })

    return holdings


@router.post("/import/robinhood")
async def import_robinhood_csv(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Import a Robinhood CSV into portfolio_holdings for the logged-in user.
    Each user's holdings are completely separate.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    try:
        holdings = parse_robinhood_csv(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not holdings:
        raise HTTPException(status_code=422, detail="No valid holdings found in CSV")

    user_id = user["id"]
    imported = 0
    async for session in get_db():
        for h in holdings:
            try:
                await session.execute(
                    text("""
                        INSERT INTO portfolio_holdings (
                            user_id, symbol, asset_type, shares, avg_cost_basis,
                            total_cost, import_source, imported_at, updated_at
                        ) VALUES (
                            :user_id, :symbol, 'stock', :shares, :avg_cost,
                            :total_cost, 'robinhood_csv', NOW(), NOW()
                        )
                        ON CONFLICT (user_id, symbol) DO UPDATE SET
                            shares        = EXCLUDED.shares,
                            avg_cost_basis = EXCLUDED.avg_cost_basis,
                            total_cost    = EXCLUDED.total_cost,
                            updated_at    = NOW()
                    """),
                    {
                        "user_id":    user_id,
                        "symbol":     h["symbol"],
                        "shares":     h["shares"],
                        "avg_cost":   h["avg_cost_basis"],
                        "total_cost": h["total_cost"],
                    },
                )
                imported += 1
            except Exception as e:
                logger.warning(f"Portfolio import [{user['username']}]: failed {h['symbol']}: {e}")

        await session.commit()

    logger.info(f"Portfolio import [{user['username']}]: {imported}/{len(holdings)} holdings")
    return {
        "status": "ok",
        "imported": imported,
        "total_in_file": len(holdings),
        "symbols": [h["symbol"] for h in holdings],
    }


@router.get("/holdings")
async def get_holdings(user: dict = Depends(get_current_user)):
    """Return the logged-in user's portfolio holdings with LT scores and DNA data."""
    async for session in get_db():
        result = await session.execute(
            text("""
                SELECT
                    ph.symbol, ph.shares, ph.avg_cost_basis, ph.total_cost,
                    ph.current_price, ph.market_value, ph.unrealized_pnl, ph.unrealized_pnl_pct,
                    ph.lt_score, ph.lt_tier, ph.covered_call_flag,
                    ph.sell_trigger_active, ph.sell_trigger_reason,
                    ph.tranche_levels, ph.updated_at,
                    sd.earnings_direction_bias_on_beat,
                    sd.post_ath_20d_median_return, sd.data_quality_score as dna_quality
                FROM portfolio_holdings ph
                LEFT JOIN stock_dna sd ON sd.symbol = ph.symbol
                WHERE ph.user_id = :uid
                ORDER BY ph.lt_score DESC NULLS LAST
            """),
            {"uid": user["id"]},
        )
        rows = [dict(r) for r in result.mappings()]
        return {"holdings": rows, "count": len(rows), "user": user["username"]}


@router.delete("/holdings/{symbol}")
async def remove_holding(symbol: str):
    """Remove a single holding (e.g., after selling out of a position)."""
    async for session in get_db():
        result = await session.execute(
            text("DELETE FROM portfolio_holdings WHERE symbol = :sym RETURNING symbol"),
            {"sym": symbol.upper()}
        )
        deleted = result.rowcount
        await session.commit()

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"{symbol} not found in portfolio")
    return {"status": "removed", "symbol": symbol.upper()}
