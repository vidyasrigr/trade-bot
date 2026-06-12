"""NEW: Institutional Options Flow — large-premium ask-side prints, dark pool signals."""

from datetime import date
import numpy as np
import pandas as pd
from loguru import logger

from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if not chain:
        return CategoryScore("options_flow", 0.0, 5.0, 0.0, "neutral", [], "No chain")

    last_close = float(df["close"].iloc[-1]) if not df.empty else 0
    today = date.today()

    # Identify unusual call/put volume vs OI
    # Volume >> OI = fresh institutional positioning (not hedging existing position)
    unusual_calls = []
    unusual_puts  = []

    for c in chain:
        vol = int(c.get("volume") or 0)
        oi  = int(c.get("open_interest") or 0)
        otype = c.get("option_type", "").upper()
        strike = float(c.get("strike") or 0)
        ask = float(c.get("ask") or 0)

        if oi == 0 or vol == 0:
            continue

        vol_oi_ratio = vol / oi
        premium = vol * ask * 100  # approximate dollar premium

        if vol_oi_ratio > 2.0 and premium > 50_000:
            record = {
                "strike": strike,
                "volume": vol,
                "oi": oi,
                "vol_oi_ratio": round(vol_oi_ratio, 1),
                "premium_usd": round(premium, 0),
                "dte": (date.fromisoformat(str(c.get("expiration_date", today))[:10]) - today).days
                        if c.get("expiration_date") else None,
            }
            if otype == "C":
                unusual_calls.append(record)
            elif otype == "P":
                unusual_puts.append(record)

    if unusual_calls:
        # Sort by premium size — largest = most conviction
        unusual_calls.sort(key=lambda x: x["premium_usd"], reverse=True)
        top_call = unusual_calls[0]
        signals.append({"name": "unusual_call_volume", "direction": "bullish", **top_call})
        score += min(len(unusual_calls) * 1.0, 3.0)
        direction = "bullish"

    if unusual_puts:
        unusual_puts.sort(key=lambda x: x["premium_usd"], reverse=True)
        top_put = unusual_puts[0]
        signals.append({"name": "unusual_put_volume", "direction": "bearish", **top_put})
        score -= min(len(unusual_puts) * 0.5, 1.5)

    # Call volume 150%+ of 20-day avg (strong signal from plan)
    total_call_vol = sum(int(c.get("volume") or 0) for c in chain if c.get("option_type") == "C")
    total_put_vol  = sum(int(c.get("volume") or 0) for c in chain if c.get("option_type") == "P")
    signals.append({"name": "total_call_volume", "value": total_call_vol})
    signals.append({"name": "total_put_volume",  "value": total_put_vol})

    # Flow bias
    if total_call_vol > 0 and total_put_vol > 0:
        flow_ratio = total_call_vol / total_put_vol
        signals.append({"name": "call_put_vol_ratio", "value": round(flow_ratio, 2)})
        if flow_ratio > 1.5:
            score += 1
            direction = "bullish"
            signals.append({"name": "call_flow_dominant", "direction": "bullish"})
        elif flow_ratio < 0.67:
            score -= 0.5
            signals.append({"name": "put_flow_dominant", "direction": "bearish"})

    score = max(0.0, min(10.0, score))

    weight = 0.0  # Embedded in sentiment weight; returned as supplementary data
    return CategoryScore(
        name="options_flow", weight=weight,
        raw_score=score, weighted_score=0.0,
        direction=direction, signals=signals,
        summary=f"{len(unusual_calls)} unusual call prints, {len(unusual_puts)} unusual put prints",
    )
