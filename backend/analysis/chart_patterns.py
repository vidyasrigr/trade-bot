"""Category 7: Chart Patterns (7%) — rule-based detection: flags, wedges, H&S, cup & handle."""

import numpy as np
import pandas as pd
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if df.empty or len(df) < 30:
        return CategoryScore("chart_patterns", 7.0, 5.0, 3.5, "neutral", [], "Insufficient data")

    close = df["close"].values
    high  = df["high"].values
    low   = df["low"].values
    volume = df["volume"].values if "volume" in df.columns else None

    # Bull flag: strong up move (>8% in 5 days) followed by tight consolidation (<3%)
    if len(close) >= 25:
        pole_return = (close[-15] - close[-20]) / close[-20] if close[-20] > 0 else 0
        consol_range = (max(close[-15:]) - min(close[-15:])) / close[-15] if close[-15] > 0 else 1
        if pole_return > 0.08 and consol_range < 0.05:
            score += 2.0
            direction = "bullish"
            signals.append({
                "name": "bull_flag",
                "pole_return_pct": round(pole_return * 100, 1),
                "consolidation_range_pct": round(consol_range * 100, 1),
                "direction": "bullish",
            })

    # Bear flag: strong down move (>8% in 5 days) followed by tight bounce
    if len(close) >= 25:
        pole_return = (close[-15] - close[-20]) / close[-20] if close[-20] > 0 else 0
        consol_range = (max(close[-15:]) - min(close[-15:])) / close[-15] if close[-15] > 0 else 1
        if pole_return < -0.08 and consol_range < 0.05:
            score -= 2.0
            direction = "bearish"
            signals.append({
                "name": "bear_flag",
                "pole_return_pct": round(pole_return * 100, 1),
                "direction": "bearish",
            })

    # Cup & Handle: U-shaped 20-60 day base + tight handle
    if len(close) >= 60:
        cup = close[-60:]
        cup_low_idx = np.argmin(cup)
        cup_left  = cup[0]
        cup_right = cup[-20]
        cup_low   = cup[cup_low_idx]
        if cup_low_idx > 5 and cup_low_idx < 55:  # low in middle
            depth = (cup_left - cup_low) / cup_left if cup_left > 0 else 0
            symmetry = abs(cup_left - cup_right) / cup_left if cup_left > 0 else 1
            if 0.10 < depth < 0.35 and symmetry < 0.08:
                handle = close[-15:]
                handle_range = (max(handle) - min(handle)) / close[-15] if close[-15] > 0 else 1
                if handle_range < 0.04:
                    score += 2.5
                    direction = "bullish"
                    signals.append({
                        "name": "cup_and_handle",
                        "depth_pct": round(depth * 100, 1),
                        "direction": "bullish",
                    })

    # Ascending triangle: flat resistance + higher lows
    if len(high) >= 20:
        resistance = np.percentile(high[-20:], 95)
        lows_slope = np.polyfit(range(10), low[-10:], 1)[0]
        closes_near_resistance = sum(1 for h in high[-5:] if abs(h - resistance) / resistance < 0.02)
        if lows_slope > 0 and closes_near_resistance >= 3:
            score += 1.5
            direction = "bullish"
            signals.append({
                "name": "ascending_triangle",
                "resistance": round(resistance, 2),
                "direction": "bullish",
            })

    # Descending triangle: flat support + lower highs
    if len(low) >= 20:
        support = np.percentile(low[-20:], 5)
        highs_slope = np.polyfit(range(10), high[-10:], 1)[0]
        closes_near_support = sum(1 for l in low[-5:] if abs(l - support) / support < 0.02)
        if highs_slope < 0 and closes_near_support >= 3:
            score -= 1.5
            direction = "bearish"
            signals.append({
                "name": "descending_triangle",
                "support": round(support, 2),
                "direction": "bearish",
            })

    # False breakout filter: breakout only valid if 2+ consecutive closes above resistance
    # (if we detected ascending triangle + close is above resistance, verify)
    if any(s["name"] == "ascending_triangle" for s in signals):
        resistance = [s["resistance"] for s in signals if s.get("name") == "ascending_triangle"][0]
        consecutive_above = sum(1 for c in close[-3:] if c > resistance)
        if volume is not None:
            avg_vol = np.mean(volume[-20:])
            breakout_vol = volume[-1] > avg_vol * 1.5
        else:
            breakout_vol = True
        if consecutive_above >= 2 and breakout_vol:
            score += 1.0
            signals.append({"name": "breakout_confirmed", "direction": "bullish"})
        elif consecutive_above < 2:
            score -= 0.5
            signals.append({"name": "unconfirmed_breakout", "note": "false_breakout_risk"})

    score = max(0.0, min(10.0, score))

    weight = 7.0
    return CategoryScore(
        name="chart_patterns", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=f"{len(signals)} pattern(s) detected: {', '.join(s['name'] for s in signals[:3])}",
    )
