"""Category 13: Sentiment & Smart Money (5%)"""

import pandas as pd
from loguru import logger
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    # Incorporate options_flow signals
    try:
        from analysis.options_flow import analyze as flow_analyze
        flow = await flow_analyze(symbol, df, chain)
        for sig in flow.signals:
            if sig.get("name") in ("unusual_call_volume", "call_flow_dominant"):
                score += 0.5
                direction = "bullish"
            elif sig.get("name") in ("unusual_put_volume", "put_flow_dominant"):
                score -= 0.3
        signals.extend(flow.signals[:4])
    except Exception:
        pass

    # Short interest (from AV overview).
    # High SI predicts UNDERperformance on average (Drechsler & Drechsler 2014,
    # "The Shorting Premium") — it is squeeze fuel only when a catalyst and price
    # momentum confirm. So: mild bearish on its own, flagged for squeeze detectors.
    try:
        from data.market import get_av
        av = get_av()
        overview = await av.get_overview(symbol)
        short_pct = float(overview.get("ShortPercentOutstanding", 0) or 0)
        if short_pct > 0.15:
            signals.append({"name": "very_high_short_interest", "value": round(short_pct * 100, 1),
                           "note": "Bearish drag on average; squeeze fuel only WITH catalyst + momentum",
                           "direction": "bearish", "squeeze_fuel": True})
            score -= 0.5
        elif short_pct > 0.08:
            signals.append({"name": "elevated_short_interest", "value": round(short_pct * 100, 1),
                           "squeeze_fuel": True})
    except Exception:
        pass

    # GEX flow contribution
    try:
        from analysis.gex_dex import analyze as gex_analyze
        gex = await gex_analyze(symbol, df, chain)
        net_gex = next((s.get("value", 0) for s in gex.signals if s.get("name") == "net_gex"), 0)
        if net_gex and float(net_gex) > 0:
            signals.append({"name": "positive_gex_sentiment", "direction": "stable"})
            score += 0.3
    except Exception:
        pass

    score = max(0.0, min(10.0, score))
    weight = 5.0
    return CategoryScore("sentiment", weight, score, weight * score / 10, direction, signals,
                        "Options flow + short interest + GEX sentiment composite")
