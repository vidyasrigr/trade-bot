"""
Volatility Regime Classifier — bull_trend/bear_trend/chop/high_vol.

Uses VIX thresholds (research-backed: <15 calm, 15-20 normal, 20-30 elevated, >30 crisis)
combined with SPY trend analysis. Individual stock RV used as secondary confirmation only.
"""

import math
import numpy as np
import pandas as pd
import pandas_ta as ta
from analysis.engine import CategoryScore


# Research-backed VIX regime thresholds (sourced from SpotGamma, Tastytrade, CBOE analysis)
VIX_CALM = 15.0        # < 15: thin premiums, directional plays preferred
VIX_NORMAL_HIGH = 20.0 # 15-20: standard iron condor environment
VIX_ELEVATED = 30.0    # 20-30: rich premiums, credit spreads ideal
                       # > 30: crisis — hedges, VIX products, reduce directional


async def analyze(symbol: str, df: pd.DataFrame, vix_current: float | None = None) -> CategoryScore:
    signals = []
    score = 5.0

    if df.empty or len(df) < 50:
        return CategoryScore("volatility_regime", 0.0, 5.0, 0.0, "neutral",
                           [{"regime": "unknown"}], "Insufficient data")

    close = df["close"]
    log_returns = np.log(close.values[1:] / close.values[:-1])

    # Realized vol (20-day, 60-day) — secondary confirmation
    rv20 = np.std(log_returns[-20:]) * math.sqrt(252)
    rv60 = np.std(log_returns[-60:]) * math.sqrt(252) if len(log_returns) >= 60 else rv20

    # SPY trend proxy: use 50-day SMA slope on the symbol (for sector direction)
    sma50 = ta.sma(close, length=50)
    sma200 = ta.sma(close, length=200) if len(df) >= 200 else None

    if sma50 is not None and len(sma50) >= 5:
        sma50_slope = (float(sma50.iloc[-1]) - float(sma50.iloc[-5])) / float(sma50.iloc[-5])
    else:
        sma50_slope = 0.0

    last_close = float(close.iloc[-1])
    sma50_val = float(sma50.iloc[-1]) if sma50 is not None else last_close
    sma200_val = float(sma200.iloc[-1]) if sma200 is not None and not sma200.isna().iloc[-1] else None

    # ── Primary regime classification via VIX ──────────────────────────────────
    trend_threshold = 0.015  # 5-day SMA slope > 1.5% = meaningful trend

    if vix_current is not None:
        signals.append({"name": "vix_current", "value": round(vix_current, 2)})

        if vix_current > VIX_ELEVATED:
            # Crisis regime: override everything, favor hedges
            regime = "high_vol"
            score = 3.0  # low score = dangerous for directional plays
            signals.append({"name": "vix_crisis", "direction": "danger",
                           "note": f"VIX {vix_current:.1f} > {VIX_ELEVATED} — crisis regime, favor UVXY calls or cash"})
        elif vix_current > VIX_NORMAL_HIGH:
            # Elevated regime: premium selling is richly rewarded
            regime = "high_vol"
            score = 7.5  # high score for premium sellers
            signals.append({"name": "vix_elevated", "direction": "sell_premium",
                           "note": f"VIX {vix_current:.1f} in 20-30 zone — credit spreads ideal, rich premiums"})
        elif vix_current > VIX_CALM:
            # Normal: standard iron condor / spread environment
            # Determine trend from price action
            if sma50_slope > trend_threshold and last_close > sma50_val:
                regime = "bull_trend"
                score = 8.0
            elif sma50_slope < -trend_threshold and last_close < sma50_val:
                regime = "bear_trend"
                score = 3.5
            else:
                regime = "chop"
                score = 5.0
        else:
            # Calm VIX < 15: directional plays preferred (cheap options)
            if sma50_slope > trend_threshold and last_close > sma50_val:
                regime = "bull_trend"
                score = 9.0  # strong bull trend in calm vol = ideal directional buy
            elif sma50_slope < -trend_threshold and last_close < sma50_val:
                regime = "bear_trend"
                score = 3.0
            else:
                regime = "chop"
                score = 4.5  # chop in low vol = calendar spreads

    else:
        # Fallback: use RV-based classification when VIX unavailable
        high_vol_rv = 0.35  # annualized RV > 35% ≈ VIX > 30 proxy
        if rv20 > high_vol_rv:
            regime = "high_vol"
            score = 6.0
        elif sma50_slope > trend_threshold and last_close > sma50_val:
            regime = "bull_trend"
            score = 8.0
        elif sma50_slope < -trend_threshold and last_close < sma50_val:
            regime = "bear_trend"
            score = 3.0
        else:
            regime = "chop"
            score = 4.5

    # ── Additional regime quality signals ──────────────────────────────────────

    # Golden/death cross (200 SMA) — strongest long-term regime indicator
    if sma200_val is not None:
        if last_close > sma200_val and regime == "bull_trend":
            signals.append({"name": "above_sma200", "direction": "bullish",
                           "note": f"Price {round(last_close, 2)} above SMA200 {round(sma200_val, 2)} — macro bull confirmed"})
            score = min(10.0, score + 0.5)
        elif last_close < sma200_val and regime == "bear_trend":
            signals.append({"name": "below_sma200", "direction": "bearish",
                           "note": f"Price below SMA200 — macro bear confirmed"})

    # RV vs historical norm — is vol expanding or contracting?
    if rv20 > rv60 * 1.3:
        signals.append({"name": "rv_expanding", "note": "RV expanding vs 60-day — volatility breakout or stress event"})
    elif rv20 < rv60 * 0.7:
        signals.append({"name": "rv_contracting", "note": "RV compressing — typical before next volatility event"})

    signals.append({
        "regime": regime,
        "rv20_pct": round(rv20 * 100, 1),
        "rv60_pct": round(rv60 * 100, 1),
        "sma50_slope_pct": round(sma50_slope * 100, 2),
        "price_vs_sma50": round((last_close - sma50_val) / sma50_val * 100, 1) if sma50_val else 0,
        "vix": round(vix_current, 2) if vix_current else None,
    })

    score = max(0.0, min(10.0, score))

    direction = "bullish" if regime == "bull_trend" else ("bearish" if regime == "bear_trend" else "neutral")

    vix_str = f"VIX={round(vix_current,1)}" if vix_current else f"RV20={round(rv20*100,1)}%"
    weight = 0.0  # Contributes to regime detection but weight embedded in other categories
    return CategoryScore(
        name="volatility_regime", weight=weight,
        raw_score=score, weighted_score=0.0,
        direction=direction, signals=signals,
        summary=f"Regime: {regime} | {vix_str} | SMA50 slope={round(sma50_slope*100,2)}%",
    )
