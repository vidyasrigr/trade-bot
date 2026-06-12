"""
Long-Term Investment Pipeline API routes.

Endpoints:
  GET /api/lt/score/{symbol}         — LT composite score for a stock
  GET /api/lt/portfolio              — LT scores for all holdings
  GET /api/lt/opportunities          — LEAPS candidates + covered call opportunities
  GET /api/lt/sell-discipline/{sym}  — Sell trigger status for a holding
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from core.auth import get_current_user

from analysis.lt_scoring import LTScore, format_lt_context, score_stock
from scoring.lt_sell_discipline import SellTriggerResult

router = APIRouter(prefix="/api/lt", tags=["long-term"])


# ---------------------------------------------------------------------------
# GET /api/lt/score/{symbol}
# ---------------------------------------------------------------------------

@router.get("/score/{symbol}")
async def get_lt_score(symbol: str, ivr: float | None = None):
    """
    Compute or retrieve cached LT score for a single symbol.
    Pass `?ivr=45` to get LEAPS/covered call flags based on current IV rank.
    """
    symbol = symbol.upper()

    try:
        lt = await score_stock(symbol=symbol, ivr=ivr)
    except Exception as e:
        logger.error(f"LT score failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return _lt_to_dict(lt)


# ---------------------------------------------------------------------------
# GET /api/lt/portfolio
# ---------------------------------------------------------------------------

@router.get("/portfolio")
async def get_portfolio_lt_scores(user: dict = Depends(get_current_user)):
    """
    Return LT scores for all portfolio holdings (from portfolio_holdings table).
    Also includes sell trigger status from lt_sell_discipline.
    """
    from core.database import get_db
    from sqlalchemy import text

    holdings = []
    async for session in get_db():
        result = await session.execute(
            text("SELECT symbol, avg_cost_basis, shares, lt_score, lt_tier, "
                 "sell_trigger_active, sell_trigger_reason, covered_call_flag, "
                 "tranche_levels FROM portfolio_holdings WHERE user_id = :uid "
                 "ORDER BY lt_score DESC NULLS LAST"),
            {"uid": user["id"]},
        )
        holdings = [dict(r) for r in result.mappings()]

    if not holdings:
        return {"holdings": [], "opportunities": []}

    # Fetch fresh LT scores for each (uses cache)
    scored = []
    for h in holdings:
        sym = h["symbol"]
        try:
            lt = await score_stock(symbol=sym)
            d = _lt_to_dict(lt)
            d["shares"] = h.get("shares")
            d["avg_cost_basis"] = h.get("avg_cost_basis")
            scored.append(d)
        except Exception as e:
            logger.debug(f"LT portfolio score failed for {sym}: {e}")
            scored.append({"symbol": sym, "error": str(e)})

    return {"holdings": scored, "count": len(scored)}


# ---------------------------------------------------------------------------
# GET /api/lt/opportunities
# ---------------------------------------------------------------------------

@router.get("/opportunities")
async def get_lt_opportunities(user: dict = Depends(get_current_user)):
    """
    Return:
    - LEAPS candidates: LT score > 75 + low IVR stocks from scanner universe
    - Covered call opportunities: portfolio holdings with LT score > 65 + IVR > 60
    - Long candidates: LT score > 65, tier = 'long'
    """
    from data.scanner import get_scanner_universe
    from core.database import get_db
    from sqlalchemy import text

    # Top stocks from scanner universe (cached)
    try:
        universe = await get_scanner_universe(limit=50)
        symbols = [s["symbol"] for s in universe]
    except Exception:
        symbols = ["NVDA", "AMD", "INTC", "AVGO", "MSFT", "GOOGL", "META", "AAPL", "AMZN", "TSLA"]

    leaps_candidates = []
    long_candidates = []

    # Score a subset of the universe (parallelism limited by FMP rate limits)
    import asyncio
    tasks = [score_stock(symbol=sym) for sym in symbols[:20]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for lt in results:
        if isinstance(lt, Exception):
            continue
        if lt.tier in ("leaps_candidate", "long"):
            row = _lt_to_dict(lt)
            if lt.leaps_candidate:
                leaps_candidates.append(row)
            else:
                long_candidates.append(row)

    # Covered call opportunities from portfolio holdings
    covered_call_opps = []
    async for session in get_db():
        result = await session.execute(
            text("SELECT symbol, shares, avg_cost_basis, lt_score, lt_tier "
                 "FROM portfolio_holdings WHERE covered_call_flag = TRUE AND user_id = :uid "
                 "ORDER BY lt_score DESC"),
            {"uid": user["id"]},
        )
        covered_call_opps = [dict(r) for r in result.mappings()]

    return {
        "leaps_candidates": sorted(leaps_candidates, key=lambda x: x.get("total_score", 0), reverse=True),
        "long_candidates": sorted(long_candidates, key=lambda x: x.get("total_score", 0), reverse=True),
        "covered_call_opportunities": covered_call_opps,
    }


# ---------------------------------------------------------------------------
# GET /api/lt/sell-discipline/{symbol}
# ---------------------------------------------------------------------------

@router.get("/sell-discipline/{symbol}")
async def get_sell_discipline(symbol: str):
    """
    Run sell discipline checks for a single symbol.
    Requires that FMP data is available.
    """
    from analysis.fundamental import _get_fmp_financials
    symbol = symbol.upper()

    fmp = await _get_fmp_financials(symbol)
    inc_data = fmp.get("income", [])
    bs_data = fmp.get("balance", [])
    cf_data = fmp.get("cashflow", [])

    if not inc_data:
        return {"symbol": symbol, "warning": "No FMP data available for sell discipline check"}

    # Build fundamentals dict for sell discipline
    from analysis.fundamental import _safe_float, _compute_piotroski

    def rev(d: list, k: str, i: int = 0):
        if i < len(d):
            return _safe_float(d[i].get(k))
        return None

    # Build revenue QoQ history
    revenues = [_safe_float(q.get("revenue")) for q in inc_data if _safe_float(q.get("revenue"))]
    rev_qoq_history = []
    for i in range(len(revenues) - 1):
        if revenues[i+1] and revenues[i+1] > 0:
            rev_qoq_history.append((revenues[i] - revenues[i+1]) / revenues[i+1])

    # Gross margin history
    gm_history = []
    for q in inc_data[:6]:
        r = _safe_float(q.get("revenue")); gp = _safe_float(q.get("grossProfit"))
        if r and r > 0 and gp is not None:
            gm_history.append(gp / r)

    # Piotroski current vs prior (use quarters 0-3 vs 4-7 as proxy)
    p_current = _compute_piotroski(inc_data[:4], bs_data[:4], cf_data[:4])
    p_prior = _compute_piotroski(inc_data[4:], bs_data[4:], cf_data[4:])

    # EPS growth history (YoY)
    eps_growth_history = []
    for i in range(min(4, len(inc_data))):
        if i + 4 < len(inc_data):
            cur_eps = _safe_float(inc_data[i].get("eps"))
            yr_eps = _safe_float(inc_data[i+4].get("eps"))
            if cur_eps and yr_eps and yr_eps != 0:
                eps_growth_history.append((cur_eps - yr_eps) / abs(yr_eps) * 100)

    fundamentals = {
        "piotroski_current": p_current,
        "piotroski_prior": p_prior,
        "rev_qoq_history": rev_qoq_history,
        "gm_history": gm_history,
        "eps_growth_history": eps_growth_history,
        "eps_revision_history": [],  # populated by analyst data if available
    }

    from scoring.lt_sell_discipline import run_sell_discipline
    result = await run_sell_discipline(symbol, fundamentals, {}, [])

    return {
        "symbol": symbol,
        "triggers_fired": result.triggers_fired,
        "bubble_conditions_met": result.bubble_conditions_met,
        "bubble_score_action": result.bubble_score_action,
        "should_alert": result.should_alert,
        "summary": result.summary,
    }


# ---------------------------------------------------------------------------
# GET /api/lt/correlation
# ---------------------------------------------------------------------------

@router.get("/correlation")
async def get_portfolio_correlation():
    """
    Rolling 60-day pairwise return correlations across all portfolio holdings.
    Returns: symbols, matrix, flagged pairs (>0.60), avg correlation, warning.
    """
    import numpy as np
    import pandas as pd
    import yfinance as yf
    from core.database import get_db
    from sqlalchemy import text

    symbols: list[str] = []
    async for session in get_db():
        result = await session.execute(
            text("SELECT symbol FROM portfolio_holdings ORDER BY symbol")
        )
        symbols = [r[0] for r in result.fetchall()]

    if len(symbols) < 2:
        return {
            "symbols": symbols,
            "matrix": {},
            "high_correlation_pairs": [],
            "avg_correlation": None,
            "warning": None,
        }

    prices: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            df = yf.Ticker(sym).history(period="3mo", interval="1d", auto_adjust=True)
            if not df.empty:
                prices[sym] = df["Close"].tail(60)
        except Exception as e:
            logger.debug(f"yfinance close failed for {sym}: {e}")

    if len(prices) < 2:
        return {
            "symbols": symbols,
            "matrix": {},
            "high_correlation_pairs": [],
            "avg_correlation": None,
            "warning": "Insufficient price data to compute correlations",
        }

    valid_syms = list(prices.keys())
    price_df = pd.DataFrame(prices).dropna(how="all")
    returns_df = price_df.pct_change().dropna()
    corr = returns_df.corr()

    # Build matrix dict
    matrix: dict[str, dict[str, float | None]] = {}
    for s1 in valid_syms:
        matrix[s1] = {}
        for s2 in valid_syms:
            try:
                v = float(corr.loc[s1, s2])
                matrix[s1][s2] = round(v, 3) if not np.isnan(v) else None
            except KeyError:
                matrix[s1][s2] = None

    # Flag notable pairs (abs corr > 0.60)
    high_pairs = []
    for i, s1 in enumerate(valid_syms):
        for j, s2 in enumerate(valid_syms):
            if i >= j:
                continue
            try:
                v = float(corr.loc[s1, s2])
                if np.isnan(v) or abs(v) <= 0.60:
                    continue
                high_pairs.append({
                    "symbol1": s1,
                    "symbol2": s2,
                    "correlation": round(v, 3),
                    "level": "extreme" if abs(v) > 0.85 else "high" if abs(v) > 0.75 else "moderate",
                })
            except KeyError:
                continue

    high_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    # Avg off-diagonal correlation
    mask = ~np.eye(len(valid_syms), dtype=bool)
    avg_corr = float(np.nanmean(corr.values[mask])) if len(valid_syms) > 1 else None

    warning = None
    if avg_corr is not None and avg_corr > 0.55:
        warning = (
            f"Portfolio avg correlation {avg_corr:.2f} exceeds 0.55 — "
            "consider adding uncorrelated positions to reduce concentration risk"
        )

    return {
        "symbols": valid_syms,
        "matrix": matrix,
        "high_correlation_pairs": high_pairs,
        "avg_correlation": round(avg_corr, 3) if avg_corr is not None else None,
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _lt_to_dict(lt: LTScore) -> dict:
    import dataclasses
    return dataclasses.asdict(lt)
