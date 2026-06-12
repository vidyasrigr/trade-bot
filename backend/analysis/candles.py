"""Category 6: Candlestick Patterns (7%) — with volume confirmation gate."""

import numpy as np
import pandas as pd
import pandas_ta as ta
from analysis.engine import CategoryScore


BULLISH_PATTERNS = [
    "CDL_HAMMER", "CDL_ENGULFING", "CDL_MORNINGSTAR", "CDL_DOJI_10_0.1",
    "CDL_DRAGONFLYDOJI", "CDL_INVERTEDHAMMER", "CDL_PIERCING",
    "CDL_3WHITESOLDIERS", "CDL_MORNINGDOJISTAR",
]
BEARISH_PATTERNS = [
    "CDL_SHOOTINGSTAR", "CDL_HANGINGMAN", "CDL_EVENINGSTAR",
    "CDL_3BLACKCROWS", "CDL_DARKCLOUDCOVER", "CDL_EVENINGDOJISTAR",
]

# Volume confirmation multipliers
VOL_STRONG     = 2.0   # ≥2× avg → pattern is high-confidence, score bonus
VOL_MODERATE   = 1.5   # ≥1.5× avg → normal weight
VOL_THIN       = 0.75  # <0.75× avg → thin volume, downgrade pattern weight


def _vol_confirmation(df: pd.DataFrame, bar_idx: int = -1) -> tuple[float, str]:
    """
    Returns (vol_ratio, label) for the given bar index.
    vol_ratio = current_volume / 20-day avg volume.
    """
    if "volume" not in df.columns or len(df) < 5:
        return 1.0, "unknown"
    avg_vol = float(df["volume"].tail(20).mean())
    if avg_vol <= 0:
        return 1.0, "unknown"
    cur_vol = float(df["volume"].iloc[bar_idx])
    ratio = cur_vol / avg_vol
    if ratio >= VOL_STRONG:
        label = "strong"
    elif ratio >= VOL_MODERATE:
        label = "moderate"
    elif ratio < VOL_THIN:
        label = "thin"
    else:
        label = "normal"
    return round(ratio, 2), label


def _pattern_score_delta(vol_label: str, base_delta: float) -> float:
    """Scale the score contribution based on volume confirmation strength."""
    if vol_label == "strong":
        return base_delta * 1.5     # high-volume pattern: 50% bonus
    elif vol_label == "thin":
        return base_delta * 0.4     # thin-volume pattern: 60% penalty
    return base_delta               # moderate/normal/unknown: unchanged


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if df.empty or len(df) < 10:
        return CategoryScore("candles", 7.0, 5.0, 3.5, "neutral", [], "Insufficient data")

    try:
        candles = ta.cdl_pattern(df["open"], df["high"], df["low"], df["close"])
    except Exception:
        return CategoryScore("candles", 7.0, 5.0, 3.5, "neutral", [], "Pattern detection unavailable")

    if candles is None or candles.empty:
        return CategoryScore("candles", 7.0, 5.0, 3.5, "neutral", [], "No patterns detected")

    # Volume confirmation for the current bar
    vol_ratio, vol_label = _vol_confirmation(df, bar_idx=-1)

    bull_weight = 0.0
    bear_weight = 0.0

    for col in candles.columns:
        last_val = candles[col].iloc[-1]
        if last_val == 0:
            continue

        is_bullish = any(p in col.upper() for p in [pat.replace("CDL_", "") for pat in BULLISH_PATTERNS])
        is_bearish = any(p in col.upper() for p in [pat.replace("CDL_", "") for pat in BEARISH_PATTERNS])

        if is_bullish:
            delta = _pattern_score_delta(vol_label, 1.0)
            bull_weight += delta
            signals.append({
                "name": col,
                "value": int(last_val),
                "direction": "bullish",
                "vol_ratio": vol_ratio,
                "vol_confirmation": vol_label,
            })
        elif is_bearish:
            delta = _pattern_score_delta(vol_label, 1.0)
            bear_weight += delta
            signals.append({
                "name": col,
                "value": int(last_val),
                "direction": "bearish",
                "vol_ratio": vol_ratio,
                "vol_confirmation": vol_label,
            })

    # Check last 3 bars for recency (use vol_ratio for that specific bar)
    for col in candles.columns:
        recent = candles[col].tail(3)
        if (recent != 0).any() and col not in [s["name"] for s in signals]:
            # Find which of the last 3 bars had the pattern
            recent_nonzero = recent[recent != 0]
            if recent_nonzero.empty:
                continue
            bar_pos = -(len(candles) - recent_nonzero.index[-1])  # relative index
            r_vol_ratio, r_vol_label = _vol_confirmation(df, bar_idx=bar_pos)
            val = int(recent_nonzero.iloc[-1])
            if val > 0:
                delta = _pattern_score_delta(r_vol_label, 0.5)
                bull_weight += delta
                signals.append({
                    "name": col, "value": val, "direction": "bullish",
                    "recency": "recent_3bar",
                    "vol_ratio": r_vol_ratio, "vol_confirmation": r_vol_label,
                })
            elif val < 0:
                delta = _pattern_score_delta(r_vol_label, 0.5)
                bear_weight += delta
                signals.append({
                    "name": col, "value": val, "direction": "bearish",
                    "recency": "recent_3bar",
                    "vol_ratio": r_vol_ratio, "vol_confirmation": r_vol_label,
                })

    if bull_weight > bear_weight:
        net = bull_weight - bear_weight
        score = min(5 + net * 1.2, 9.0)
        direction = "bullish"
    elif bear_weight > bull_weight:
        net = bear_weight - bull_weight
        score = max(5 - net * 1.2, 1.0)
        direction = "bearish"

    # Summarize volume confirmation quality
    strong_count = sum(1 for s in signals if s.get("vol_confirmation") == "strong")
    thin_count   = sum(1 for s in signals if s.get("vol_confirmation") == "thin")
    vol_note = ""
    if strong_count > 0:
        vol_note = f" | {strong_count} volume-confirmed"
    elif thin_count > 0:
        vol_note = f" | {thin_count} thin-volume (downgraded)"

    weight = 7.0
    return CategoryScore(
        name="candles", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals[:8],
        summary=f"{bull_weight:.1f} bullish / {bear_weight:.1f} bearish (vol-adjusted){vol_note}",
    )
