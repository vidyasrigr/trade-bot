"""Category 8: Volume & Momentum (7%) — with Daniel-Moskowitz crash filter."""

import math
import asyncio
import numpy as np
import pandas as pd
import pandas_ta as ta
from analysis.engine import CategoryScore


# Daniel & Moskowitz (2016) — momentum crashes coincide with high realized vol
# regimes. Gate any bullish momentum vote when SPX 6-month RV breaches the 80th
# percentile of its trailing 5-year history. Cached for the duration of one scan.
_CRASH_REGIME_CACHE: dict[str, bool] = {}


async def _spx_crash_regime() -> bool:
    if "value" in _CRASH_REGIME_CACHE:
        return _CRASH_REGIME_CACHE["value"]
    try:
        from data.market import get_ohlcv_yfinance
        spx = await asyncio.get_event_loop().run_in_executor(
            None, lambda: get_ohlcv_yfinance("SPY", period="5y"),
        )
        if spx is None or spx.empty or len(spx) < 252 * 5:
            _CRASH_REGIME_CACHE["value"] = False
            return False
        rets = np.log(spx["close"].values[1:] / spx["close"].values[:-1])
        rolling = pd.Series(rets).rolling(126).std() * math.sqrt(252)
        rolling = rolling.dropna()
        if len(rolling) < 252:
            _CRASH_REGIME_CACHE["value"] = False
            return False
        threshold = float(np.percentile(rolling.iloc[:-1], 80))
        current = float(rolling.iloc[-1])
        _CRASH_REGIME_CACHE["value"] = current > threshold
        return _CRASH_REGIME_CACHE["value"]
    except Exception:
        _CRASH_REGIME_CACHE["value"] = False
        return False


