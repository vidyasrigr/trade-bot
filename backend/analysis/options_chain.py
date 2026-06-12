"""Category 10: Options Chain Selection (10%) — strike/DTE recommendation, liquidity check."""

from datetime import date
import numpy as np
import pandas as pd
from loguru import logger

from analysis.engine import CategoryScore
from core.config import settings


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if not chain:
        return CategoryScore("options_chain", 10.0, 5.0, 5.0, "neutral", [], "No options chain available")

    last_close = float(df["close"].iloc[-1]) if not df.empty else 0
    today = date.today()

    # Separate calls and puts
    calls = [c for c in chain if c.get("option_type") == "C"]
    puts  = [c for c in chain if c.get("option_type") == "P"]

    # Call/Put OI ratio
    total_call_oi = sum(int(c.get("open_interest") or 0) for c in calls)
    total_put_oi  = sum(int(c.get("open_interest") or 0) for c in puts)
    if total_put_oi > 0:
        pc_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 999
        signals.append({"name": "put_call_oi_ratio", "value": round(pc_ratio, 2)})
        if pc_ratio < 0.7:
            score += 1
            direction = "bullish"
            signals.append({"name": "low_put_call_ratio", "direction": "bullish"})
        elif pc_ratio > 1.3:
            score -= 0.5
            signals.append({"name": "high_put_call_ratio", "direction": "bearish"})

    # Find best strike for directional trade (target: ~0.40 delta call for bullish)
    best_call = _find_target_delta_contract(calls, target_delta=settings.DIRECTIONAL_DELTA)
    best_put  = _find_target_delta_contract(puts, target_delta=-settings.DIRECTIONAL_DELTA)

    if best_call:
        bid = float(best_call.get("bid") or 0)
        ask = float(best_call.get("ask") or 0)
        spread_pct = (ask - bid) / ((ask + bid) / 2) if (ask + bid) > 0 else 1.0
        signals.append({
            "name": "best_call_strike",
            "strike": best_call.get("strike"),
            "delta": best_call.get("greeks", {}).get("delta") if best_call.get("greeks") else None,
            "bid": bid,
            "ask": ask,
            "spread_pct": round(spread_pct * 100, 1),
            "oi": best_call.get("open_interest"),
        })
        if spread_pct < 0.10:
            score += 1
            signals.append({"name": "tight_call_spread", "direction": "good_liquidity"})

    if best_put:
        signals.append({
            "name": "best_put_strike",
            "strike": best_put.get("strike"),
            "delta": best_put.get("greeks", {}).get("delta") if best_put.get("greeks") else None,
        })

    # Max pain (strike with maximum OI)
    oi_by_strike: dict[float, int] = {}
    for c in chain:
        strike = float(c.get("strike", 0))
        oi = int(c.get("open_interest") or 0)
        oi_by_strike[strike] = oi_by_strike.get(strike, 0) + oi
    if oi_by_strike:
        max_pain_strike = max(oi_by_strike, key=oi_by_strike.get)
        signals.append({"name": "max_pain", "value": max_pain_strike})
        pct_from_max_pain = (last_close - max_pain_strike) / last_close if last_close > 0 else 0
        signals.append({"name": "pct_from_max_pain", "value": round(pct_from_max_pain * 100, 1)})

    # Volume spike in calls
    call_vols = [int(c.get("volume") or 0) for c in calls]
    if call_vols:
        total_call_vol = sum(call_vols)
        signals.append({"name": "total_call_volume", "value": total_call_vol})

    score = max(0.0, min(10.0, score))
    weight = 10.0
    return CategoryScore(
        name="options_chain", weight=weight,
        raw_score=score, weighted_score=weight * score / 10,
        direction=direction, signals=signals,
        summary=f"P/C OI ratio: {round(total_put_oi/max(total_call_oi,1),2)}; Max pain: ${max_pain_strike if oi_by_strike else 'N/A'}",
    )


def _find_target_delta_contract(contracts: list[dict], target_delta: float) -> dict | None:
    """Find the contract closest to target_delta."""
    if not contracts:
        return None
    with_delta = []
    for c in contracts:
        g = c.get("greeks", {})
        d = g.get("delta") if g else c.get("delta")
        if d is not None:
            with_delta.append((abs(float(d) - abs(target_delta)), c))
    if not with_delta:
        return None
    with_delta.sort(key=lambda x: x[0])
    return with_delta[0][1]
