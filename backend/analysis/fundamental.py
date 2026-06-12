"""Category 3: Fundamental & Catalyst (8%) — earnings, short interest, analyst targets, LT quality signals."""

from __future__ import annotations

import httpx
import pandas as pd
from loguru import logger
from analysis.engine import CategoryScore
from core.config import settings
from core.redis_client import cache_get, cache_set


# ---------------------------------------------------------------------------
# FMP helper: financials for Piotroski + FCF + gross margin + revenue QoQ
# ---------------------------------------------------------------------------

async def _get_fmp_financials(symbol: str) -> dict:
    """
    Pull income statement + balance sheet + cash flow from FMP.
    Returns dict with last 3 quarters of key metrics.
    Cached 24h.
    """
    if not settings.FMP_API_KEY:
        return {}

    cache_key = f"fmp_fin:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    result: dict = {}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Income statement (quarterly)
            inc_resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/income-statement/{symbol}",
                params={"period": "quarter", "limit": 8, "apikey": settings.FMP_API_KEY},
            )
            inc_data = inc_resp.json() if inc_resp.status_code == 200 else []

            # Balance sheet (quarterly)
            bs_resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{symbol}",
                params={"period": "quarter", "limit": 8, "apikey": settings.FMP_API_KEY},
            )
            bs_data = bs_resp.json() if bs_resp.status_code == 200 else []

            # Cash flow (quarterly)
            cf_resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{symbol}",
                params={"period": "quarter", "limit": 8, "apikey": settings.FMP_API_KEY},
            )
            cf_data = cf_resp.json() if cf_resp.status_code == 200 else []

        if not isinstance(inc_data, list):
            inc_data = []
        if not isinstance(bs_data, list):
            bs_data = []
        if not isinstance(cf_data, list):
            cf_data = []

        result = {
            "income": inc_data[:8],
            "balance": bs_data[:8],
            "cashflow": cf_data[:8],
        }

        import orjson
        await cache_set(cache_key, orjson.dumps(result).decode(), ttl=86400)
        return result

    except Exception as e:
        logger.debug(f"FMP financials failed for {symbol}: {e}")
        return {}


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Revenue acceleration (QoQ slope)
# ---------------------------------------------------------------------------

def _compute_revenue_acceleration(inc_data: list) -> dict:
    """Compute QoQ revenue growth and whether it's accelerating or decelerating."""
    if len(inc_data) < 3:
        return {}

    revenues = []
    for q in inc_data[:5]:
        r = _safe_float(q.get("revenue"))
        if r and r > 0:
            revenues.append(r)

    if len(revenues) < 3:
        return {}

    # QoQ growth rates (most recent first)
    qoq_rates = []
    for i in range(len(revenues) - 1):
        if revenues[i+1] > 0:
            qoq_rates.append((revenues[i] - revenues[i+1]) / revenues[i+1])

    if not qoq_rates:
        return {}

    latest_qoq = qoq_rates[0]
    prev_qoq = qoq_rates[1] if len(qoq_rates) > 1 else None

    # YoY comparison (q0 vs q4)
    yoy = None
    if len(revenues) >= 5 and revenues[4] > 0:
        yoy = (revenues[0] - revenues[4]) / revenues[4]

    return {
        "revenue_qoq": round(latest_qoq, 4),
        "revenue_yoy": round(yoy, 4) if yoy is not None else None,
        "revenue_accelerating": (prev_qoq is not None and latest_qoq > prev_qoq),
        "revenue_decelerating": (prev_qoq is not None and latest_qoq < prev_qoq - 0.05),
    }


# ---------------------------------------------------------------------------
# Gross margin trend
# ---------------------------------------------------------------------------

def _compute_gross_margin_trend(inc_data: list) -> dict:
    """Detect gross margin expansion vs compression over last 3 quarters."""
    if len(inc_data) < 3:
        return {}

    margins = []
    for q in inc_data[:5]:
        rev = _safe_float(q.get("revenue"))
        gp = _safe_float(q.get("grossProfit"))
        if rev and rev > 0 and gp is not None:
            margins.append(gp / rev)

    if len(margins) < 2:
        return {}

    latest = margins[0]
    prev = margins[1]
    older = margins[2] if len(margins) > 2 else None

    expanding = latest > prev and (older is None or prev > older)
    compressing = latest < prev and (older is None or prev < older)

    return {
        "gross_margin_latest": round(latest, 4),
        "gross_margin_expanding": expanding,
        "gross_margin_compressing": compressing,
        "gross_margin_delta_qoq": round(latest - prev, 4),
    }


