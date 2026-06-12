"""Category 1: Market & Macro (8%)"""

import pandas as pd
from loguru import logger
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    try:
        from data.macro import get_fred
        fred = get_fred()
        macro = await fred.get_macro_snapshot()
    except Exception as e:
        logger.debug(f"Macro data unavailable: {e}")
        macro = {}

    vix = macro.get("vix")
    yield_spread = macro.get("t10y2y")

    if vix is not None:
        signals.append({"name": "vix", "value": round(vix, 1)})
        if vix < 15:
            score += 1.5
            direction = "bullish"
            signals.append({"name": "low_vix", "direction": "bullish", "note": "Low fear = favorable"})
        elif vix > 25:
            score -= 1
            direction = "bearish"
            signals.append({"name": "elevated_vix", "direction": "bearish", "note": "Elevated fear = caution"})
        elif vix > 35:
            score -= 2
            signals.append({"name": "high_vix", "direction": "bearish", "note": "High fear = hedge required"})

    if yield_spread is not None:
        signals.append({"name": "yield_spread_10y2y", "value": round(yield_spread, 3)})
        if yield_spread < 0:
            score -= 1
            signals.append({"name": "inverted_yield_curve", "direction": "bearish", "note": "Recession signal"})
        elif yield_spread > 0.5:
            score += 0.5
            signals.append({"name": "normal_yield_curve", "direction": "bullish"})

    # SPY/QQQ trend as market regime proxy
    if not df.empty and len(df) >= 50:
        import pandas_ta as ta
        close = df["close"]
        ema50 = ta.ema(close, length=50)
        if ema50 is not None:
            last = float(close.iloc[-1])
            e50 = float(ema50.iloc[-1])
            if last > e50 * 1.02:
                score += 0.5
                signals.append({"name": "above_50ema", "direction": "bullish"})
            elif last < e50 * 0.98:
                score -= 0.5
                signals.append({"name": "below_50ema", "direction": "bearish"})

    score = max(0.0, min(10.0, score))
    weight = 8.0
    return CategoryScore("macro", weight, score, weight * score / 10, direction, signals,
                        f"VIX={vix}, Yield spread={yield_spread}")
