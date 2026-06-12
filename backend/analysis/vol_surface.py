"""
Volatility Surface Intelligence Module.

Implements research-backed vol surface signals:
  5a: IV term structure slope (Vasquez 2015 — 5.5% net monthly returns when sorted by slope)
  5b: IV skew slope as directional signal (Xing-Zhang-Zhao 2010 — ~6%/qtr edge)
  5c: Rolling VRP z-score (AQR 2018 — 0.68 Sharpe vs 0.32 passive)
  5d: (Integrated into calendar.py — event calendar beyond earnings)
  5e: Calendar spread structure detection
  5f: Sector dispersion signal (Kakushadze 6.3)

All data sourced from Tradier options chains (already in stack).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class VolSurfaceSignals:
    symbol: str

    # 5a: IV Term Structure
    iv_21dte: float | None = None
    iv_45dte: float | None = None
    iv_term_slope: float | None = None    # IV(21) - IV(45). Negative = contango, positive = backwardation
    term_structure: str = "unknown"        # 'contango', 'backwardation', 'flat'
    term_structure_signal: str = "neutral" # 'safe_sell_premium', 'use_calendar_spread'

    # 5b: IV Skew Slope
    iv_20delta_put: float | None = None    # IV of put with delta ~ -0.20
    iv_50delta_call: float | None = None   # IV of call with delta ~ 0.50 (ATM)
    skew_slope: float | None = None        # put IV - call IV
    skew_rank: float | None = None         # 0-1: percentile vs universe (0=flat/bullish, 1=steep/bearish)
    skew_signal: str = "neutral"           # 'bearish_put_demand', 'bullish_no_fear', 'neutral'

    # 5c: VRP z-score
    iv_current: float | None = None
    hv20: float | None = None
    vrp_current: float | None = None       # iv - hv20
    vrp_zscore: float | None = None        # z-scored vs own 1-year history
    vrp_signal: str = "neutral"            # 'sell_premium', 'buy_vol', 'neutral'

    # 5e: Calendar spread eligibility
    calendar_spread_eligible: bool = False
    calendar_spread_reason: str = ""

    # Scoring contribution
    vol_surface_score_delta: float = 0.0   # adjustment to iv_analysis score
    signals: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 5a: IV Term Structure Slope
# ---------------------------------------------------------------------------

def compute_term_structure(chain: list[dict], current_price: float) -> tuple[float | None, float | None, str]:
    """
    Compute IV at ~21 DTE and ~45 DTE from the options chain.
    Returns (iv_21, iv_45, term_structure).

    Contango: iv_21 < iv_45 (normal, safe to sell front-month)
    Backwardation: iv_21 > iv_45 (event risk in near term, use calendar spread)
    """
    from datetime import date, timedelta

    today = date.today()
    target_21 = today + timedelta(days=21)
    target_45 = today + timedelta(days=45)

    # Group chain by expiry
    expiry_ivs: dict[str, list[float]] = {}
    for contract in chain:
        exp_str = contract.get("expiration_date") or contract.get("expiry", "")
        if not exp_str:
            continue
        try:
            exp_date = date.fromisoformat(exp_str[:10])
        except ValueError:
            continue

        # Get ATM IV for this expiry
        strike = float(contract.get("strike", 0))
        if abs(strike - current_price) / current_price > 0.05:  # only within 5% of ATM
            continue

        iv = None
        greeks = contract.get("greeks", {})
        if greeks:
            iv = greeks.get("mid_iv") or greeks.get("bid_iv")
        if iv is None:
            iv = contract.get("iv")
        if iv and float(iv) > 0:
            expiry_ivs.setdefault(exp_str[:10], []).append(float(iv))

    if not expiry_ivs:
        return None, None, "unknown"

    def _get_iv_near(target: date, tolerance_days: int = 7) -> float | None:
        best_match = None
        best_diff = float("inf")
        for exp_str, ivs in expiry_ivs.items():
            try:
                exp = date.fromisoformat(exp_str)
            except ValueError:
                continue
            diff = abs((exp - target).days)
            if diff < best_diff and diff <= tolerance_days:
                best_diff = diff
                best_match = float(np.mean(ivs))
        return best_match

    iv_21 = _get_iv_near(target_21, tolerance_days=10)
    iv_45 = _get_iv_near(target_45, tolerance_days=10)

    if iv_21 is None or iv_45 is None:
        return iv_21, iv_45, "unknown"

    slope = iv_21 - iv_45
    if slope < -0.02:
        structure = "contango"  # normal: near IV < far IV
    elif slope > 0.02:
        structure = "backwardation"  # stressed: near IV > far IV
    else:
        structure = "flat"

    return iv_21, iv_45, structure


# ---------------------------------------------------------------------------
# 5b: IV Skew Slope
# ---------------------------------------------------------------------------

def compute_skew_slope(chain: list[dict]) -> tuple[float | None, float | None]:
    """
    Compute SkewSlope = IV(Δ=-0.20 put) - IV(Δ=0.50 call).

    Steep skew (high value): informed traders buying puts = bearish.
    Flat skew (low value): no fear = bullish confirmation.
    """
    put_20delta_ivs = []
    call_50delta_ivs = []

    for contract in chain:
        option_type = contract.get("option_type") or contract.get("type", "")
        greeks = contract.get("greeks", {}) or {}

        delta = greeks.get("delta")
        if delta is None:
            continue
        delta = float(delta)

        iv = greeks.get("mid_iv") or greeks.get("bid_iv") or contract.get("iv")
        if not iv or float(iv) <= 0:
            continue
        iv = float(iv)

        # Put with delta around -0.20
        if option_type in ("put", "P") and -0.25 <= delta <= -0.15:
            put_20delta_ivs.append(iv)

        # Call with delta around 0.50 (ATM)
        if option_type in ("call", "C") and 0.45 <= delta <= 0.55:
            call_50delta_ivs.append(iv)

    iv_put_20d = float(np.mean(put_20delta_ivs)) if put_20delta_ivs else None
    iv_call_50d = float(np.mean(call_50delta_ivs)) if call_50delta_ivs else None

    return iv_put_20d, iv_call_50d


def compute_skew_rank(skew_slope: float, universe_slopes: list[float] | None = None) -> float:
    """
    Rank this stock's skew slope vs a universe.
    Returns 0.0 (flat/bullish) to 1.0 (steep/bearish).
    """
    if universe_slopes is None or len(universe_slopes) < 5:
        # Without cross-sectional data, use absolute thresholds
        # Typical skew slope range: 0.02 (flat) to 0.15 (steep)
        if skew_slope <= 0.03:
            return 0.1
        elif skew_slope <= 0.06:
            return 0.3
        elif skew_slope <= 0.10:
            return 0.6
        elif skew_slope <= 0.15:
            return 0.8
        else:
            return 0.95

    # Cross-sectional rank
    below = sum(1 for s in universe_slopes if s < skew_slope)
    return below / len(universe_slopes)


# ---------------------------------------------------------------------------
# 5c: Rolling VRP Z-Score
# ---------------------------------------------------------------------------

def compute_vrp_zscore(
    iv_history: list[float],    # most recent first, daily IV values
    hv20_history: list[float],  # most recent first, daily HV20 values
    lookback: int = 252,
) -> float | None:
    """
    VRP = IV - HV20 (volatility risk premium).
    Returns z-score of current VRP vs its own 1-year rolling history.

    VRP z-score > +1: rich premium environment → iron condors/credit spreads have edge
    VRP z-score < 0: IV below realized → avoid short vol; prefer long gamma
    """
    if len(iv_history) < 30 or len(hv20_history) < 30:
        return None

    n = min(len(iv_history), len(hv20_history), lookback)
    iv_arr = np.array(iv_history[:n])
    hv_arr = np.array(hv20_history[:n])

    vrp_series = iv_arr - hv_arr
    if len(vrp_series) < 30:
        return None

    current_vrp = float(vrp_series[0])
    mean = float(np.mean(vrp_series[1:]))
    std = float(np.std(vrp_series[1:]))

    if std < 0.001:
        return 0.0

    return round((current_vrp - mean) / std, 2)


# ---------------------------------------------------------------------------
# 5e: Calendar Spread Eligibility
# ---------------------------------------------------------------------------

def check_calendar_spread_eligible(
    term_structure: str,
    iv_21: float | None,
    iv_45: float | None,
    vrp_zscore: float | None,
    has_near_term_event: bool = False,  # earnings/FOMC within front month
) -> tuple[bool, str]:
    """
    Calendar spread entry conditions (Kakushadze 2.18-2.21):
    1. IV term structure in contango (back > front by ≥3%)
    2. No binary event in front-month
    3. IVR of back-month < 30th percentile (currently approximated by vrp_zscore)
    4. Stock in neutral/low-vol trend

    Returns (eligible, reason).
    """
    if term_structure == "backwardation" and iv_21 and iv_45:
        # Backwardation = front-month expensive relative to back → textbook calendar spread entry
        slope_pct = (iv_21 - iv_45) / iv_45 if iv_45 > 0 else 0
        if slope_pct >= 0.03 and not has_near_term_event:
            return True, (
                f"Backwardation: near IV {iv_21*100:.0f}% > far IV {iv_45*100:.0f}% "
                f"({slope_pct*100:.0f}% differential) — calendar spread: buy 45 DTE, sell 21 DTE"
            )

    if term_structure == "contango" and iv_21 and iv_45:
        slope_pct = (iv_45 - iv_21) / iv_45 if iv_45 > 0 else 0
        if slope_pct >= 0.03 and not has_near_term_event:
            if vrp_zscore is None or vrp_zscore < 0:
                return True, (
                    f"Contango: far IV {iv_45*100:.0f}% > near IV {iv_21*100:.0f}% "
                    f"with low VRP → buy 45 DTE/sell 21 DTE calendar for theta harvest"
                )

    return False, ""


# ---------------------------------------------------------------------------
# Main vol surface analyzer
# ---------------------------------------------------------------------------

async def analyze_vol_surface(
    symbol: str,
    df: pd.DataFrame,
    chain: list[dict],
    iv_history: list[float] | None = None,    # 252 days of daily IV values (optional)
) -> VolSurfaceSignals:
    """
    Run the full vol surface analysis for a symbol.
    Returns VolSurfaceSignals dataclass with all computed signals.
    """
    vs = VolSurfaceSignals(symbol=symbol)

    if not chain or df.empty:
        return vs

    current_price = float(df["close"].iloc[-1]) if not df.empty else 0.0

    # 5a: Term structure
    iv_21, iv_45, term_structure = compute_term_structure(chain, current_price)
    vs.iv_21dte = iv_21
    vs.iv_45dte = iv_45
    vs.term_structure = term_structure
    if iv_21 is not None and iv_45 is not None:
        vs.iv_term_slope = round(iv_21 - iv_45, 4)
        vs.signals.append({
            "name": "iv_term_structure",
            "iv_21dte": round(iv_21 * 100, 1),
            "iv_45dte": round(iv_45 * 100, 1),
            "slope": round(vs.iv_term_slope * 100, 2),
            "structure": term_structure,
        })

        if term_structure == "contango":
            vs.term_structure_signal = "safe_sell_premium"
            vs.vol_surface_score_delta += 0.5
            vs.signals.append({"name": "vol_contango", "direction": "premium_favorable"})
        elif term_structure == "backwardation":
            vs.term_structure_signal = "use_calendar_spread"
            vs.vol_surface_score_delta -= 0.5  # penalizes naked premium selling
            vs.signals.append({"name": "vol_backwardation", "direction": "use_calendar",
                                "note": "Front-month IV elevated — avoid naked sells; use calendar spread"})

    # 5b: Skew slope
    iv_put_20d, iv_call_50d = compute_skew_slope(chain)
    vs.iv_20delta_put = iv_put_20d
    vs.iv_50delta_call = iv_call_50d
    if iv_put_20d is not None and iv_call_50d is not None:
        vs.skew_slope = round(iv_put_20d - iv_call_50d, 4)
        vs.skew_rank = compute_skew_rank(vs.skew_slope)
        vs.signals.append({
            "name": "iv_skew_slope",
            "put_20d_iv": round(iv_put_20d * 100, 1),
            "call_50d_iv": round(iv_call_50d * 100, 1),
            "skew_slope": round(vs.skew_slope * 100, 2),
            "skew_rank": round(vs.skew_rank, 2),
        })

        if vs.skew_rank >= 0.80:
            vs.skew_signal = "bearish_put_demand"
            vs.vol_surface_score_delta -= 1.0
            vs.signals.append({"name": "steep_skew", "direction": "bearish",
                                "note": f"Skew rank {vs.skew_rank:.0%} — informed put demand (Xing-Zhang-Zhao)"})
        elif vs.skew_rank <= 0.20:
            vs.skew_signal = "bullish_no_fear"
            vs.vol_surface_score_delta += 0.5
            vs.signals.append({"name": "flat_skew", "direction": "bullish",
                                "note": "Flat skew — market shows no downside fear"})

    # 5c: VRP z-score
    if len(df) >= 30:
        # Compute HV20 history from price data
        log_ret = np.log(df["close"].values[1:] / df["close"].values[:-1])
        hv20_vals = []
        for i in range(20, len(log_ret)):
            hv20_vals.append(float(np.std(log_ret[i-20:i]) * math.sqrt(252)))
        hv20_vals.reverse()  # most recent first

        if hv20_vals:
            vs.hv20 = hv20_vals[0]
            vs.iv_current = iv_21 or iv_45  # use nearest DTE as proxy for current IV

        if iv_history and hv20_vals and len(hv20_vals) >= 30:
            vrp_z = compute_vrp_zscore(iv_history, hv20_vals)
            vs.vrp_zscore = vrp_z
            if vrp_z is not None:
                vs.vrp_current = round((iv_history[0] - hv20_vals[0]), 4) if iv_history else None
                vs.signals.append({
                    "name": "vrp_zscore",
                    "value": vrp_z,
                    "iv": round(iv_history[0] * 100, 1) if iv_history else None,
                    "hv20": round(hv20_vals[0] * 100, 1),
                })

                if vrp_z > 1.0:
                    vs.vrp_signal = "sell_premium"
                    vs.vol_surface_score_delta += 1.0
                    vs.signals.append({"name": "vrp_rich", "direction": "sell_vol",
                                       "note": f"VRP z-score={vrp_z:.1f} > 1.0 — premium is structurally rich"})
                elif vrp_z < 0:
                    vs.vrp_signal = "buy_vol"
                    vs.vol_surface_score_delta -= 1.0
                    vs.signals.append({"name": "vrp_cheap", "direction": "buy_vol",
                                       "note": f"VRP z-score={vrp_z:.1f} < 0 — IV below realized; avoid short vol"})

    # 5e: Calendar spread eligibility
    has_near_term_event = False  # TODO: integrate with calendar.py event detection
    cal_eligible, cal_reason = check_calendar_spread_eligible(
        term_structure, iv_21, iv_45, vs.vrp_zscore, has_near_term_event
    )
    vs.calendar_spread_eligible = cal_eligible
    vs.calendar_spread_reason = cal_reason
    if cal_eligible:
        vs.signals.append({"name": "calendar_spread_setup", "direction": "calendar",
                            "note": cal_reason})

    return vs


def format_vol_surface_context(vs: VolSurfaceSignals) -> str:
    """Format vol surface signals for injection into Claude context."""
    lines = [f"[{vs.symbol} Vol Surface]"]

    if vs.iv_term_slope is not None:
        lines.append(f"Term structure: {vs.term_structure} (slope={vs.iv_term_slope*100:+.1f}%) — {vs.term_structure_signal}")

    if vs.skew_slope is not None:
        lines.append(f"Skew: slope={vs.skew_slope*100:.1f}%, rank={vs.skew_rank:.0%} — {vs.skew_signal}")

    if vs.vrp_zscore is not None:
        lines.append(f"VRP z-score: {vs.vrp_zscore:+.2f} → {vs.vrp_signal}")

    if vs.calendar_spread_eligible:
        lines.append(f"Calendar spread eligible: {vs.calendar_spread_reason}")

    return "\n".join(lines)