# ---------------------------------------------------------------------------
# FCF yield
# ---------------------------------------------------------------------------

def _compute_fcf_yield(cf_data: list, inc_data: list, symbol: str) -> dict:
    """
    FCF yield = (TTM Free Cash Flow) / Market Cap.
    FCF = operating cash flow - capex.
    """
    if not cf_data:
        return {}

    ttm_fcf = 0.0
    for q in cf_data[:4]:  # trailing 4 quarters
        ocf = _safe_float(q.get("operatingCashFlow")) or 0
        capex = _safe_float(q.get("capitalExpenditure")) or 0
        ttm_fcf += ocf - abs(capex)  # capex is usually negative in FMP data

    if ttm_fcf == 0:
        return {}

    return {
        "ttm_fcf": round(ttm_fcf, 0),
        "fcf_positive": ttm_fcf > 0,
    }


# ---------------------------------------------------------------------------
# Piotroski F-score (0-9)
# ---------------------------------------------------------------------------

def _compute_piotroski(inc_data: list, bs_data: list, cf_data: list) -> int | None:
    """
    Compute Piotroski F-score from quarterly financial statements.
    Returns 0-9 integer or None if data insufficient.

    Profitability (4 signals):
      F1: ROA > 0
      F2: Operating CF > 0
      F3: ROA increasing (vs prior year)
      F4: Accruals = OCF/Assets - ROA > 0 (cash > accruals)

    Leverage / Liquidity (3 signals):
      F5: Long-term debt ratio decreasing
      F6: Current ratio increasing
      F7: No new shares issued

    Operating efficiency (2 signals):
      F8: Gross margin improving
      F9: Asset turnover improving
    """
    if not inc_data or not bs_data or not cf_data:
        return None

    try:
        def g(d: list, key: str, idx: int = 0) -> float | None:
            if idx < len(d):
                return _safe_float(d[idx].get(key))
            return None

        # Current quarter (most recent)
        net_income = g(inc_data, "netIncome")
        total_assets = g(bs_data, "totalAssets")
        ocf = g(cf_data, "operatingCashFlow")
        gross_profit = g(inc_data, "grossProfit")
        revenue = g(inc_data, "revenue")

        # Prior year same quarter (index 4 = 4 quarters ago)
        net_income_prev = g(inc_data, "netIncome", 4)
        total_assets_prev = g(bs_data, "totalAssets", 4)
        gross_profit_prev = g(inc_data, "grossProfit", 4)
        revenue_prev = g(inc_data, "revenue", 4)

        # Balance sheet components
        lt_debt = g(bs_data, "longTermDebt") or 0
        lt_debt_prev = (g(bs_data, "longTermDebt", 4) or 0)
        current_assets = g(bs_data, "totalCurrentAssets") or 0
        current_liab = g(bs_data, "totalCurrentLiabilities") or 0
        current_assets_prev = (g(bs_data, "totalCurrentAssets", 4) or 0)
        current_liab_prev = (g(bs_data, "totalCurrentLiabilities", 4) or 0)
        shares = g(bs_data, "commonStock") or g(inc_data, "weightedAverageShsOut")
        shares_prev = (g(bs_data, "commonStock", 4) or g(inc_data, "weightedAverageShsOut", 4))

        if not all([net_income, total_assets, ocf]):
            return None

        roa = net_income / total_assets if total_assets else 0
        roa_prev = (net_income_prev / total_assets_prev) if (net_income_prev and total_assets_prev) else None
        gm = (gross_profit / revenue) if (gross_profit and revenue) else None
        gm_prev = (gross_profit_prev / revenue_prev) if (gross_profit_prev and revenue_prev) else None
        asset_turn = (revenue / total_assets) if (revenue and total_assets) else None
        asset_turn_prev = (revenue_prev / total_assets_prev) if (revenue_prev and total_assets_prev) else None

        score = 0
        score += 1 if roa > 0 else 0                                           # F1
        score += 1 if ocf > 0 else 0                                            # F2
        score += 1 if (roa_prev is not None and roa > roa_prev) else 0          # F3
        score += 1 if (ocf / total_assets > roa) else 0                         # F4: accruals
        score += 1 if (total_assets_prev and lt_debt / total_assets <          # F5
                       lt_debt_prev / total_assets_prev) else 0
        cr = current_assets / current_liab if current_liab else 0
        cr_prev = current_assets_prev / current_liab_prev if current_liab_prev else 0
        score += 1 if cr > cr_prev else 0                                        # F6
        score += 1 if (shares_prev and (shares or 0) <= shares_prev * 1.02) else 0  # F7
        score += 1 if (gm and gm_prev and gm > gm_prev) else 0                  # F8
        score += 1 if (asset_turn and asset_turn_prev and                        # F9
                       asset_turn > asset_turn_prev) else 0

        return score

    except Exception as e:
        logger.debug(f"Piotroski computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Estimate revision direction (FMP analyst estimates)
# ---------------------------------------------------------------------------

async def _get_eps_revision_direction(symbol: str) -> dict:
    """
    Compare current FMP analyst EPS consensus to 4 weeks ago.
    Returns {revision_pct, direction: 'up'|'down'|'flat', count}.
    """
    if not settings.FMP_API_KEY:
        return {}

    cache_key = f"fmp_revision:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/analyst-estimates/{symbol}",
                params={"period": "annual", "limit": 4, "apikey": settings.FMP_API_KEY},
            )
            data = resp.json()

        if not isinstance(data, list) or not data:
            return {}

        current = data[0]
        est_eps_avg = _safe_float(current.get("estimatedEpsAvg"))
        est_eps_high = _safe_float(current.get("estimatedEpsHigh"))
        analyst_count = int(current.get("numberAnalysts") or 0)

        if est_eps_avg is None:
            return {}

        result = {
            "forward_eps_estimate": round(est_eps_avg, 4),
            "forward_eps_high": round(est_eps_high, 4) if est_eps_high else None,
            "analyst_count": analyst_count,
        }

        # Check for revision vs prior period estimate if available
        if len(data) >= 2:
            prior_eps = _safe_float(data[1].get("estimatedEpsAvg"))
            if prior_eps and prior_eps != 0:
                rev_pct = (est_eps_avg - prior_eps) / abs(prior_eps)
                result["eps_revision_pct"] = round(rev_pct, 4)
                result["eps_revision_direction"] = (
                    "up" if rev_pct > 0.03 else "down" if rev_pct < -0.03 else "flat"
                )

        import orjson
        await cache_set(cache_key, orjson.dumps(result).decode(), ttl=21600)  # 6h
        return result

    except Exception as e:
        logger.debug(f"FMP estimate revision failed for {symbol}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"
    summary_parts = []

    # ── yfinance: fast fundamentals (PE, short interest, market cap) ────────
    # yfinance replaces Alpha Vantage for overview data — free, unlimited, no key
    yf_info: dict = {}
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        yf_info = info
    except Exception as e:
        logger.debug(f"yfinance info failed for {symbol}: {e}")

    if yf_info:
        pe_val = _safe_float(yf_info.get("trailingPE") or yf_info.get("forwardPE"))
        if pe_val:
            signals.append({"name": "pe_ratio", "value": round(pe_val, 1)})
            if 0 < pe_val < 20:
                score += 0.5
                signals.append({"name": "low_pe", "value": pe_val, "direction": "value"})
            elif pe_val > 50:
                signals.append({"name": "high_pe", "value": pe_val, "note": "Growth premium"})

        rev_growth = _safe_float(yf_info.get("revenueGrowth"))
        if rev_growth is not None:
            signals.append({"name": "revenue_growth_yoy", "value": round(rev_growth * 100, 1)})
            if rev_growth > 0.20:
                score += 1.0
                direction = "bullish"
                signals.append({"name": "strong_revenue_growth", "direction": "bullish"})
            elif rev_growth < -0.05:
                score -= 0.5
                signals.append({"name": "declining_revenue", "direction": "bearish"})

        eps_growth = _safe_float(yf_info.get("earningsGrowth"))
        if eps_growth is not None:
            signals.append({"name": "eps_growth_yoy", "value": round(eps_growth * 100, 1)})
            if eps_growth > 0.20:
                score += 0.5
                signals.append({"name": "strong_eps_growth", "direction": "bullish"})

        short_pct = _safe_float(yf_info.get("shortPercentOfFloat"))
        if short_pct is not None and short_pct > 0.10:
            score += 0.5
            signals.append({"name": "high_short_interest", "value": round(short_pct * 100, 1),
                             "note": "Squeeze potential"})

    # ── FMP: deep financials (Piotroski, revenue accel, gross margin, FCF) ────
    fmp = await _get_fmp_financials(symbol)
    inc_data = fmp.get("income", [])
    bs_data = fmp.get("balance", [])
    cf_data = fmp.get("cashflow", [])

    # Revenue acceleration
    rev_metrics = _compute_revenue_acceleration(inc_data)
    if rev_metrics:
        qoq = rev_metrics.get("revenue_qoq")
        if qoq is not None:
            signals.append({"name": "revenue_qoq", "value": round(qoq * 100, 1)})
            if rev_metrics.get("revenue_accelerating"):
                score += 1.0
                direction = "bullish"
                signals.append({"name": "revenue_accelerating", "direction": "bullish"})
                summary_parts.append(f"Rev accel: QoQ={qoq*100:.1f}%+")
            elif rev_metrics.get("revenue_decelerating"):
                score -= 0.5
                signals.append({"name": "revenue_decelerating", "direction": "bearish"})

    # Gross margin trend
    gm_metrics = _compute_gross_margin_trend(inc_data)
    if gm_metrics:
        gm = gm_metrics.get("gross_margin_latest")
        if gm is not None:
            signals.append({"name": "gross_margin", "value": round(gm * 100, 1)})
        if gm_metrics.get("gross_margin_expanding"):
            score += 0.5
            signals.append({"name": "gross_margin_expanding", "direction": "bullish"})
        elif gm_metrics.get("gross_margin_compressing"):
            score -= 0.5
            signals.append({"name": "gross_margin_compressing", "direction": "bearish"})

    # FCF
    fcf_metrics = _compute_fcf_yield(cf_data, inc_data, symbol)
    if fcf_metrics:
        if fcf_metrics.get("fcf_positive"):
            score += 0.5
            signals.append({"name": "positive_fcf", "direction": "bullish",
                             "value": round(fcf_metrics.get("ttm_fcf", 0) / 1e6, 1)})
        else:
            signals.append({"name": "negative_fcf", "direction": "bearish"})

    # Piotroski F-score
    piotroski = _compute_piotroski(inc_data, bs_data, cf_data)
    if piotroski is not None:
        signals.append({"name": "piotroski_fscore", "value": piotroski})
        if piotroski >= 8:
            score += 1.5
            direction = "bullish"
            signals.append({"name": "piotroski_high", "direction": "bullish",
                             "note": f"F-score={piotroski}/9 — strong financial quality"})
            summary_parts.append(f"Piotroski={piotroski}/9")
        elif piotroski >= 5:
            score += 0.5
        elif piotroski <= 3:
            score -= 1.0
            signals.append({"name": "piotroski_low", "direction": "bearish",
                             "note": f"F-score={piotroski}/9 — financial quality concerns"})

    # ── Analyst consensus gap (FMP) ───────────────────────────────────────────
    try:
        from data.analyst_targets import get_consensus_gap
        consensus = await get_consensus_gap(symbol)
        if consensus:
            upside = consensus.get("upside_pct", 0)
            signals.append({"name": "analyst_upside_pct", "value": round(upside, 1)})
            if upside > 20:
                score += 1.5
                direction = "bullish"
                signals.append({"name": "strong_analyst_consensus", "direction": "bullish",
                               "note": f"{round(upside,1)}% upside to consensus target"})
                summary_parts.append(f"Analyst upside={upside:.0f}%")
            elif upside < -10:
                score -= 1
                signals.append({"name": "downside_risk_analyst", "direction": "bearish"})
    except Exception:
        pass

    # ── EPS revision direction ────────────────────────────────────────────────
    revision = await _get_eps_revision_direction(symbol)
    if revision:
        rev_dir = revision.get("eps_revision_direction")
        if rev_dir == "up":
            score += 1.0
            signals.append({"name": "eps_revision_up", "direction": "bullish",
                             "value": round(revision.get("eps_revision_pct", 0) * 100, 1),
                             "note": "Analysts raising EPS estimates"})
            summary_parts.append("EPS revisions↑")
        elif rev_dir == "down":
            score -= 1.0
            signals.append({"name": "eps_revision_down", "direction": "bearish",
                             "note": "Analysts cutting EPS estimates"})

    # ── Final scoring ─────────────────────────────────────────────────────────
    score = max(0.0, min(10.0, score))

    bull_sigs = sum(1 for s in signals if s.get("direction") == "bullish")
    bear_sigs = sum(1 for s in signals if s.get("direction") == "bearish")
    if bull_sigs > bear_sigs + 1:
        direction = "bullish"
    elif bear_sigs > bull_sigs + 1:
        direction = "bearish"

    summary = " | ".join(summary_parts) if summary_parts else (
        f"PE={yf_info.get('trailingPE','N/A')}, Rev growth={yf_info.get('revenueGrowth','N/A')}"
    )

    weight = 8.0
    return CategoryScore("fundamental", weight, score, weight * score / 10, direction, signals, summary)
