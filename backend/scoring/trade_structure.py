"""
DETERMINISTIC trade structure selector.
Input: vol_regime + iv_percentile + direction + total_score
Output: specific strategy, target strikes, DTE range, rationale.

Claude validates and explains — this engine makes the structural decision.
"""

from dataclasses import dataclass
from core.config import settings


@dataclass
class TradeStructureInput:
    vol_regime: str      # bull_trend | bear_trend | chop | high_vol
    iv_percentile: float # 0-100
    direction: str       # bullish | bearish | neutral
    total_score: float   # 0-100
    dte_preference: str = "swing"  # swing (14-21) | position (30-60)


@dataclass
class TradeStructure:
    strategy: str
    short_strike: str  # e.g., "0.16 delta OTM put" or "ATM"
    long_strike: str   # e.g., "0.05 delta OTM put" or "N/A"
    dte_min: int
    dte_max: int
    target_delta: float
    max_loss: str       # "defined" | "undefined"
    profit_target_pct: float  # % of max profit to close at
    direction: str
    rationale: str


def select_structure(inp: TradeStructureInput) -> TradeStructure:
    """
    Deterministic rule engine — maps regime/IV/direction → optimal structure.
    Based on tastytrade research + professional options mechanics.
    """
    dte_min = settings.SWING_DTE_MIN if inp.dte_preference == "swing" else settings.POSITION_DTE_MIN
    dte_max = settings.SWING_DTE_MAX if inp.dte_preference == "swing" else settings.POSITION_DTE_MAX

    # ================================================================
    # HIGH IV (> 60th percentile) → Sell premium
    # ================================================================
    if inp.iv_percentile > 60:

        if inp.vol_regime in ("chop", "high_vol") and inp.direction == "neutral":
            return TradeStructure(
                strategy="iron_condor",
                short_strike=f"0.16 delta OTM call and 0.16 delta OTM put",
                long_strike=f"5–10 points further OTM (wings)",
                dte_min=30, dte_max=45,
                target_delta=0.16,
                max_loss="defined",
                profit_target_pct=0.50,
                direction="neutral",
                rationale=f"IV at {inp.iv_percentile:.0f}th pct in chop/high-vol: iron condor collects elevated premium on both sides. Close at 50% max profit (~21 DTE).",
            )

        if inp.direction == "bullish":
            return TradeStructure(
                strategy="bull_put_spread",
                short_strike=f"0.30 delta OTM put (below support)",
                long_strike=f"5–10 points further OTM",
                dte_min=30, dte_max=45,
                target_delta=0.30,
                max_loss="defined",
                profit_target_pct=0.50,
                direction="bullish",
                rationale=f"High IV ({inp.iv_percentile:.0f}th pct) + bullish: sell put spread, collect theta, defined risk.",
            )

        if inp.direction == "bearish":
            return TradeStructure(
                strategy="bear_call_spread",
                short_strike=f"0.30 delta OTM call (above resistance)",
                long_strike=f"5–10 points further OTM",
                dte_min=30, dte_max=45,
                target_delta=0.30,
                max_loss="defined",
                profit_target_pct=0.50,
                direction="bearish",
                rationale=f"High IV ({inp.iv_percentile:.0f}th pct) + bearish: sell call spread, defined risk.",
            )

    # ================================================================
    # LOW IV (< 40th percentile) → Buy premium / directional
    # ================================================================
    elif inp.iv_percentile < 40:

        if inp.direction == "bullish":
            if inp.total_score > 75:
                return TradeStructure(
                    strategy="long_call",
                    short_strike="N/A",
                    long_strike=f"0.40–0.45 delta ATM call",
                    dte_min=dte_min, dte_max=dte_max,
                    target_delta=settings.DIRECTIONAL_DELTA,
                    max_loss="defined",
                    profit_target_pct=1.0,  # hold for full move
                    direction="bullish",
                    rationale=f"Low IV ({inp.iv_percentile:.0f}th pct) + strong bull signal (score {inp.total_score:.0f}): buy 0.40Δ call outright, cheap premium.",
                )
            else:
                return TradeStructure(
                    strategy="bull_call_spread",
                    short_strike=f"0.25 delta OTM call (resistance level)",
                    long_strike=f"0.40–0.45 delta ATM call",
                    dte_min=dte_min, dte_max=dte_max,
                    target_delta=settings.DIRECTIONAL_DELTA,
                    max_loss="defined",
                    profit_target_pct=0.75,
                    direction="bullish",
                    rationale=f"Low IV + moderate bull signal: bull call spread reduces cost vs outright call.",
                )

        if inp.direction == "bearish":
            if inp.total_score < 35:
                return TradeStructure(
                    strategy="long_put",
                    short_strike="N/A",
                    long_strike=f"0.40–0.45 delta ATM put",
                    dte_min=dte_min, dte_max=dte_max,
                    target_delta=-settings.DIRECTIONAL_DELTA,
                    max_loss="defined",
                    profit_target_pct=1.0,
                    direction="bearish",
                    rationale=f"Low IV + strong bear signal: buy ATM put, cheap premium.",
                )
            else:
                return TradeStructure(
                    strategy="bear_put_spread",
                    short_strike=f"0.25 delta OTM put",
                    long_strike=f"0.40–0.45 delta ATM put",
                    dte_min=dte_min, dte_max=dte_max,
                    target_delta=-settings.DIRECTIONAL_DELTA,
                    max_loss="defined",
                    profit_target_pct=0.75,
                    direction="bearish",
                    rationale=f"Low IV + moderate bear signal: bear put spread.",
                )

    # ================================================================
    # MODERATE IV (40–60th percentile) → Debit spreads
    # ================================================================
    else:
        if inp.direction == "bullish":
            return TradeStructure(
                strategy="bull_call_spread",
                short_strike=f"0.25 delta OTM call",
                long_strike=f"0.40–0.45 delta call near ATM",
                dte_min=dte_min, dte_max=dte_max,
                target_delta=settings.DIRECTIONAL_DELTA,
                max_loss="defined",
                profit_target_pct=0.75,
                direction="bullish",
                rationale=f"Moderate IV ({inp.iv_percentile:.0f}th pct) + bullish: bull call spread balances cost vs upside.",
            )

        if inp.direction == "bearish":
            return TradeStructure(
                strategy="bear_put_spread",
                short_strike=f"0.25 delta OTM put",
                long_strike=f"0.40–0.45 delta put near ATM",
                dte_min=dte_min, dte_max=dte_max,
                target_delta=-settings.DIRECTIONAL_DELTA,
                max_loss="defined",
                profit_target_pct=0.75,
                direction="bearish",
                rationale=f"Moderate IV + bearish: bear put spread.",
            )

        # Neutral in moderate IV — small iron condor or calendar
        return TradeStructure(
            strategy="calendar_spread",
            short_strike="ATM short near-term",
            long_strike="ATM long 30-45 DTE",
            dte_min=14, dte_max=45,
            target_delta=0.0,
            max_loss="defined",
            profit_target_pct=0.50,
            direction="neutral",
            rationale=f"Moderate IV + neutral: calendar spread profits from theta differential with limited directional risk.",
        )

    # Fallback
    return TradeStructure(
        strategy="bull_call_spread",
        short_strike="0.25 delta OTM call",
        long_strike="0.40 delta call",
        dte_min=21, dte_max=45,
        target_delta=0.40,
        max_loss="defined",
        profit_target_pct=0.75,
        direction=inp.direction,
        rationale="Default structure — review IV and direction manually.",
    )
