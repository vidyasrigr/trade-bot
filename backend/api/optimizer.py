"""
Options return optimizer — strike/expiry grid with P(+30%) / P(+100%) per contract.

Uses REAL data: last close + HV20 from yfinance, ATM IV from the Tradier chain
when available (falls back to HV with the fallback flagged in the response).
Replaces the frontend mock that priced NVDA at a hardcoded $1,247.50.
"""

import math
from datetime import date, timedelta

from fastapi import HTTPException
from loguru import logger
from scipy.stats import norm


def _bs_call(s: float, k: float, t: float, sigma: float) -> float:
    if t <= 0 or sigma <= 0:
        return max(0.0, s - k)
    d1 = (math.log(s / k) + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return s * norm.cdf(d1) - k * norm.cdf(d2)


def _bs_call_delta(s: float, k: float, t: float, sigma: float) -> float:
    if t <= 0:
        return 1.0 if s > k else 0.0
    d1 = (math.log(s / k) + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    return float(norm.cdf(d1))


def _prob_above(s: float, target: float, t: float, sigma: float) -> float:
    """P(S_T >= target) under driftless lognormal."""
    if target <= s:
        return 1.0
    if t <= 0 or sigma <= 0:
        return 0.0
    d2 = (math.log(s / target) - 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    return float(norm.cdf(d2))


def _prob_below(s: float, target: float, t: float, sigma: float) -> float:
    if target >= s:
        return 1.0
    if t <= 0 or sigma <= 0:
        return 0.0
    return 1.0 - _prob_above(s, target, t, sigma)


def _atm_iv_from_chain(chain: list[dict], spot: float) -> float | None:
    """Median mid-IV of the few contracts nearest the money."""
    ivs = []
    for c in chain:
        greeks = c.get("greeks") or {}
        iv = greeks.get("mid_iv") or greeks.get("smv_vol")
        strike = c.get("strike")
        if iv and strike and abs(float(strike) - spot) / spot < 0.05:
            ivs.append(float(iv))
    if not ivs:
        return None
    ivs.sort()
    return ivs[len(ivs) // 2]


async def compute_optimizer(symbol: str) -> dict:
    from data.market import get_ohlcv_yfinance

    df = get_ohlcv_yfinance(symbol, period="1y")
    if df is None or df.empty or len(df) < 60:
        raise HTTPException(404, f"Insufficient price history for {symbol}")

    spot = float(df["close"].iloc[-1])
    rets = df["close"].pct_change().dropna()
    hv20 = float(rets.tail(20).std() * math.sqrt(252))
    if hv20 <= 0:
        raise HTTPException(422, f"Cannot estimate volatility for {symbol}")

    # HV rank over the past year as IV-percentile proxy (honest fallback)
    rolling_hv = rets.rolling(20).std().dropna() * math.sqrt(252)
    hv_rank = float((rolling_hv < hv20).mean() * 100) if len(rolling_hv) > 30 else 50.0

    # Direction + rough trend score from 20d momentum
    ret_20 = float(df["close"].iloc[-1] / df["close"].iloc[-21] - 1) if len(df) >= 21 else 0.0
    direction = "bullish" if ret_20 >= -0.03 else "bearish"
    trend_score = max(20, min(80, round(50 + ret_20 * 400)))

    # Try real ATM IV from Tradier; fall back to HV20
    iv = None
    iv_source = "hv20_fallback"
    try:
        from data.tradier import get_tradier
        chain = await get_tradier().get_best_chain(symbol, min_dte=14, max_dte=45)
        if chain:
            iv = _atm_iv_from_chain(chain, spot)
            if iv:
                iv_source = "tradier_atm"
    except Exception as e:
        logger.debug(f"Optimizer: Tradier chain unavailable for {symbol}: {e}")
    if not iv:
        iv = hv20

    iv_pct = round(hv_rank)
    today = date.today()
    expiries = [
        {"label": "14d", "dte": 14},
        {"label": "21d", "dte": 21},
        {"label": "30d", "dte": 30},
    ]
    is_call = direction != "bearish"
    strike_offsets = (
        [-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10]
        if not is_call
        else [-0.05, 0.0, 0.03, 0.06, 0.10, 0.14, 0.18, 0.22]
    )

    rows = []
    for exp in expiries:
        dte = exp["dte"]
        t = dte / 252.0
        expiry_date = (today + timedelta(days=dte)).isoformat()

        for offset in strike_offsets:
            strike = round(spot * (1 + offset) / 0.5) * 0.5
            call_px = _bs_call(spot, strike, t, iv)
            opt_mid = call_px if is_call else call_px - spot + strike
            opt_mid = round(max(0.05, opt_mid), 2)

            call_delta = _bs_call_delta(spot, strike, t, iv)
            delta_abs = abs(call_delta if is_call else call_delta - 1.0)
            if delta_abs < 0.05 or opt_mid < 0.05:
                continue

            def _target(gain: float) -> tuple[float, float, int]:
                move = (gain * opt_mid) / delta_abs
                tgt = spot + move if is_call else spot - move
                move_pct = abs(move / spot * 100)
                prob = (
                    _prob_above(spot, tgt, t, iv) if is_call else _prob_below(spot, tgt, t, iv)
                )
                return round(tgt, 2), round(move_pct, 1), round(prob * 100)

            tgt30, move30, prob30 = _target(0.30)
            tgt100, move100, prob100 = _target(1.00)

            conf = 40
            conf += round((trend_score - 50) * 0.4)
            if iv_pct < 35:
                conf += 12
            elif iv_pct < 50:
                conf += 6
            elif iv_pct > 65:
                conf -= 8
            if 14 <= dte <= 21:
                conf += 6
            elif dte < 7:
                conf -= 15
            if 0.35 <= delta_abs <= 0.55:
                conf += 8
            elif delta_abs < 0.15:
                conf -= 10
            conf += round(prob30 * 0.15)
            conf = max(10, min(95, conf))

            recommended = conf >= 60 and prob30 >= 35 and dte >= 14 and delta_abs >= 0.25
            rows.append({
                "expiry": expiry_date,
                "dte": dte,
                "strike": strike,
                "type": "call" if is_call else "put",
                "option_price": opt_mid,
                "iv_pct": round(iv * 100),
                "delta": round(delta_abs, 2),
                "target_price_30": tgt30,
                "move_pct_30": move30,
                "prob_30": prob30,
                "conf_30": conf,
                "target_price_100": tgt100,
                "move_pct_100": move100,
                "prob_100": max(2, prob100),
                "conf_100": max(10, conf - 18),
                "recommended": recommended,
                "rationale": (
                    f"{dte}d {'call' if is_call else 'put'}, Δ{round(delta_abs * 100)}: "
                    f"{prob30}% chance of +30% with {move30:.1f}% underlying move needed"
                ) if recommended else "",
            })

    rows.sort(key=lambda r: (not r["recommended"], -r["conf_30"]))

    if iv_pct > 65:
        note = f"⚠️ Vol rank {iv_pct}th pct — options are EXPENSIVE. Favor spreads over naked buys to cap cost."
    elif iv_pct < 35:
        note = f"✅ Vol rank {iv_pct}th pct — options are CHEAP. Good time to buy directional premium."
    else:
        note = f"ℹ️ Vol rank {iv_pct}th pct — moderate pricing. Debit spreads balance cost vs upside."
    if iv_source == "hv20_fallback":
        note += " (IV from HV20 fallback — Tradier chain unavailable; vol rank is HV-based.)"

    return {
        "symbol": symbol,
        "current_price": round(spot, 2),
        "iv_pct": iv_pct,
        "hv20_pct": round(hv20 * 100),
        "direction": direction,
        "iv_vs_hv": "rich" if iv > hv20 else "cheap",
        "iv_source": iv_source,
        "rows": rows,
        "note": note,
    }
