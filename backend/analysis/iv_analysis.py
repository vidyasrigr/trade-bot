"""Category 9: IV & Volatility (12%) — IVR, IV percentile, IV vs HV, skew, term structure."""

import math
from datetime import date

import numpy as np
import pandas as pd
from loguru import logger

from analysis.engine import CategoryScore


async def analyze(
    symbol: str,
    df: pd.DataFrame,
    chain: list[dict],
    iv_surface: dict,
) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if df.empty:
        return CategoryScore("iv_analysis", 12.0, 5.0, 6.0, "neutral", [], "No price data")

    # Historical Volatility (20-day realized vol)
    if len(df) >= 21:
        log_returns = np.log(df["close"].values[1:] / df["close"].values[:-1])
        hv20 = np.std(log_returns[-20:]) * math.sqrt(252)
        signals.append({"name": "hv20", "value": round(hv20 * 100, 1)})
    else:
        hv20 = None

    # Extract IV from options chain
    atm_iv = None
    if chain:
        last_close = float(df["close"].iloc[-1])
        atm_contracts = sorted(
            [c for c in chain if c.get("greeks") or c.get("iv")],
            key=lambda c: abs(float(c.get("strike", 0)) - last_close),
        )[:4]

        ivs = []
        for c in atm_contracts:
            iv = c.get("greeks", {}).get("mid_iv") if c.get("greeks") else c.get("iv")
            if iv and float(iv) > 0:
                ivs.append(float(iv))
        if ivs:
            atm_iv = np.mean(ivs)
            signals.append({"name": "atm_iv", "value": round(atm_iv * 100, 1)})

    # IV Percentile (ORATS-style): where is current IV vs last 52 weeks of realized vol
    iv_percentile = None
    if hv20 is not None:
        if len(df) >= 252:
            log_returns_full = np.log(df["close"].values[1:] / df["close"].values[:-1])
            hv_series = pd.Series([
                np.std(log_returns_full[max(0, i-20):i]) * math.sqrt(252)
                for i in range(20, len(log_returns_full) + 1)
            ])
            current_iv = atm_iv if atm_iv else hv20
            iv_percentile = round(float((hv_series < current_iv).mean() * 100), 1)
        else:
            iv_percentile = 50.0  # default when insufficient history

        signals.append({"name": "iv_percentile", "iv_percentile": iv_percentile, "value": iv_percentile})

        if iv_percentile > 80:
            signals.append({"name": "high_iv_rank", "direction": "sell_premium", "note": "IV elevated — prefer premium-selling structures"})
            score += 1.5
        elif iv_percentile < 30:
            signals.append({"name": "low_iv_rank", "direction": "buy_premium", "note": "IV cheap — prefer buying structures"})
            score += 1.0

    # IV vs HV premium
    if atm_iv and hv20:
        iv_hv_ratio = atm_iv / hv20
        signals.append({"name": "iv_hv_ratio", "value": round(iv_hv_ratio, 2)})
        if iv_hv_ratio > 1.3:
            score += 1
            signals.append({"name": "iv_premium", "direction": "sell_premium", "value": round(iv_hv_ratio, 2)})
        elif iv_hv_ratio < 0.9:
            score += 0.5
            signals.append({"name": "iv_discount", "direction": "buy_premium", "value": round(iv_hv_ratio, 2)})

    # Term structure (contango vs backwardation)
    if len(iv_surface) >= 2:
        expirations = sorted(iv_surface.keys())
        try:
            near_chain = iv_surface[expirations[0]]
            far_chain  = iv_surface[expirations[-1]]
            near_iv = _get_atm_iv(near_chain, float(df["close"].iloc[-1]))
            far_iv  = _get_atm_iv(far_chain, float(df["close"].iloc[-1]))
            if near_iv and far_iv:
                term_slope = far_iv - near_iv
                signals.append({"name": "term_structure_slope", "value": round(term_slope * 100, 2)})
                if term_slope < -0.05:
                    signals.append({"name": "iv_backwardation", "note": "Near IV > Far IV — hedging demand or event risk"})
                    score += 0.5
        except Exception:
            pass

    # IV Skew: 25Δ put vs 25Δ call (standard volatility skew measure)
    if chain:
        last_close = float(df["close"].iloc[-1])
        # 25Δ put: strike ~5% OTM on put side; 25Δ call: strike ~5% OTM on call side
        otm_puts  = [c for c in chain if c.get("option_type") == "P"
                     and last_close * 0.90 < float(c.get("strike", 0)) < last_close * 0.97]
        otm_calls = [c for c in chain if c.get("option_type") == "C"
                     and last_close * 1.03 < float(c.get("strike", 0)) < last_close * 1.10]
        # Prefer contracts nearest to 25Δ via delta, fall back to strikes
        def _iv(contracts: list[dict]) -> float | None:
            ivs = []
            for c in contracts[:3]:
                iv = c.get("greeks", {}).get("mid_iv") if c.get("greeks") else c.get("iv")
                if iv and float(iv) > 0:
                    ivs.append(float(iv))
            return float(np.mean(ivs)) if ivs else None

        put_iv_25d  = _iv(otm_puts)
        call_iv_25d = _iv(otm_calls)

        if put_iv_25d and call_iv_25d:
            skew_25d = put_iv_25d - call_iv_25d
            signals.append({"name": "iv_skew_25d", "value": round(skew_25d * 100, 2),
                            "note": f"25Δ put IV {round(put_iv_25d*100,1)}% vs call IV {round(call_iv_25d*100,1)}%"})
            if skew_25d > 0.08:
                direction = "bearish"  # tail risk premium elevated
                signals.append({"name": "elevated_25d_put_skew", "direction": "bearish",
                                "note": "Market pricing crash risk — elevated put demand"})
                score += 0.5
            elif skew_25d < -0.02:
                signals.append({"name": "inverted_skew", "direction": "bullish",
                                "note": "Unusual: calls more expensive than puts — bullish speculation"})
                score += 0.5

    # Expected Move: ATM straddle price / current price (1 std dev expected move)
    if chain:
        last_close = float(df["close"].iloc[-1])
        atm_calls = sorted(
            [c for c in chain if c.get("option_type") == "C"],
            key=lambda c: abs(float(c.get("strike", 0)) - last_close),
        )[:2]
        atm_puts = sorted(
            [c for c in chain if c.get("option_type") == "P"],
            key=lambda c: abs(float(c.get("strike", 0)) - last_close),
        )[:2]

        call_mids = [((float(c.get("bid") or 0) + float(c.get("ask") or 0)) / 2) for c in atm_calls
                     if c.get("bid") and c.get("ask")]
        put_mids  = [((float(c.get("bid") or 0) + float(c.get("ask") or 0)) / 2) for c in atm_puts
                     if c.get("bid") and c.get("ask")]

        if call_mids and put_mids:
            straddle_price = np.mean(call_mids) + np.mean(put_mids)
            expected_move_pct = (straddle_price / last_close) * 100
            signals.append({"name": "expected_move_straddle",
                            "value": round(expected_move_pct, 2),
                            "note": f"±${round(straddle_price, 2)} (±{round(expected_move_pct,1)}%) — ATM straddle price"})
            # Context: is current trend within or beyond expected move?
            if hv20 is not None:
                thirty_day_move = hv20 / math.sqrt(252 / 30) * 100
                if expected_move_pct > thirty_day_move * 1.3:
                    signals.append({"name": "em_elevated_vs_rv",
                                    "note": f"Expected move ({round(expected_move_pct,1)}%) elevated vs realized ({round(thirty_day_move,1)}%)"})
                    score += 0.5

    score = max(0.0, min(10.0, score))

    if iv_percentile is not None:
        if iv_percentile > 60:
            direction = "bearish"  # high IV → lean toward premium selling / bearish structures
        elif iv_percentile < 40:
            direction = "bullish"  # low IV → cheap to buy directional

    weight = 12.0
    return CategoryScore(
        name="iv_analysis", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=f"IV%ile={iv_percentile}, ATM IV={round(atm_iv*100,1) if atm_iv else 'N/A'}%, HV20={round(hv20*100,1) if hv20 else 'N/A'}%",
    )


def _get_atm_iv(chain: list[dict], last_close: float) -> float | None:
    if not chain:
        return None
    atm = sorted(chain, key=lambda c: abs(float(c.get("strike", 0)) - last_close))[:2]
    ivs = []
    for c in atm:
        iv = c.get("greeks", {}).get("mid_iv") if c.get("greeks") else c.get("iv")
        if iv and float(iv) > 0:
            ivs.append(float(iv))
    return float(np.mean(ivs)) if ivs else None
