"""Category 12: Trade Structure Analysis (5%) — calls the deterministic selector, scores result quality."""

import pandas as pd
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 7.0  # Default: having a clear structure is good
    direction = "neutral"

    try:
        from scoring.trade_structure import select_structure, TradeStructureInput
        from analysis.volatility_regime import analyze as vr_analyze
        from analysis.iv_analysis import analyze as iv_analyze

        # Get vol regime + IV percentile
        vr_result = await vr_analyze(symbol, df)
        iv_result = await iv_analyze(symbol, df, chain, {})

        vol_regime = "chop"
        iv_pct = 50.0
        for sig in vr_result.signals:
            if "regime" in sig:
                vol_regime = sig["regime"]
                break
        for sig in iv_result.signals:
            if "iv_percentile" in sig:
                iv_pct = sig["iv_percentile"]
                break

        inp = TradeStructureInput(
            vol_regime=vol_regime,
            iv_percentile=iv_pct,
            direction=direction,
            total_score=score,
        )
        structure = select_structure(inp)

        signals.append({
            "name": "recommended_structure",
            "value": structure.strategy,
            "short_strike": structure.short_strike,
            "long_strike": structure.long_strike,
            "target_dte_min": structure.dte_min,
            "target_dte_max": structure.dte_max,
            "target_delta": structure.target_delta,
            "rationale": structure.rationale,
        })
        score = 8.0 if structure.strategy else 5.0
        direction = structure.direction if structure.direction else "neutral"

    except Exception as e:
        signals.append({"name": "structure_error", "note": str(e)[:100]})
        score = 5.0

    weight = 5.0
    return CategoryScore("trade_structure", weight, score, weight * score / 10,
                        direction, signals, f"Recommended: {signals[0].get('value','N/A') if signals else 'N/A'}")