async def analyze(symbol: str, df: pd.DataFrame) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"
    momentum_events: list[dict] = []  # crossover events for watchlist alerts

    if df.empty or len(df) < 20:
        return CategoryScore("momentum", 7.0, 5.0, 3.5, "neutral", [], "Insufficient data")

    crash_regime = await _spx_crash_regime()
    if crash_regime:
        signals.append({
            "name": "momentum_crash_filter",
            "direction": "neutral",
            "note": "SPX 126d RV in top quintile — momentum crash risk (Daniel-Moskowitz 2016)",
        })

    close = df["close"]
    volume = df["volume"]

    # RSI
    rsi_s = ta.rsi(close, length=14)
    if rsi_s is not None and not rsi_s.empty and len(rsi_s) >= 2:
        rsi = float(rsi_s.iloc[-1])
        rsi_prev = float(rsi_s.iloc[-2])
        signals.append({"name": "rsi", "value": round(rsi, 1)})

        if rsi > 70:
            signals.append({"name": "rsi_overbought", "direction": "bearish"})
            score -= 1
        elif rsi < 30:
            signals.append({"name": "rsi_oversold", "direction": "bullish"})
            score += 1.5
            if rsi > rsi_prev:
                momentum_events.append({
                    "event": "rsi_oversold_bounce",
                    "label": "RSI bouncing from oversold (<30)",
                    "value": round(rsi, 1),
                    "direction": "bullish",
                    "strength": "strong",
                })
        elif 50 < rsi < 70 and rsi > rsi_prev:
            score += 1
            direction = "bullish"

        # RSI crossing 50 from below (bullish momentum flip)
        if rsi_prev < 50 <= rsi:
            score += 1.5
            momentum_events.append({
                "event": "rsi_cross_50_bullish",
                "label": "RSI crossed above 50 (momentum flip bullish)",
                "value": round(rsi, 1),
                "direction": "bullish",
                "strength": "strong",
            })
            signals.append({"name": "rsi_crossed_50_bullish", "direction": "bullish"})

        # RSI crossing 50 from above (bearish momentum flip)
        elif rsi_prev > 50 >= rsi:
            score -= 1.5
            momentum_events.append({
                "event": "rsi_cross_50_bearish",
                "label": "RSI crossed below 50 (momentum flip bearish)",
                "value": round(rsi, 1),
                "direction": "bearish",
                "strength": "strong",
            })
            signals.append({"name": "rsi_crossed_50_bearish", "direction": "bearish"})

    # MACD (treat as ONE momentum vote with RSI — factor orthogonality)
    macd_df = ta.macd(close)
    if macd_df is not None and not macd_df.empty and len(macd_df) >= 2:
        macd_line = float(macd_df.iloc[-1, 0])
        macd_signal_line = float(macd_df.iloc[-1, 1])
        hist = float(macd_df.iloc[-1, 2])
        hist_prev = float(macd_df.iloc[-2, 2])
        macd_line_prev = float(macd_df.iloc[-2, 0])
        macd_signal_prev = float(macd_df.iloc[-2, 1])

        signals.append({"name": "macd_hist", "value": round(hist, 4)})

        # MACD bullish crossover (line crosses signal from below)
        if macd_line_prev <= macd_signal_prev and macd_line > macd_signal_line:
            score += 1.5
            momentum_events.append({
                "event": "macd_bull_crossover",
                "label": "MACD bullish crossover (line crossed above signal)",
                "value": round(macd_line, 4),
                "direction": "bullish",
                "strength": "strong" if macd_line > 0 else "moderate",
            })
            signals.append({"name": "macd_bull_crossover", "direction": "bullish"})

        # MACD bearish crossover
        elif macd_line_prev >= macd_signal_prev and macd_line < macd_signal_line:
            score -= 1.0
            momentum_events.append({
                "event": "macd_bear_crossover",
                "label": "MACD bearish crossover (line crossed below signal)",
                "value": round(macd_line, 4),
                "direction": "bearish",
                "strength": "strong" if macd_line < 0 else "moderate",
            })
            signals.append({"name": "macd_bear_crossover", "direction": "bearish"})

        elif macd_line > macd_signal_line and hist > 0 and hist > hist_prev:
            score += 0.5  # already bullish and strengthening
            signals.append({"name": "macd_bull_expanding", "direction": "bullish"})

    # EMA21 price crossover
    ema21 = ta.ema(close, length=21)
    if ema21 is not None and not ema21.empty and len(ema21) >= 2:
        ema21_val = float(ema21.iloc[-1])
        ema21_prev = float(ema21.iloc[-2])
        price_now = float(close.iloc[-1])
        price_prev = float(close.iloc[-2])
        signals.append({"name": "ema21", "value": round(ema21_val, 2)})

        # Price crossed above EMA21
        if price_prev <= ema21_prev and price_now > ema21_val:
            score += 1.5
            momentum_events.append({
                "event": "price_cross_ema21_bullish",
                "label": f"Price crossed above EMA21 (${ema21_val:.2f})",
                "value": round(price_now, 2),
                "direction": "bullish",
                "strength": "moderate",
            })
            signals.append({"name": "price_above_ema21", "direction": "bullish"})

        # Price crossed below EMA21
        elif price_prev >= ema21_prev and price_now < ema21_val:
            score -= 1.5
            momentum_events.append({
                "event": "price_cross_ema21_bearish",
                "label": f"Price crossed below EMA21 (${ema21_val:.2f})",
                "value": round(price_now, 2),
                "direction": "bearish",
                "strength": "moderate",
            })
            signals.append({"name": "price_below_ema21", "direction": "bearish"})

        elif price_now > ema21_val:
            score += 0.5
            signals.append({"name": "price_above_ema21", "direction": "bullish"})

    # OBV trend
    obv = ta.obv(close, volume)
    if obv is not None and not obv.empty and len(obv) >= 10:
        obv_ema = ta.ema(obv, length=10)
        if obv_ema is not None and not obv_ema.empty:
            obv_val = float(obv.iloc[-1])
            obv_ema_val = float(obv_ema.iloc[-1])
            if obv_val > obv_ema_val:
                score += 0.5
                signals.append({"name": "obv_rising", "direction": "bullish"})
            else:
                score -= 0.5
                signals.append({"name": "obv_falling", "direction": "bearish"})

    # Volume spike check (today vs 20-day avg)
    if len(volume) >= 20:
        avg_vol = float(volume.iloc[-21:-1].mean())
        today_vol = float(volume.iloc[-1])
        vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0
        signals.append({"name": "vol_ratio", "value": round(vol_ratio, 2)})
        if vol_ratio >= 2.0:
            score += 1.5
            momentum_events.append({
                "event": "volume_spike_2x",
                "label": f"Volume spike {vol_ratio:.1f}× average (institutional interest)",
                "value": round(vol_ratio, 2),
                "direction": "confirming",
                "strength": "strong",
            })
            signals.append({"name": "vol_spike_2x", "direction": "confirming"})
        elif vol_ratio > 1.5:
            score += 1.0
            signals.append({"name": "vol_spike", "direction": "confirming"})

    # Momentum deceleration — Kakushadze Alpha017
    # close[-1] - 2×close[-2] + close[-3] (second derivative of price)
    # Negative at RSI >65 = momentum exhaustion → bear structure signal
    if len(close) >= 3 and rsi_s is not None and len(rsi_s) >= 1:
        rsi_now = float(rsi_s.iloc[-1])
        momentum_accel = float(close.iloc[-1]) - 2 * float(close.iloc[-2]) + float(close.iloc[-3])
        signals.append({"name": "momentum_accel_alpha017", "value": round(momentum_accel, 4)})
        if rsi_now > 65 and momentum_accel < 0:
            score -= 1.0
            signals.append({"name": "momentum_exhaustion", "direction": "bearish",
                             "note": "Momentum decelerating at high RSI (Alpha017) — potential reversal"})
            momentum_events.append({
                "event": "momentum_deceleration",
                "label": f"Momentum exhaustion: second derivative negative at RSI={rsi_now:.0f}",
                "value": round(momentum_accel, 4),
                "direction": "bearish",
                "strength": "moderate",
            })
        elif rsi_now < 45 and momentum_accel > 0:
            score += 0.5
            signals.append({"name": "momentum_reacceleration", "direction": "bullish",
                             "note": "Momentum re-accelerating at low RSI — potential bounce"})

    # 1-month short-term momentum (most predictive in current crowded markets — per research)
    if len(close) >= 21:
        ret_1m = (float(close.iloc[-1]) - float(close.iloc[-21])) / float(close.iloc[-21])
        signals.append({"name": "return_1m", "value": round(ret_1m * 100, 1)})
        if ret_1m > 0.05:
            score += 0.5
            signals.append({"name": "momentum_1m_positive", "direction": "bullish"})
        elif ret_1m < -0.05:
            score -= 0.5
            signals.append({"name": "momentum_1m_negative", "direction": "bearish"})

    score = max(0.0, min(10.0, score))

    # Direction from RSI + MACD agreement
    bull_sigs = sum(1 for s in signals if s.get("direction") == "bullish")
    bear_sigs = sum(1 for s in signals if s.get("direction") == "bearish")
    if bull_sigs > bear_sigs:
        direction = "bullish"
    elif bear_sigs > bull_sigs:
        direction = "bearish"

    # Daniel-Moskowitz gate: when SPX is in a high-RV regime, BULLISH momentum
    # is suppressed (the regime where momentum historically crashes); bearish
    # momentum is left alone — that's the side the crash protects.
    if crash_regime and direction == "bullish":
        direction = "neutral"
        score = min(score, 5.0)

    # Attach crossover events as a special signal for the watchlist agent
    if momentum_events:
        signals.append({"name": "momentum_events", "events": momentum_events})

    event_labels = [e["label"] for e in momentum_events] if momentum_events else []
    summary_parts = [f"RSI/MACD/OBV momentum {'bullish' if direction=='bullish' else 'bearish' if direction=='bearish' else 'mixed'}"]
    if event_labels:
        summary_parts.append(f"Events: {'; '.join(event_labels)}")

    weight = 7.0
    return CategoryScore(
        name="momentum", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=" | ".join(summary_parts),
    )
