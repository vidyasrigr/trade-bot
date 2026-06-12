"""Category 11: Greeks (8%) — delta/theta/vega/gamma analysis for position sizing."""

import math
from datetime import date

import numpy as np
import pandas as pd
from loguru import logger

from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if not chain or df.empty:
        return CategoryScore("greeks", 8.0, 5.0, 4.0, "neutral", [], "No options chain")

    last_close = float(df["close"].iloc[-1])
    today = date.today()

    # ATM contract analysis
    atm_contracts = sorted(
        [c for c in chain if c.get("greeks") or (c.get("delta") is not None)],
        key=lambda c: abs(float(c.get("strike", 0)) - last_close),
    )[:4]

    if not atm_contracts:
        return CategoryScore("greeks", 8.0, 5.0, 4.0, "neutral", [], "No greek data in chain")

    deltas, gammas, thetas, vegas = [], [], [], []
    for c in atm_contracts:
        g = c.get("greeks", c)  # some APIs put greeks at top level
        try:
            if g.get("delta"):  deltas.append(float(g["delta"]))
            if g.get("gamma"):  gammas.append(float(g["gamma"]))
            if g.get("theta"):  thetas.append(float(g["theta"]))
            if g.get("vega"):   vegas.append(float(g["vega"]))
        except (TypeError, ValueError):
            pass

    if deltas:
        avg_delta = np.mean(deltas)
        signals.append({"name": "atm_delta", "value": round(avg_delta, 3)})

    if gammas:
        avg_gamma = np.mean(gammas)
        signals.append({"name": "atm_gamma", "value": round(avg_gamma, 4)})
        if avg_gamma > 0.05:
            signals.append({"name": "high_gamma", "note": "High gamma risk near expiry or ATM"})

        # Gamma Acceleration (Speed = dGamma/dS): approximated via finite difference across nearby strikes
        # High speed means delta changes very rapidly as price moves — important near ATM pre-earnings
        strikes_sorted = sorted(
            [c for c in atm_contracts if c.get("greeks") or c.get("gamma")],
            key=lambda c: float(c.get("strike", 0))
        )
        if len(strikes_sorted) >= 3:
            try:
                g_vals = []
                s_vals = []
                for c in strikes_sorted:
                    g_raw = c.get("greeks", c)
                    g = g_raw.get("gamma") if g_raw else None
                    if g:
                        g_vals.append(float(g))
                        s_vals.append(float(c.get("strike", 0)))
                if len(g_vals) >= 3:
                    # Central finite difference: dGamma/dS ≈ (G[+1] - G[-1]) / (2*ΔS)
                    mid = len(g_vals) // 2
                    ds = (s_vals[mid + 1] - s_vals[mid - 1]) / 2 if mid + 1 < len(s_vals) else 1
                    gamma_accel = (g_vals[min(mid + 1, len(g_vals)-1)] - g_vals[max(mid - 1, 0)]) / (2 * ds) if ds > 0 else 0
                    signals.append({"name": "gamma_acceleration", "value": round(gamma_accel, 6),
                                    "note": "dGamma/dS (speed): how fast delta changes per $1 move"})
                    if abs(gamma_accel) > 0.001:
                        signals.append({"name": "high_gamma_acceleration",
                                        "note": "Delta changes rapidly — position requires active monitoring near ATM"})
                        score -= 0.3  # elevated risk, minor penalty
            except Exception:
                pass

    if thetas:
        avg_theta = np.mean(thetas)
        signals.append({"name": "atm_theta_daily", "value": round(avg_theta, 3)})
        # Theta/premium ratio: how much premium erodes daily
        mid_price = None
        for c in atm_contracts:
            bid = float(c.get("bid") or 0)
            ask = float(c.get("ask") or 0)
            if bid > 0 and ask > 0:
                mid_price = (bid + ask) / 2
                break
        if mid_price and mid_price > 0:
            theta_ratio = abs(avg_theta) / mid_price
            signals.append({"name": "theta_premium_ratio_daily", "value": round(theta_ratio * 100, 2)})
            if theta_ratio > 0.03:
                signals.append({"name": "high_theta_decay", "note": ">3% daily theta erosion"})
                score -= 0.5

    if vegas:
        avg_vega = np.mean(vegas)
        signals.append({"name": "atm_vega", "value": round(avg_vega, 3)})

    # Greeks-based direction assessment
    calls_in_atm = [c for c in atm_contracts if c.get("option_type") == "C"]
    if calls_in_atm:
        call = calls_in_atm[0]
        g = call.get("greeks", call)
        call_delta = g.get("delta")
        if call_delta:
            delta_val = float(call_delta)
            if 0.45 < delta_val < 0.60:
                score += 1
                signals.append({"name": "atm_call_delta_ideal", "value": delta_val})
            if delta_val > 0.70:
                direction = "bullish"
                signals.append({"name": "deep_itm_call", "direction": "bullish"})

    # DTE check for theta decay warning
    for c in atm_contracts[:1]:
        expiry_str = c.get("expiration_date") or c.get("expiry") or c.get("expiration")
        if expiry_str:
            try:
                exp_date = date.fromisoformat(str(expiry_str)[:10])
                dte = (exp_date - today).days
                signals.append({"name": "dte", "value": dte})
                if dte < 14:
                    score -= 1
                    signals.append({"name": "low_dte_risk", "note": "< 14 DTE — high theta decay, gamma risk"})
                elif 21 <= dte <= 60:
                    score += 0.5
                    signals.append({"name": "ideal_dte_range", "direction": "favorable"})
            except Exception:
                pass

    score = max(0.0, min(10.0, score))
    weight = 8.0
    return CategoryScore(
        name="greeks", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=f"ATM delta={round(np.mean(deltas),3) if deltas else 'N/A'}, theta={round(np.mean(thetas),3) if thetas else 'N/A'}/day",
    )
