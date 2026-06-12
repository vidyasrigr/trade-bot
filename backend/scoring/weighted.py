"""
Weighted scoring with IC adjustments, 3-signal confirmation gate, anti-crowding,
and Kelly-based position sizing.

This module takes raw category scores from analysis/engine.py and:
1. Applies regime-conditional IC multipliers from ic_tracker
2. Enforces 3-independent-signal minimum gate
3. Applies anti-crowding discount
4. Computes conviction-scaled half-Kelly position size
"""

from dataclasses import dataclass
from loguru import logger

from core.config import settings


# Category independence groups — signals within a group are correlated.
# Count at most ONE vote per group toward the 3-signal minimum.
# This prevents RSI + MACD + Stochastic all counting as separate signals.
INDEPENDENT_GROUPS = {
    "momentum_technical": ["momentum", "candles", "chart_patterns"],
    "trend_structural":   ["trend", "support_resistance"],
    "volatility":         ["iv_analysis", "earnings_adj_iv", "volatility_regime"],
    "options_specific":   ["options_chain", "greeks", "trade_structure"],
    "flow_and_sentiment": ["sentiment", "options_flow", "gex_dex"],
    "fundamental_macro":  ["fundamental", "macro"],
    "catalyst_specific":  ["calendar", "dow_bias"],
    "risk_liquidity":     ["liquidity", "risk"],
}

# Category weight base table (same as engine.py — kept in sync)
BASE_WEIGHTS = {
    "macro":              8.0,
    "calendar":           7.0,
    "fundamental":        8.0,
    "trend":             10.0,
    "support_resistance": 8.0,
    "candles":            7.0,
    "chart_patterns":     7.0,
    "momentum":           7.0,
    "iv_analysis":       12.0,
    "options_chain":     10.0,
    "greeks":             8.0,
    "trade_structure":    5.0,
    "sentiment":          5.0,
    "liquidity":          5.0,
    "dow_bias":           4.0,
    "risk":               5.0,
    "gex_dex":            0.0,   # overlaid on top of sentiment
    "options_flow":       0.0,   # overlaid on top of sentiment
    "volatility_regime":  0.0,   # overlaid on top of iv_analysis
    "earnings_adj_iv":    0.0,   # overlaid on top of iv_analysis
}


@dataclass
class ScoringResult:
    total_score: float                    # 0–100
    conviction_score: float               # 0–100 (stricter — requires confirmation)
    direction: str                        # bullish / bearish / neutral
    independent_signals_count: int        # how many independent groups fired
    confirmation_met: bool                # >= MIN_SIGNALS_REQUIRED independent groups
    crowding_applied: bool
    crowding_discount: float
    position_size_pct: float              # % of portfolio (Kelly-scaled)
    suggested_contracts: int
    warnings: list[str]
    weight_adjustments: dict[str, float]  # category → applied multiplier


