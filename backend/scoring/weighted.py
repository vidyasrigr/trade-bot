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
    "catalyst_specific":  ["calendar"],
    "risk_liquidity":     ["liquidity", "risk"],
}

# Category weight base table (same as engine.py — kept in sync)
BASE_WEIGHTS = {
    "macro":              6.0,
    "calendar":           6.0,
    "fundamental":        7.0,
    "trend":              9.0,
    "support_resistance": 7.0,
    "candles":            5.0,
    "chart_patterns":     6.0,
    "momentum":           6.0,
    "iv_analysis":       11.0,
    "options_chain":      9.0,
    "greeks":             8.0,
    "trade_structure":    5.0,
    "sentiment":          5.0,
    "liquidity":          5.0,
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

    # P0 Stage 1.5 — runtime kill-switch. Read the operating mode once; any signal
    # below the mode's promotion threshold contributes 0 (not just downweighted),
    # so sandboxed/proposed experimental signals cannot leak into conviction.
    from scoring.signal_registry import contributes_in_mode
    _mode = getattr(settings, "OPERATING_MODE", "paper")
    _blocked_signals: list[str] = []

    for key, cat in category_scores.items():
        if not contributes_in_mode(key, _mode):
            adjusted_scores[key] = 0.0
            weight_adjustments[key] = 0.0
            _blocked_signals.append(key)
            continue
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

    if _blocked_signals:
        warnings.append(
            f"Mode '{_mode}': {len(_blocked_signals)} signal(s) below promotion threshold "
            f"contributed 0 — {', '.join(sorted(_blocked_signals))}"
        )

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

    # 5. Count independent signal groups that fired (score > 5 = firing).
    # 0620.3 Phase 4.2: a signal blocked by mode/ledger contributes 0 to score, so it
    # must NOT count toward the independent-confirmation gate either. Exclude blocked.
    _blocked_set = set(_blocked_signals)
    independent_count = 0
    for group_name, group_cats in INDEPENDENT_GROUPS.items():
        group_scores = [category_scores[c].raw_score for c in group_cats
                        if c in category_scores and c not in _blocked_set]
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

    # 7. Conviction-multiplier sizing (Phase I.1).
    # Half-Kelly is the default policy because it gives ~75% of full-Kelly
    # compounding growth at ~50% the drawdown. But when the system identifies a
    # *genuinely* stacked setup — 5+ independent signal groups firing AND a tail
    # signal aligned (insider cluster, VRP-z>+1, or whale sweep) — that's where
    # the 2-5x trades live. We tier the Kelly fraction by stacking count:
    #     3-4 groups          → half-Kelly  (current behavior)
    #     5 groups            → 0.75 Kelly
    #     6+ groups + tail    → full Kelly  (subject to MAX_POSITION_SIZE_PCT cap)
    # 0620.3 Phase 4.2: tail-alignment must also ignore blocked signals.
    _unblocked_cats = {k: v for k, v in category_scores.items() if k not in _blocked_set}
    tail_aligned = _detect_tail_alignment(_unblocked_cats)
    account = account_value or portfolio_value or settings.PAPER_PORTFOLIO_VALUE
    position_size_pct, suggested_contracts, kelly_used = _kelly_size(
        conviction_score=conviction_score,
        portfolio_value=account,
        confirmation_met=confirmation_met,
        independent_signals_count=independent_count,
        tail_signal_aligned=tail_aligned,
    )
    if kelly_used > settings.KELLY_FRACTION + 1e-6:
        warnings.append(
            f"CONVICTION_STACK: {independent_count} independent groups firing"
            f"{' + tail signal aligned' if tail_aligned else ''} → "
            f"Kelly fraction lifted to {kelly_used:.2f} (default {settings.KELLY_FRACTION:.2f})"
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


def _detect_tail_alignment(category_scores: dict) -> bool:
    """
    A "tail" signal is one whose firing has historically preceded outsized
    moves: deep variance risk premium, insider cluster buying, or institutional
    whale sweep. When one of these is aligned with strong overall conviction,
    the system has more reason to believe this isn't an average setup.

    We look at the raw signals embedded in each category:
      - iv_analysis: vrp_z >= +1 (rich premium)  OR  vrp_z <= -1 (cheap premium)
      - sentiment / options_flow: 'whale_sweep' or 'insider_cluster' name found
      - macro: 'pre_fomc_gate_passed' (Lucca-Moench drift window)
    """
    def _signals_for(cat_name: str) -> list[dict]:
        cat = category_scores.get(cat_name)
        if cat is None:
            return []
        return getattr(cat, "signals", []) or []

    for sig in _signals_for("iv_analysis"):
        if sig.get("name") in ("vrp_z", "iv_premium", "iv_discount"):
            try:
                z = abs(float(sig.get("z_score", sig.get("value", 0))))
                if z >= 1.0:
                    return True
            except (TypeError, ValueError):
                continue
    for cat_name in ("sentiment", "options_flow"):
        for sig in _signals_for(cat_name):
            name = (sig.get("name") or "").lower()
            if name in {"whale_sweep", "insider_cluster", "unusual_call_volume",
                         "unusual_put_volume", "call_flow_dominant"}:
                return True
    for sig in _signals_for("macro"):
        if sig.get("name") == "pre_fomc_gate_passed" and sig.get("value"):
            return True
    return False


def _choose_kelly_fraction(independent_signals_count: int, tail_signal_aligned: bool) -> float:
    """
    Tiered Kelly fraction (Phase I.1 — conviction multiplier).

      <= 4 groups               → settings.KELLY_FRACTION (half-Kelly default)
      = 5 groups                → midpoint between half-Kelly and full
      >= 6 groups + tail signal → full Kelly (clamped at 1.0)
      >= 6 groups, no tail      → 0.75 Kelly (still bumped, but cautiously)
    """
    base = float(settings.KELLY_FRACTION)
    cap = float(getattr(settings, "KELLY_FRACTION_MAX", 0.25))
    # 0620.3 Phase 4.3: the conviction-stack LIFT is DISABLED until paper calibration.
    # No matter how many groups fire, the fraction stays at base (tenth-Kelly), hard-capped.
    if not getattr(settings, "KELLY_LIFT_ENABLED", False):
        return min(base, cap)
    # (legacy lift path, only if explicitly re-enabled)
    if independent_signals_count <= 4:
        return min(base, cap)
    if independent_signals_count == 5:
        return min(cap, base + (cap - base) * 0.5)
    if independent_signals_count >= 6 and tail_signal_aligned:
        return cap
    return min(cap, base + (cap - base) * 0.5)


def _kelly_size(
    conviction_score: float,
    portfolio_value: float,
    confirmation_met: bool,
    independent_signals_count: int = 0,
    tail_signal_aligned: bool = False,
    option_price: float = 2.50,
) -> tuple[float, int, float]:
    """
    Conviction-scaled Kelly position sizing.

    Returns (position_size_pct, suggested_contracts, kelly_fraction_used).

    Default = half-Kelly (settings.KELLY_FRACTION). Stacked-signal trades lift
    the Kelly fraction up to full when 6+ independent groups fire AND a tail
    signal aligns. The MAX_POSITION_SIZE_PCT cap is enforced regardless — so
    even at full Kelly, no single trade exceeds the portfolio cap.
    """
    if not confirmation_met or conviction_score < 60:
        return (0.0, 0, 0.0)

    # Conviction 60-100 → position size 1.0-4.0% of portfolio (pre-Kelly scaling)
    normalized_conviction = (conviction_score - 60) / 40  # 0.0 to 1.0
    raw_pct = settings.BASE_POSITION_SIZE_PCT + (
        normalized_conviction * (settings.MAX_POSITION_SIZE_PCT - settings.BASE_POSITION_SIZE_PCT)
    )

    kelly_fraction = _choose_kelly_fraction(independent_signals_count, tail_signal_aligned)
    kelly_scaled_pct = raw_pct * kelly_fraction
    kelly_scaled_pct = round(min(kelly_scaled_pct, settings.MAX_POSITION_SIZE_PCT), 4)

    dollar_risk = portfolio_value * kelly_scaled_pct
    contracts = max(1, round(dollar_risk / (option_price * 100)))
    contracts = min(contracts, 10)  # hard cap

    return (kelly_scaled_pct, contracts, kelly_fraction)


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
