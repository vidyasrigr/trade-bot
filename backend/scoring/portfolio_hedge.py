"""Portfolio-level hedge recommendations — deterministic rule engine."""

from core.config import settings


async def get_hedge_recommendation(portfolio_heat: float, vol_regime: str, net_delta: float) -> dict:
    """
    Returns hedge recommendation based on current portfolio state.
    Completely deterministic — no LLM.
    """
    recommendations = []

    # High heat + directional bias → hedge
    if portfolio_heat > settings.MAX_PORTFOLIO_HEAT * 0.8 and abs(net_delta) > 0.4:
        direction = "long" if net_delta > 0 else "short"
        hedge_instrument = "UVXY calls" if vol_regime == "high_vol" else "SPY puts" if direction == "long" else "SPY calls"
        recommendations.append({
            "type": "portfolio_hedge",
            "instrument": hedge_instrument,
            "rationale": f"Portfolio {round(portfolio_heat*100,1)}% deployed with {direction} bias {round(net_delta,2)}Δ — hedge recommended",
            "size": "5-10% of total portfolio value",
        })

    # Vol regime = high_vol → VIX hedge
    if vol_regime == "high_vol" and portfolio_heat > 0.15:
        recommendations.append({
            "type": "vol_hedge",
            "instrument": "UVXY 15-delta calls, 30 DTE",
            "rationale": "High-vol regime with deployed capital — VIX call hedge for tail risk",
            "size": "2-3% of portfolio value",
        })

    return {
        "recommendations": recommendations,
        "portfolio_heat": round(portfolio_heat, 3),
        "vol_regime": vol_regime,
        "net_delta": round(net_delta, 3),
    }
