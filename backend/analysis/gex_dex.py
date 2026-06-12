"""NEW: GEX/DEX/Vanna/Charm — dealer hedging flow predicts S/R levels."""

import numpy as np
import pandas as pd
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if not chain or df.empty:
        return CategoryScore("gex_dex", 0.0, 5.0, 0.0, "neutral", [], "No chain data for GEX")

    last_close = float(df["close"].iloc[-1])

    # GEX = Sum(gamma * OI * 100 * price^2 * 0.01) per strike
    # Positive GEX = market makers dampen moves (buy dips/sell rips)
    # Negative GEX = market makers amplify moves

    call_gex = 0.0
    put_gex  = 0.0
    gex_by_strike: dict[float, float] = {}

    for c in chain:
        g = c.get("greeks", {}) or {}
        gamma = float(g.get("gamma") or c.get("gamma") or 0)
        oi    = float(c.get("open_interest") or 0)
        strike = float(c.get("strike", 0))
        otype  = c.get("option_type", "").upper()

        if gamma == 0 or oi == 0:
            continue

        # GEX contribution (simplified)
        gex_contrib = gamma * oi * 100 * (last_close ** 2) * 0.0001

        if otype == "C":
            call_gex += gex_contrib
            gex_by_strike[strike] = gex_by_strike.get(strike, 0) + gex_contrib
        elif otype == "P":
            put_gex  -= gex_contrib  # puts flip sign
            gex_by_strike[strike] = gex_by_strike.get(strike, 0) - gex_contrib

    net_gex = call_gex + put_gex
    signals.append({"name": "net_gex", "value": round(net_gex, 2)})

    if net_gex > 0:
        score += 1.5
        direction = "neutral"  # positive GEX = pinning behavior
        signals.append({"name": "positive_gex", "direction": "dampening", "note": "MMs buying dips/selling rips — mean reversion"})
    elif net_gex < 0:
        score -= 1
        signals.append({"name": "negative_gex", "direction": "amplifying", "note": "MMs amplifying moves — momentum"})

    # GEX flip level: strike where GEX changes sign (key support/resistance)
    if gex_by_strike:
        sorted_strikes = sorted(gex_by_strike.items())
        flip_levels = []
        for i in range(1, len(sorted_strikes)):
            prev_gex = sorted_strikes[i-1][1]
            curr_gex = sorted_strikes[i][1]
            if (prev_gex > 0) != (curr_gex > 0):  # sign change
                flip_levels.append(sorted_strikes[i][0])
        if flip_levels:
            nearest_flip = min(flip_levels, key=lambda x: abs(x - last_close))
            signals.append({"name": "gex_flip_level", "value": round(nearest_flip, 2)})
            pct_to_flip = (nearest_flip - last_close) / last_close
            signals.append({"name": "pct_to_gex_flip", "value": round(pct_to_flip * 100, 1)})

    # DEX (delta-weighted exposure): sum of delta * OI per strike for market maker net delta
    dex = sum(
        float((c.get("greeks") or {}).get("delta") or c.get("delta") or 0)
        * float(c.get("open_interest") or 0) * 100
        for c in chain
    )
    signals.append({"name": "net_dex", "value": round(dex, 0)})

    weight = 0.0  # GEX embedded in sentiment and options_chain weights
    return CategoryScore(
        name="gex_dex", weight=weight,
        raw_score=score, weighted_score=0.0,
        direction=direction, signals=signals,
        summary=f"Net GEX={round(net_gex,2)} ({'positive=dampening' if net_gex>0 else 'negative=amplifying'}) | DEX={round(dex,0)}",
    )