async def compute_final_score(
    symbol: str,
    category_scores: dict,
    vol_regime: str,
    influencer_mention_count: int = 0,
    portfolio_value: float | None = None,
    account_value: float | None = None,
    lt_score: float | None = None,         # from analysis/lt_scoring.py
    lt_tier: str | None = None,
) -> ScoringResult:
    """
    Main entry point: takes raw category scores, applies IC multipliers,
    enforces confirmation gate, returns final conviction + sizing.

    Args:
        symbol: Stock symbol
        category_scores: Dict of CategoryScore from analysis/engine
        vol_regime: Current regime (bull_trend/bear_trend/chop/high_vol)
        influencer_mention_count: How many YouTube/social channels mentioned this week
        portfolio_value: For position sizing
        account_value: Override for portfolio value if available
    """
    warnings = []

    # 1. Fetch IC multipliers for this regime
    multipliers = await _get_ic_multipliers(vol_regime)

    # 2. Compute IC-adjusted weighted scores
    adjusted_scores = {}
    weight_adjustments = {}
    direction_votes: dict[str, float] = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}

    for key, cat in category_scores.items():
        base_weight = BASE_WEIGHTS.get(key, 5.0)
        ic_mult = multipliers.get(key, 1.0)

        # Cap multiplier to prevent any single factor dominating
        ic_mult = max(0.25, min(2.0, ic_mult))

        effective_weight = base_weight * ic_mult
        effective_score = (cat.raw_score / 10.0) * effective_weight

        adjusted_scores[key] = effective_score
        weight_adjustments[key] = round(ic_mult, 3)

        if cat.direction != "neutral":
            direction_votes[cat.direction] = direction_votes.get(cat.direction, 0) + effective_score

    raw_total = sum(adjusted_scores.values())

    # 3. Apply anti-crowding discount
    crowding_applied = False
    crowding_discount = 0.0
    if influencer_mention_count >= 5:
        crowding_discount = 0.20  # -20% as per plan
        crowding_applied = True
        warnings.append(f"Anti-crowding: {influencer_mention_count} channels mentioned — applying -20% discount")

    effective_total = raw_total * (1.0 - crowding_discount)
    total_score = round(min(effective_total, 100.0), 2)

    # 3b. LT score gate (from LT investment pipeline)
    # LT score < 40 blocks bullish options entries; >75 boosts conviction
    if lt_score is not None:
        if lt_tier == "blocked" or lt_score < 40:
            # Reduce score significantly for bullish direction
            effective_total *= 0.60
            total_score = round(min(effective_total, 100.0), 2)
            warnings.append(
                f"LT gate: score={lt_score:.0f} (<40) — bullish conviction reduced 40%. "
                "Underlying has poor fundamentals."
            )
        elif lt_score > 75:
            # Boost conviction when LT fundamentals are strong
            effective_total *= 1.10
            total_score = round(min(effective_total, 100.0), 2)

    # 4. Determine direction
    bull = direction_votes["bullish"]
    bear = direction_votes["bearish"]
    if bull > bear * 1.3:
        direction = "bullish"
    elif bear > bull * 1.3:
        direction = "bearish"
    else:
        direction = "neutral"

    # 5. Count independent signal groups that fired (score > 5 = firing)
    independent_count = 0
    for group_name, group_cats in INDEPENDENT_GROUPS.items():
        group_scores = [category_scores[c].raw_score for c in group_cats if c in category_scores]
        if group_scores and max(group_scores) > 5.5:
            independent_count += 1

    confirmation_met = independent_count >= settings.MIN_SIGNALS_REQUIRED

    if not confirmation_met:
        warnings.append(
            f"Only {independent_count}/{settings.MIN_SIGNALS_REQUIRED} independent signal groups firing "
            f"— below minimum confirmation threshold. Do not trade."
        )

    # 6. Conviction score (total + confirmation penalty if not met)
    conviction_score = total_score
    if not confirmation_met:
        # Heavy penalty — conviction below 60 blocks Alpha stream entries
        conviction_score = min(conviction_score, 55.0)
        conviction_score = round(conviction_score, 2)

    # 7. Half-Kelly position sizing
    account = account_value or portfolio_value or settings.PAPER_PORTFOLIO_VALUE
    position_size_pct, suggested_contracts = _kelly_size(
        conviction_score=conviction_score,
        portfolio_value=account,
        confirmation_met=confirmation_met,
    )

    return ScoringResult(
        total_score=total_score,
        conviction_score=conviction_score,
        direction=direction,
        independent_signals_count=independent_count,
        confirmation_met=confirmation_met,
        crowding_applied=crowding_applied,
        crowding_discount=crowding_discount,
        position_size_pct=position_size_pct,
        suggested_contracts=suggested_contracts,
        warnings=warnings,
        weight_adjustments=weight_adjustments,
    )


def _kelly_size(
    conviction_score: float,
    portfolio_value: float,
    confirmation_met: bool,
    option_price: float = 2.50,
) -> tuple[float, int]:
    """
    Half-Kelly position sizing scaled by conviction.
    Research: half-Kelly = 75% of optimal compounding growth with ~50% less drawdown vs full Kelly.
    """
    if not confirmation_met or conviction_score < 60:
        return (0.0, 0)

    # Conviction 60-100 → position size 1.0-4.0% of portfolio (half-Kelly scaled)
    normalized_conviction = (conviction_score - 60) / 40  # 0.0 to 1.0
    raw_pct = settings.BASE_POSITION_SIZE_PCT + (
        normalized_conviction * (settings.MAX_POSITION_SIZE_PCT - settings.BASE_POSITION_SIZE_PCT)
    )

    # Apply half-Kelly fraction
    kelly_scaled_pct = raw_pct * settings.KELLY_FRACTION
    kelly_scaled_pct = round(min(kelly_scaled_pct, settings.MAX_POSITION_SIZE_PCT), 4)

    # Derive suggested contracts
    dollar_risk = portfolio_value * kelly_scaled_pct
    contracts = max(1, round(dollar_risk / (option_price * 100)))
    contracts = min(contracts, 10)  # hard cap

    return (kelly_scaled_pct, contracts)


async def _get_ic_multipliers(regime: str) -> dict[str, float]:
    """Fetch IC multipliers from DB; fall back to defaults (1.0) if DB unavailable."""
    try:
        from scoring.ic_tracker import get_weight_multipliers
        return await get_weight_multipliers(regime)
    except Exception as e:
        logger.debug(f"IC multipliers unavailable, using defaults: {e}")
        return {}


def get_regime_for_symbol(category_scores: dict) -> str:
    """Extract vol_regime string from category score signals."""
    vr = category_scores.get("volatility_regime")
    if vr and vr.signals:
        for sig in vr.signals:
            if "regime" in sig:
                return sig["regime"]
    return "unknown"
