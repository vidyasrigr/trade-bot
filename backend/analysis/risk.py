"""Category 16: Risk Management (5%) — position sizing, R/R, portfolio heat."""

import pandas as pd
from analysis.engine import CategoryScore
from core.config import settings


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 6.0
    direction = "neutral"

    if df.empty:
        return CategoryScore("risk", 5.0, 5.0, 2.5, "neutral", [], "No data")

    close = df["close"]
    last = float(close.iloc[-1])

    # ATR-based stop level
    import pandas_ta as ta
    atr = ta.atr(df["high"], df["low"], close, length=14)
    if atr is not None and not atr.empty:
        atr_val = float(atr.iloc[-1])
        stop_level = last - 2 * atr_val  # 2-ATR stop
        risk_pct = (last - stop_level) / last
        signals.append({"name": "atr_14", "value": round(atr_val, 2)})
        signals.append({"name": "suggested_stop", "value": round(stop_level, 2)})
        signals.append({"name": "risk_pct_to_stop", "value": round(risk_pct * 100, 1)})

        if risk_pct < 0.05:
            score += 1
            signals.append({"name": "tight_stop_available", "direction": "favorable"})
        elif risk_pct > 0.12:
            score -= 1
            signals.append({"name": "wide_stop_required", "note": "Reduce size"})

    # Portfolio heat check
    try:
        from scoring.portfolio_risk import get_current_heat
        heat = await get_current_heat()
        signals.append({"name": "portfolio_heat_pct", "value": round(heat * 100, 1)})
        if heat > settings.MAX_PORTFOLIO_HEAT:
            score -= 2
            signals.append({"name": "portfolio_at_max_heat", "note": f"Cannot add new position: {round(heat*100,1)}% deployed"})
        elif heat > settings.MAX_PORTFOLIO_HEAT * 0.8:
            score -= 0.5
            signals.append({"name": "portfolio_heat_elevated", "note": "Reduce size on new positions"})
    except Exception:
        signals.append({"name": "portfolio_heat", "note": "Cannot fetch — proceed with caution"})

    score = max(0.0, min(10.0, score))
    weight = 5.0
    return CategoryScore("risk", weight, score, weight * score / 10, direction, signals,
                        f"ATR-based stop at {round(stop_level,2) if atr is not None and not atr.empty else 'N/A'}")
