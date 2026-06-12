"""Category 4: Trend & Market Structure (10%)"""

import pandas as pd
import pandas_ta as ta
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if df.empty or len(df) < 50:
        return CategoryScore("trend", 10.0, 5.0, 5.0, "neutral", [], "Insufficient data")

    close = df["close"]

    # EMAs
    ema8   = ta.ema(close, length=8).iloc[-1]
    ema21  = ta.ema(close, length=21).iloc[-1]
    ema50  = ta.ema(close, length=50).iloc[-1]
    ema200 = ta.ema(close, length=200).iloc[-1] if len(df) >= 200 else None
    last   = float(close.iloc[-1])

    bullish_count = 0
    bearish_count = 0

    # EMA stack alignment
    if ema8 > ema21 > ema50:
        bullish_count += 2
        signals.append({"name": "ema_stack", "value": "bullish_8>21>50", "direction": "bullish"})
    elif ema8 < ema21 < ema50:
        bearish_count += 2
        signals.append({"name": "ema_stack", "value": "bearish_8<21<50", "direction": "bearish"})

    if ema200:
        if last > ema200:
            bullish_count += 1
            signals.append({"name": "above_200ema", "value": round(last - ema200, 2), "direction": "bullish"})
        else:
            bearish_count += 1
            signals.append({"name": "below_200ema", "value": round(ema200 - last, 2), "direction": "bearish"})

    # Higher highs / higher lows detection (last 20 bars)
    recent = df.tail(20)
    highs = recent["high"].values
    lows  = recent["low"].values
    hh = highs[-1] > highs[-5] > highs[-10]
    hl = lows[-1] > lows[-5] > lows[-10]
    ll = lows[-1] < lows[-5] < lows[-10]
    lh = highs[-1] < highs[-5] < highs[-10]

    if hh and hl:
        bullish_count += 2
        signals.append({"name": "hh_hl_structure", "value": "bullish_trend", "direction": "bullish"})
    elif ll and lh:
        bearish_count += 2
        signals.append({"name": "ll_lh_structure", "value": "bearish_trend", "direction": "bearish"})

    # ADX (trend strength)
    adx_df = ta.adx(df["high"], df["low"], close, length=14)
    if adx_df is not None and not adx_df.empty:
        adx = float(adx_df.iloc[-1, 0])
        if adx > 25:
            score += 1
            signals.append({"name": "adx", "value": round(adx, 1), "direction": "strong_trend"})
        elif adx < 15:
            score -= 0.5
            signals.append({"name": "adx", "value": round(adx, 1), "direction": "weak_trend"})

    # Final score
    net = bullish_count - bearish_count
    if net >= 3:
        score = 8.5
        direction = "bullish"
    elif net >= 1:
        score = 7.0
        direction = "bullish"
    elif net <= -3:
        score = 1.5
        direction = "bearish"
    elif net <= -1:
        score = 3.0
        direction = "bearish"
    else:
        score = 5.0
        direction = "neutral"

    weight = 10.0
    return CategoryScore(
        name="trend", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=f"EMA stack {'aligned' if net != 0 else 'mixed'}, ADX trend strength {'strong' if any(s.get('name')=='adx' and s.get('value',0)>25 for s in signals) else 'moderate'}",
    )
