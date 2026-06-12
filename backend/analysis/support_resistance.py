"""Category 5: Support & Resistance (8%)"""

import pandas as pd
import pandas_ta as ta
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if df.empty or len(df) < 20:
        return CategoryScore("support_resistance", 8.0, 5.0, 4.0, "neutral", [], "Insufficient data")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    last = float(close.iloc[-1])

    # VWAP (proxy: EMA of typical price weighted by volume)
    typical = (high + low + close) / 3
    if "volume" in df.columns and df["volume"].sum() > 0:
        vwap = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
        vwap_val = float(vwap.iloc[-1])
        signals.append({"name": "vwap", "value": round(vwap_val, 2)})
        if last > vwap_val * 1.01:
            score += 1
            direction = "bullish"
            signals.append({"name": "above_vwap", "direction": "bullish"})
        elif last < vwap_val * 0.99:
            score -= 1
            direction = "bearish"
            signals.append({"name": "below_vwap", "direction": "bearish"})

    # Pivot levels (Standard: P, R1, R2, S1, S2)
    prev_high = float(high.iloc[-2]) if len(high) > 1 else float(high.iloc[-1])
    prev_low  = float(low.iloc[-2]) if len(low) > 1 else float(low.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else float(close.iloc[-1])
    pivot = (prev_high + prev_low + prev_close) / 3
    r1 = 2 * pivot - prev_low
    s1 = 2 * pivot - prev_high
    r2 = pivot + (prev_high - prev_low)
    s2 = pivot - (prev_high - prev_low)

    signals.append({"name": "pivot", "value": round(pivot, 2)})
    signals.append({"name": "r1", "value": round(r1, 2)})
    signals.append({"name": "s1", "value": round(s1, 2)})

    # Is price at key support/resistance?
    pct_from_pivot = (last - pivot) / pivot
    pct_from_s1 = (last - s1) / s1 if s1 != 0 else 0
    pct_from_r1 = (last - r1) / r1 if r1 != 0 else 0

    if abs(pct_from_s1) < 0.015:
        score += 1.5
        signals.append({"name": "at_s1_support", "direction": "bullish", "note": "Bounce opportunity"})
    if abs(pct_from_r1) < 0.015:
        score -= 1
        signals.append({"name": "at_r1_resistance", "direction": "bearish", "note": "Resistance ahead"})

    # 52-week high/low proximity
    high_52 = float(high.tail(252).max()) if len(high) >= 252 else float(high.max())
    low_52  = float(low.tail(252).min()) if len(low) >= 252 else float(low.min())

    pct_from_52h = (high_52 - last) / high_52
    pct_from_52l = (last - low_52) / low_52 if low_52 > 0 else 0

    if pct_from_52h < 0.03:
        score += 1.5
        signals.append({"name": "near_52wk_high", "value": round(high_52, 2), "direction": "bullish"})
    if pct_from_52l < 0.05:
        score += 0.5
        signals.append({"name": "near_52wk_low", "value": round(low_52, 2), "direction": "potential_reversal"})

    # Fibonacci retracement (last significant swing)
    swing_high = float(high.tail(60).max())
    swing_low  = float(low.tail(60).min())
    fib_618 = swing_high - 0.618 * (swing_high - swing_low)
    fib_382 = swing_high - 0.382 * (swing_high - swing_low)

    if abs(last - fib_618) / last < 0.02:
        score += 1
        signals.append({"name": "fib_618_level", "value": round(fib_618, 2), "direction": "support"})
    elif abs(last - fib_382) / last < 0.02:
        score += 0.5
        signals.append({"name": "fib_382_level", "value": round(fib_382, 2), "direction": "support"})

    score = max(0.0, min(10.0, score))

    bull_sigs = sum(1 for s in signals if s.get("direction") in ("bullish", "support"))
    bear_sigs = sum(1 for s in signals if s.get("direction") in ("bearish", "resistance"))
    if bull_sigs > bear_sigs:
        direction = "bullish"
    elif bear_sigs > bull_sigs:
        direction = "bearish"

    weight = 8.0
    return CategoryScore(
        name="support_resistance", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=f"Pivot P={round(pivot,2)}, S1={round(s1,2)}, R1={round(r1,2)}; price {round(pct_from_pivot*100,1)}% from pivot",
    )
