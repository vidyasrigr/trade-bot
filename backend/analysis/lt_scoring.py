"""
Long-Term Investment Composite Scorer (0-100).

Scores a stock across 4 layers grounded in academic and institutional research:
  Valuation     (25 pts): FCF yield, PEG, P/E vs own 5yr mean
  Growth Quality (30 pts): Revenue acceleration, gross margin trend, estimate revisions
  Financial Quality (25 pts): Piotroski F-score, FCF conversion, gross margin vs peers
  Moat Proxy    (20 pts): ROIC vs WACC, Rule of 40 (SaaS), insider ownership

Gate thresholds:
  < 40  → Block bullish options entries on this stock
  40-65 → Neutral (technicals decide)
  > 65  → Long candidate
  > 75 + IVR < 30 → LEAPS candidate
  Holding + IVR > 60 → Covered call opportunity
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


@dataclass
class LTScore:
    symbol: str
    total_score: float = 0.0
    tier: str = "neutral"          # 'leaps_candidate', 'long', 'neutral', 'blocked'

    # Layer scores (raw points, not normalized)
    valuation_pts: float = 0.0     # max 25
    growth_pts: float = 0.0        # max 30
    quality_pts: float = 0.0       # max 25
    moat_pts: float = 0.0          # max 20

    # Component details for UI breakdown
    fcf_yield: float | None = None
    peg_ratio: float | None = None
    pe_vs_5yr_mean: float | None = None   # current P/E / 5yr mean P/E
    revenue_acceleration: str = "unknown"  # 'accelerating', 'flat', 'decelerating'
    gross_margin_trend: str = "unknown"    # 'expanding', 'flat', 'compressing'
    eps_revision_dir: str = "flat"         # 'up', 'down', 'flat'
    piotroski: int | None = None
    roic: float | None = None
    rule_of_40: float | None = None
    insider_ownership: float | None = None
    accruals_ratio: float | None = None

    # Sell trigger status
    sell_triggers_active: list[str] = field(default_factory=list)

    # Context flags
    leaps_candidate: bool = False
    covered_call_opportunity: bool = False   # populated externally when IVR > 60

    # Tranche buy levels (populated when score > 65)
    tranche_levels: dict[str, float | None] = field(default_factory=dict)

    quality_momentum_tier: int = 0   # 1=both, 2=quality only, 3=momentum only, 0=neither
    sector_phase_multiplier: float = 1.0
    data_confidence: str = "low"     # 'high', 'medium', 'low'


# ---------------------------------------------------------------------------
# FMP data loader (re-uses cached data from fundamental.py pattern)
# ---------------------------------------------------------------------------

async def _fmp_get(endpoint: str, params: dict, cache_key: str, ttl: int = 86400) -> Any:
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        return orjson.loads(cached)

    if not settings.FMP_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/{endpoint}",
                params={**params, "apikey": settings.FMP_API_KEY},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()

        import orjson
        await cache_set(cache_key, orjson.dumps(data).decode(), ttl=ttl)
        return data
    except Exception as e:
        logger.debug(f"FMP {endpoint} failed: {e}")
        return None


def _sf(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Layer 1: Valuation (25 pts)
# ---------------------------------------------------------------------------

def _score_valuation(
    fcf_yield: float | None,
    peg: float | None,
    pe_current: float | None,
    pe_5yr_mean: float | None,
) -> tuple[float, dict]:
    pts = 0.0
    detail: dict[str, Any] = {}

    # FCF Yield (10 pts)
    if fcf_yield is not None:
        detail["fcf_yield_pct"] = round(fcf_yield * 100, 2)
        if fcf_yield > 0.06:
            pts += 10
        elif fcf_yield > 0.04:
            pts += 7
        elif fcf_yield > 0.02:
            pts += 4
        elif fcf_yield > 0:
            pts += 1

    # PEG Ratio (10 pts)
    if peg is not None and peg > 0:
        detail["peg_ratio"] = round(peg, 2)
        if peg < 1.0:
            pts += 10
        elif peg < 1.5:
            pts += 8
        elif peg < 2.5:
            pts += 5
        else:
            pts += 2

    # P/E vs own 5yr mean (5 pts)
    if pe_current and pe_5yr_mean and pe_5yr_mean > 0:
        pe_ratio = pe_current / pe_5yr_mean
        detail["pe_vs_5yr_mean"] = round(pe_ratio, 2)
        if pe_ratio < 1.0:
            pts += 5
        elif pe_ratio < 1.3:
            pts += 3
        elif pe_ratio > 1.5:
            pts += 0  # stretched valuation

    return min(pts, 25.0), detail


# ---------------------------------------------------------------------------
# Layer 2: Growth Quality (30 pts)
# ---------------------------------------------------------------------------

def _score_growth(
    rev_qoq: float | None,
    rev_prev_qoq: float | None,
    gm_latest: float | None,
    gm_prev: float | None,
    eps_rev_dir: str,
    eps_rev_pct: float | None,
) -> tuple[float, dict]:
    pts = 0.0
    detail: dict[str, Any] = {}

    # Revenue acceleration (10 pts)
    if rev_qoq is not None:
        detail["revenue_qoq_pct"] = round(rev_qoq * 100, 1)
        if rev_prev_qoq is not None:
            accel = rev_qoq - rev_prev_qoq
            detail["revenue_acceleration_pp"] = round(accel * 100, 2)
            if accel > 0.05:
                pts += 10
                detail["revenue_trend"] = "accelerating"
            elif accel > 0.02:
                pts += 7
                detail["revenue_trend"] = "slightly_accelerating"
            elif accel > -0.02:
                pts += 4
                detail["revenue_trend"] = "flat"
            else:
                pts += 0
                detail["revenue_trend"] = "decelerating"
        elif rev_qoq > 0.10:
            pts += 7

    # Gross margin trend (10 pts)
    if gm_latest is not None:
        detail["gross_margin_pct"] = round(gm_latest * 100, 1)
        if gm_prev is not None:
            gm_delta = gm_latest - gm_prev
            detail["gross_margin_delta_pp"] = round(gm_delta * 100, 2)
            if gm_delta > 0.02:
                pts += 10
                detail["gm_trend"] = "expanding"
            elif gm_delta > 0.005:
                pts += 7
                detail["gm_trend"] = "slightly_expanding"
            elif gm_delta > -0.005:
                pts += 5
                detail["gm_trend"] = "flat"
            else:
                pts += 0
                detail["gm_trend"] = "compressing"

    # EPS estimate revisions (10 pts)
    if eps_rev_dir == "up":
        rev_pct = eps_rev_pct or 0
        pts += 10 if rev_pct > 0.05 else 7
        detail["eps_revision"] = "up"
    elif eps_rev_dir == "flat":
        pts += 5
        detail["eps_revision"] = "flat"
    else:
        pts += 0
        detail["eps_revision"] = "down"

    return min(pts, 30.0), detail


# ---------------------------------------------------------------------------
# Layer 3: Financial Quality (25 pts)
# ---------------------------------------------------------------------------

def _score_quality(
    piotroski: int | None,
    fcf_to_earnings: float | None,
    gross_margin: float | None,
    peer_gross_margin: float | None,
    accruals_ratio: float | None,
) -> tuple[float, dict]:
    pts = 0.0
    detail: dict[str, Any] = {}

    # Piotroski F-score (15 pts)
    if piotroski is not None:
        detail["piotroski_fscore"] = piotroski
        if piotroski >= 8:
            pts += 15
        elif piotroski >= 5:
            pts += 8
        else:
            pts += 2

    # FCF / Earnings ratio (5 pts)
    if fcf_to_earnings is not None and fcf_to_earnings > 0:
        detail["fcf_to_earnings"] = round(fcf_to_earnings, 2)
        if fcf_to_earnings > 0.90:
            pts += 5
        elif fcf_to_earnings > 0.70:
            pts += 3
        else:
            pts += 1

    # Gross margin vs peers (5 pts) — simplified: use absolute level as proxy
    if gross_margin is not None:
        detail["gross_margin_pct"] = round(gross_margin * 100, 1)
        if peer_gross_margin:
            diff = gross_margin - peer_gross_margin
            if diff > 0.10:
                pts += 5
            elif diff > 0:
                pts += 2
        else:
            # No peer benchmark: use absolute thresholds (tech = typically 50%+)
            if gross_margin > 0.60:
                pts += 5
            elif gross_margin > 0.40:
                pts += 3
            elif gross_margin > 0.20:
                pts += 1

    # Accruals quality penalty (Sloan 1996)
    if accruals_ratio is not None:
        detail["accruals_ratio"] = round(accruals_ratio, 4)
        if accruals_ratio > 0.10:
            pts -= 2  # poor earnings quality — cap deduction at 2pts

    return min(max(pts, 0.0), 25.0), detail


# ---------------------------------------------------------------------------
# Layer 4: Moat Proxy (20 pts)
# ---------------------------------------------------------------------------

def _score_moat(
    roic: float | None,
    wacc_proxy: float = 0.10,  # default WACC estimate (10% = industry standard)
    rule_of_40: float | None = None,
    insider_ownership: float | None = None,
) -> tuple[float, dict]:
    pts = 0.0
    detail: dict[str, Any] = {}

    # ROIC vs WACC spread (10 pts)
    if roic is not None:
        detail["roic_pct"] = round(roic * 100, 1)
        spread = roic - wacc_proxy
        detail["roic_vs_wacc_spread_pp"] = round(spread * 100, 1)
        if spread > 0.10:
            pts += 10
        elif spread > 0.05:
            pts += 6
        elif spread > 0:
            pts += 3

    # Rule of 40 for SaaS / high-growth tech (5 pts)
    if rule_of_40 is not None:
        detail["rule_of_40"] = round(rule_of_40, 1)
        if rule_of_40 > 60:
            pts += 5
        elif rule_of_40 > 40:
            pts += 3
        elif rule_of_40 > 20:
            pts += 1

    # Insider ownership (5 pts)
    if insider_ownership is not None:
        detail["insider_ownership_pct"] = round(insider_ownership * 100, 1)
        if insider_ownership > 0.15:
            pts += 5
        elif insider_ownership > 0.05:
            pts += 3
        else:
            pts += 1

    return min(pts, 20.0), detail


# ---------------------------------------------------------------------------
# Quality-Momentum Gate (multiplicative effect per AQR research)
# ---------------------------------------------------------------------------

def _quality_momentum_tier(
    quality_score: float,
    momentum_positive: bool,  # from technical analysis: is 6-month return positive?
    piotroski: int | None,
) -> int:
    """
    Tier 1: quality AND momentum confirmed → full conviction
    Tier 2: quality only → half position, wait for momentum
    Tier 3: momentum only → half position, wait for quality
    Tier 0: neither
    """
    quality_ok = quality_score >= 13 or (piotroski is not None and piotroski >= 7)
    if quality_ok and momentum_positive:
        return 1
    if quality_ok and not momentum_positive:
        return 2
    if not quality_ok and momentum_positive:
        return 3
    return 0


# ---------------------------------------------------------------------------
# Sector phase multiplier (ISM PMI routing)
# ---------------------------------------------------------------------------

async def _get_sector_phase_multiplier(sector: str) -> float:
    """
    Applies sector rotation adjustment based on ISM PMI regime.
    From macro.py's ISM data. Returns a multiplier (0.85-1.10).
    """
    try:
        from data.macro import get_macro_snapshot
        macro = await get_macro_snapshot()
        ism = macro.get("ism_pmi")
        if not ism:
            return 1.0

        ism = float(ism)
        sector_lower = (sector or "").lower()

        if ism > 52:
            # Overweight industrials/materials/energy
            if any(x in sector_lower for x in ["industrial", "material", "energy", "defense"]):
                return 1.10
            elif any(x in sector_lower for x in ["tech", "software", "semiconductor"]):
                return 1.00
            else:
                return 0.95
        elif ism >= 50:
            # Stable: tech, healthcare, financials
            if any(x in sector_lower for x in ["tech", "software", "semi", "healthcare", "finance"]):
                return 1.05
            else:
                return 1.00
        else:
            # ISM < 50: rotate to defensives
            if any(x in sector_lower for x in ["staples", "utilities", "healthcare"]):
                return 1.05
            elif any(x in sector_lower for x in ["tech", "software", "semi", "industrial"]):
                return 0.85
            else:
                return 1.00
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# Tranche buy levels
# ---------------------------------------------------------------------------

def _compute_tranche_levels(current_price: float, high_52w: float | None) -> dict[str, float | None]:
    """Compute standard tranche entry levels for LT long candidates."""
    if not current_price or current_price <= 0:
        return {}

    if high_52w and high_52w > 0:
        fib_382 = high_52w - 0.382 * high_52w
        fib_50 = high_52w * 0.50
        fib_618 = high_52w * (1 - 0.618)
        return {
            "t1": round(current_price, 2),
            "t2": round(current_price * 0.95, 2),     # ~5% pullback / EMA50 proxy
            "t3": round(fib_382, 2),
            "t4": round(fib_50, 2),
            "stop": round(fib_618, 2),
        }
    else:
        return {
            "t1": round(current_price, 2),
            "t2": round(current_price * 0.95, 2),
            "t3": round(current_price * 0.88, 2),
            "t4": round(current_price * 0.80, 2),
            "stop": round(current_price * 0.75, 2),
        }


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

async def score_stock(
    symbol: str,
    sector: str = "",
    current_price: float | None = None,
    momentum_positive: bool = True,
    ivr: float | None = None,
    high_52w: float | None = None,
) -> LTScore:
    """
    Compute full LT score for a symbol.
    Fetches all needed FMP data internally.
    """
    cache_key = f"lt_score:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        d = orjson.loads(cached)
        return LTScore(**d)

    lt = LTScore(symbol=symbol)

    # ── Parallel FMP data fetch ───────────────────────────────────────────────
    tasks = [
        _fmp_get(f"v3/income-statement/{symbol}", {"period": "quarter", "limit": 8},
                 f"lt_inc:{symbol}"),
        _fmp_get(f"v3/balance-sheet-statement/{symbol}", {"period": "quarter", "limit": 8},
                 f"lt_bs:{symbol}"),
        _fmp_get(f"v3/cash-flow-statement/{symbol}", {"period": "quarter", "limit": 8},
                 f"lt_cf:{symbol}"),
        _fmp_get(f"v3/key-metrics/{symbol}", {"period": "annual", "limit": 5},
                 f"lt_km:{symbol}"),
        _fmp_get(f"v3/analyst-estimates/{symbol}", {"period": "annual", "limit": 2},
                 f"lt_ae:{symbol}"),
        _fmp_get(f"v4/insider-trading", {"symbol": symbol, "limit": 20},
                 f"lt_it:{symbol}", ttl=86400 * 3),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    inc_data = results[0] if isinstance(results[0], list) else []
    bs_data = results[1] if isinstance(results[1], list) else []
    cf_data = results[2] if isinstance(results[2], list) else []
    km_data = results[3] if isinstance(results[3], list) else []
    ae_data = results[4] if isinstance(results[4], list) else []
    insider_data = results[5] if isinstance(results[5], list) else []

    # ── Extract metrics ───────────────────────────────────────────────────────

    # Key metrics (annual, most recent)
    km = km_data[0] if km_data else {}
    km_prev = km_data[1] if len(km_data) > 1 else {}

    roic = _sf(km.get("roic"))
    lt.roic = roic
    peg = _sf(km.get("priceToEarningsRatio")) or None  # FMP key-metrics has PE, not PEG directly

    # PEG from analyst estimates
    if ae_data and ae_data[0]:
        forward_eps = _sf(ae_data[0].get("estimatedEpsAvg"))
        if forward_eps and forward_eps > 0 and current_price:
            forward_pe = current_price / forward_eps
            # Approximate PEG: forward PE / expected EPS growth (use rev growth as proxy if no EPS growth)
            if len(ae_data) >= 2:
                eps_prev = _sf(ae_data[1].get("estimatedEpsAvg"))
                if eps_prev and eps_prev > 0:
                    eps_growth_rate = (forward_eps - eps_prev) / eps_prev * 100
                    if eps_growth_rate > 0:
                        peg = round(forward_pe / eps_growth_rate, 2)

    lt.peg_ratio = peg

    # FCF yield
    ttm_fcf = 0.0
    for q in cf_data[:4]:
        ocf = _sf(q.get("operatingCashFlow")) or 0
        capex = abs(_sf(q.get("capitalExpenditure")) or 0)
        ttm_fcf += ocf - capex

    mkt_cap = _sf(km.get("marketCap"))
    fcf_yield = (ttm_fcf / mkt_cap) if (mkt_cap and mkt_cap > 0 and ttm_fcf) else None
    lt.fcf_yield = fcf_yield

    # P/E vs own 5yr mean
    pe_vals = [_sf(k.get("priceEarningsRatio")) for k in km_data if _sf(k.get("priceEarningsRatio"))]
    pe_current = pe_vals[0] if pe_vals else None
    pe_5yr_mean = (sum(pe_vals[:5]) / len(pe_vals[:5])) if len(pe_vals) >= 3 else None
    lt.pe_vs_5yr_mean = round(pe_current / pe_5yr_mean, 2) if (pe_current and pe_5yr_mean) else None

    # Revenue QoQ
    revenues = [_sf(q.get("revenue")) for q in inc_data if _sf(q.get("revenue"))]
    rev_qoq = None
    rev_prev_qoq = None
    if len(revenues) >= 3:
        rev_qoq = (revenues[0] - revenues[1]) / revenues[1] if revenues[1] else None
        rev_prev_qoq = (revenues[1] - revenues[2]) / revenues[2] if revenues[2] else None
        if rev_qoq is not None:
            lt.revenue_acceleration = (
                "accelerating" if (rev_prev_qoq and rev_qoq > rev_prev_qoq) else
                "decelerating" if (rev_prev_qoq and rev_qoq < rev_prev_qoq - 0.03) else
                "flat"
            )

    # Gross margin
    gm_vals = []
    for q in inc_data[:4]:
        r = _sf(q.get("revenue")); gp = _sf(q.get("grossProfit"))
        if r and r > 0 and gp is not None:
            gm_vals.append(gp / r)
    gm_latest = gm_vals[0] if gm_vals else None
    gm_prev = gm_vals[1] if len(gm_vals) > 1 else None
    lt.gross_margin_trend = (
        "expanding" if (gm_latest and gm_prev and gm_latest > gm_prev + 0.005) else
        "compressing" if (gm_latest and gm_prev and gm_latest < gm_prev - 0.005) else
        "flat"
    )

    # EPS revision
    eps_rev_dir = "flat"
    eps_rev_pct = None
    if len(ae_data) >= 2:
        cur_eps = _sf(ae_data[0].get("estimatedEpsAvg"))
        prev_eps = _sf(ae_data[1].get("estimatedEpsAvg"))
        if cur_eps and prev_eps and prev_eps != 0:
            eps_rev_pct = (cur_eps - prev_eps) / abs(prev_eps)
            eps_rev_dir = "up" if eps_rev_pct > 0.03 else "down" if eps_rev_pct < -0.03 else "flat"
    lt.eps_revision_dir = eps_rev_dir

    # Piotroski
    from analysis.fundamental import _compute_piotroski
    piotroski_score = _compute_piotroski(inc_data, bs_data, cf_data)
    lt.piotroski = piotroski_score

    # FCF to earnings ratio
    ttm_net_income = sum(_sf(q.get("netIncome")) or 0 for q in inc_data[:4])
    fcf_to_earnings = (ttm_fcf / ttm_net_income) if (ttm_net_income and ttm_net_income > 0) else None

    # Accruals ratio (Sloan 1996)
    ttm_ocf = sum(_sf(q.get("operatingCashFlow")) or 0 for q in cf_data[:4])
    total_assets = _sf(bs_data[0].get("totalAssets")) if bs_data else None
    accruals_ratio = None
    if total_assets and total_assets > 0 and ttm_net_income:
        accruals_ratio = (ttm_net_income - ttm_ocf) / total_assets
    lt.accruals_ratio = accruals_ratio

    # Rule of 40 (revenue growth % + operating margin %)
    rev_growth_yoy_pct = None
    if len(revenues) >= 5:
        rev_growth_yoy_pct = (revenues[0] - revenues[4]) / revenues[4] * 100 if revenues[4] else None
    op_margin_latest = None
    if inc_data:
        op_income = _sf(inc_data[0].get("operatingIncome"))
        rev = _sf(inc_data[0].get("revenue"))
        if op_income and rev and rev > 0:
            op_margin_latest = op_income / rev * 100
    if rev_growth_yoy_pct is not None and op_margin_latest is not None:
        lt.rule_of_40 = round(rev_growth_yoy_pct + op_margin_latest, 1)

    # ROIC from key metrics
    lt.roic = _sf(km.get("returnOnEquity"))  # FMP uses ROE, close proxy for ROIC

    # Insider ownership
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            profile_resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/profile/{symbol}",
                params={"apikey": settings.FMP_API_KEY},
            )
            profile = profile_resp.json()
            if isinstance(profile, list) and profile:
                lt.insider_ownership = _sf(profile[0].get("insidersOwnership"))
    except Exception:
        pass

    # ── Score each layer ──────────────────────────────────────────────────────
    val_pts, _ = _score_valuation(fcf_yield, peg, pe_current, pe_5yr_mean)
    grow_pts, _ = _score_growth(rev_qoq, rev_prev_qoq, gm_latest, gm_prev, eps_rev_dir, eps_rev_pct)
    qual_pts, _ = _score_quality(piotroski_score, fcf_to_earnings, gm_latest, None, accruals_ratio)
    moat_pts, _ = _score_moat(lt.roic, 0.10, lt.rule_of_40, lt.insider_ownership)

    lt.valuation_pts = val_pts
    lt.growth_pts = grow_pts
    lt.quality_pts = qual_pts
    lt.moat_pts = moat_pts
    lt.total_score = round(val_pts + grow_pts + qual_pts + moat_pts, 1)

    # Sector phase multiplier
    lt.sector_phase_multiplier = await _get_sector_phase_multiplier(sector)
    lt.total_score = round(lt.total_score * lt.sector_phase_multiplier, 1)
    lt.total_score = max(0.0, min(100.0, lt.total_score))

    # Quality-momentum gate
    lt.quality_momentum_tier = _quality_momentum_tier(qual_pts, momentum_positive, piotroski_score)

    # Tier classification
    if lt.total_score >= 75:
        lt.tier = "long"
        if ivr is not None and ivr < 30:
            lt.tier = "leaps_candidate"
            lt.leaps_candidate = True
    elif lt.total_score >= 65:
        lt.tier = "long"
    elif lt.total_score >= 40:
        lt.tier = "neutral"
    else:
        lt.tier = "blocked"

    # Covered call flag
    if lt.total_score >= 65 and ivr is not None and ivr > 60:
        lt.covered_call_opportunity = True

    # Tranche levels
    if lt.total_score >= 65 and current_price:
        lt.tranche_levels = _compute_tranche_levels(current_price, high_52w)

    # Data confidence
    data_points = sum([
        1 if piotroski_score is not None else 0,
        1 if fcf_yield is not None else 0,
        1 if rev_qoq is not None else 0,
        1 if peg is not None else 0,
        1 if lt.roic is not None else 0,
    ])
    lt.data_confidence = "high" if data_points >= 4 else "medium" if data_points >= 2 else "low"

    # Cache for 6 hours
    import orjson
    import dataclasses
    await cache_set(cache_key, orjson.dumps(dataclasses.asdict(lt)).decode(), ttl=21600)

    logger.info(f"LT score {symbol}: {lt.total_score:.0f}/100 ({lt.tier}) "
                f"quality_tier={lt.quality_momentum_tier}")
    return lt


def format_lt_context(lt: LTScore) -> str:
    """Format LT score for injection into Claude's analysis context."""
    lines = [
        f"[{lt.symbol} Long-Term Score: {lt.total_score:.0f}/100 — {lt.tier.upper()}]",
        f"Valuation={lt.valuation_pts:.0f}/25, Growth={lt.growth_pts:.0f}/30, "
        f"Quality={lt.quality_pts:.0f}/25, Moat={lt.moat_pts:.0f}/20",
    ]

    if lt.piotroski is not None:
        lines.append(f"Piotroski F-score: {lt.piotroski}/9")
    if lt.fcf_yield is not None:
        lines.append(f"FCF yield: {lt.fcf_yield*100:.1f}%")
    if lt.peg_ratio is not None:
        lines.append(f"PEG ratio: {lt.peg_ratio:.1f}x")
    if lt.eps_revision_dir != "flat":
        lines.append(f"EPS revision: {lt.eps_revision_dir}")
    if lt.accruals_ratio is not None and lt.accruals_ratio > 0.05:
        lines.append(f"⚠ Accruals ratio {lt.accruals_ratio:.3f} — earnings quality concern")
    if lt.tier == "blocked":
        lines.append("⛔ LT score < 40 — bullish options blocked for this stock")
    if lt.leaps_candidate:
        lines.append("⭐ LEAPS candidate (score >75, IVR <30)")
    if lt.covered_call_opportunity:
        lines.append("💰 Covered call opportunity (score >65, IVR >60)")
    if lt.quality_momentum_tier == 1:
        lines.append("✅ Quality + Momentum both confirmed — FULL conviction sizing")
    elif lt.quality_momentum_tier == 2:
        lines.append("⚠ Quality confirmed but momentum not yet — half position until momentum confirms")
    elif lt.quality_momentum_tier == 3:
        lines.append("⚠ Momentum confirmed but quality not yet — half position until quality confirms")

    return "\n".join(lines)
