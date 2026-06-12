"""NEW: Earnings-Adjusted IV — strip earnings spike from IVR to get true base IV."""

from datetime import date, timedelta
import math
import numpy as np
import pandas as pd
from loguru import logger

from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    if not chain or df.empty:
        return CategoryScore("earnings_adj_iv", 0.0, 5.0, 0.0, "neutral", [], "No data")

    # Try to detect earnings proximity from chain structure
    # Proxy: if near-term IV >> longer-term IV, earnings are likely embedded
    today = date.today()
    exp_ivs: dict[str, float] = {}

    for c in chain:
        g = c.get("greeks", {}) or {}
        iv = float(g.get("mid_iv") or c.get("iv") or 0)
        exp = c.get("expiration_date") or c.get("expiry")
        if iv > 0 and exp:
            exp_str = str(exp)[:10]
            if exp_str not in exp_ivs:
                exp_ivs[exp_str] = []
            exp_ivs[exp_str].append(iv)

    if len(exp_ivs) < 2:
        return CategoryScore("earnings_adj_iv", 0.0, 5.0, 0.0, "neutral",
                           signals, "Insufficient expirations for earnings-adj analysis")

    avg_by_exp = {k: float(np.mean(v)) for k, v in exp_ivs.items()}
    sorted_exps = sorted(avg_by_exp.items())

    # Earnings detection heuristic:
    # If the near-term expiry IV is >30% higher than the next expiry, earnings are likely in it
    near_exp, near_iv  = sorted_exps[0]
    far_exp,  far_iv   = sorted_exps[1]
    near_dte = (date.fromisoformat(near_exp) - today).days
    far_dte  = (date.fromisoformat(far_exp) - today).days

    earnings_in_near = False
    if near_iv > far_iv * 1.30 and near_dte <= 21:
        earnings_in_near = True
        signals.append({
            "name": "earnings_embedded_in_near_term",
            "near_exp": near_exp,
            "near_iv_pct": round(near_iv * 100, 1),
            "far_iv_pct": round(far_iv * 100, 1),
            "note": "Near-term IV elevated: likely earnings spike embedded",
        })

    # Base IV (earnings-stripped) = far expiry IV
    base_iv = far_iv
    signals.append({"name": "base_iv_adj_pct", "value": round(base_iv * 100, 1)})

    # Earnings IV expected move: IV × √(DTE/365)
    if earnings_in_near:
        expected_move_pct = near_iv * math.sqrt(near_dte / 365)
        signals.append({
            "name": "expected_earnings_move_pct",
            "value": round(expected_move_pct * 100, 1),
            "note": f"Market pricing ±{round(expected_move_pct*100,1)}% move at earnings",
        })
        score += 1  # earnings events = elevated opportunity
        signals.append({"name": "earnings_straddle_candidate", "direction": "straddle"})

    # If using base_iv for IVR calculation
    if len(df) >= 252:
        log_returns = np.log(df["close"].values[1:] / df["close"].values[:-1])
        hv_series = pd.Series([
            np.std(log_returns[max(0, i-20):i]) * math.sqrt(252)
            for i in range(20, len(log_returns) + 1)
        ])
        adj_ivr = round(float((hv_series < base_iv).mean() * 100), 1)
        signals.append({"name": "earnings_adj_iv_percentile", "value": adj_ivr})
        if adj_ivr > 70:
            score += 1
            signals.append({"name": "adj_iv_elevated", "direction": "sell_premium"})
        elif adj_ivr < 35:
            score += 0.5
            signals.append({"name": "adj_iv_cheap", "direction": "buy_volatility"})

    weight = 0.0
    return CategoryScore(
        name="earnings_adj_iv", weight=weight,
        raw_score=score, weighted_score=0.0,
        direction="neutral", signals=signals,
        summary=f"Base IV (adj)={round(base_iv*100,1)}% | Earnings embedded: {earnings_in_near}",
    )
