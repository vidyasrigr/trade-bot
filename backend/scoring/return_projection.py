"""
Return projection — IV-implied lognormal probabilities + expected value.

REPLACES (2026-06-13) the previous version that invented scenario probabilities
(p_bear=25%, p_base=45%, p_bull=30%, shifted by LLM conviction). That was the
last place in the live ticket carrying fabricated numbers.

What we do instead:
  - Terminal underlying price S_T is lognormal under the risk-neutral measure:
      S_T = S * exp((-0.5*sigma^2)*T + sigma*sqrt(T)*Z),  Z ~ N(0,1)
  - "bear/base/bull" scenarios are the 16th / 50th / 84th percentile prices
    (one-sigma bands of the IV-implied distribution). NOT directionally tilted.
  - Probabilities ARE the IV-implied probabilities of finishing in each
    one-sigma band — there is no LLM conviction tilt.
  - Expected value of the option at expiry is the integral of intrinsic value
    over the lognormal density (Gauss-Hermite quadrature).
  - Probability of finishing ITM is reported separately.

Stream classification: replaced the prior "alpha = cheap OTM" lottery routing
(Boyer-Vorkink 2014 — systematically EV-negative) with regime-correct
"premium-buying" vs "premium-selling" based on IV rank.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm


# Gauss-Hermite nodes/weights for risk-neutral expected payoff
_GH_NODES, _GH_WEIGHTS = np.polynomial.hermite_e.hermegauss(32)


@dataclass
class Scenario:
    name: str                   # "bear" | "base" | "bull"
    move_pct: float             # underlying price move (e.g. +0.08 = +8%)
    option_price_exit: float    # intrinsic value of the option at expiry
    return_pct: float           # (exit - entry) / entry × 100
    probability: float          # IV-implied probability of this 1-sigma band


@dataclass
class ReturnProjection:
    stream: str                       # "premium_buying" | "premium_selling" | "neutral"
    entry_price: float                # option mid-price at entry
    target_price_50pct: float         # option price for +50% return
    target_price_2x: float            # option price for +100% return
    scenarios: list[Scenario] = field(default_factory=list)
    expected_value_pct: float = 0.0   # IV-implied EV of holding to expiry, %
    prob_itm: float = 0.0             # IV-implied P(finish ITM)
    prob_profit: float = 0.0          # IV-implied P(payoff > entry_premium) for long premium
    confidence_pct: float = 0.0       # carry-through of system conviction
    stream_rationale: str = ""

    def to_dict(self) -> dict:
        # target_price_10x removed 2026-06-15 (Phase F.4) — was an aspirational
        # 4σ move masquerading as a "target". UI now uses target_price_2x.
        return {
            "stream": self.stream,
            "entry_price": round(self.entry_price, 2),
            "target_price_50pct": round(self.target_price_50pct, 2),
            "target_price_2x": round(self.target_price_2x, 2),
            "expected_value_pct": round(self.expected_value_pct, 1),
            "prob_itm": round(self.prob_itm, 3),
            "prob_profit": round(self.prob_profit, 3),
            "confidence_pct": round(self.confidence_pct, 1),
            "stream_rationale": self.stream_rationale,
            "scenarios": [
                {
                    "name": s.name,
                    "underlying_move_pct": round(s.move_pct * 100, 1),
                    "option_price_exit": round(s.option_price_exit, 2),
                    "return_pct": round(s.return_pct, 1),
                    "probability": round(s.probability, 3),
                }
                for s in self.scenarios
            ],
        }


def _terminal_price(s: float, sigma_sqrt_t: float, sigma_sq_t: float, z: float) -> float:
    """S_T under risk-neutral lognormal, zero drift."""
    return s * math.exp(-0.5 * sigma_sq_t + sigma_sqrt_t * z)


def _expected_payoff(s: float, k: float, sigma_sqrt_t: float, sigma_sq_t: float,
                     is_call: bool) -> float:
    """E[max(S_T - K, 0)] under risk-neutral lognormal via Gauss-Hermite (32-pt)."""
    # ∫ payoff(S_T) * φ(z) dz  where φ is N(0,1) density
    # hermegauss returns nodes/weights for the standard-normal-weighted integral
    norm_const = 1.0 / math.sqrt(2 * math.pi)
    total = 0.0
    for z, w in zip(_GH_NODES, _GH_WEIGHTS):
        s_t = _terminal_price(s, sigma_sqrt_t, sigma_sq_t, z)
        payoff = max(s_t - k, 0.0) if is_call else max(k - s_t, 0.0)
        total += w * payoff
    return norm_const * total


_LONG_PREMIUM_STRATEGIES = {
    "long_call", "long_put", "bull_call_spread", "bear_put_spread",
    "calendar_spread", "diagonal_spread", "debit_spread",
    "long_strangle", "long_straddle",
    "pmcc",  # poor man's covered call (long LEAPS leg drives sign)
}

_SHORT_PREMIUM_STRATEGIES = {
    "short_call", "short_put", "naked_put", "covered_call", "cash_secured_put",
    "bull_put_spread", "bear_call_spread", "credit_spread",
    "iron_condor", "iron_butterfly",
    "short_strangle", "short_straddle",
}


def _classify_stream(strategy: str | None, iv_percentile: float) -> str:
    """
    Classify the *trade*, not the underlying.

    Previous rule looked only at IV-rank: a long call on a 70th-pct IV stock was
    labeled "premium_selling" even though we were *buying* premium. That confused
    the briefing, the analytics, and the postmortem.

    Rule of preference:
      1. If the strategy is a known long-premium structure  → premium_buying
      2. If the strategy is a known short-premium structure → premium_selling
      3. Else (unknown strategy / no strategy) fall back to IV-rank heuristic
         used previously: ≥60 → premium_selling, ≤35 → premium_buying, else neutral.
    """
    if strategy:
        s = strategy.lower().strip()
        if s in _LONG_PREMIUM_STRATEGIES:
            return "premium_buying"
        if s in _SHORT_PREMIUM_STRATEGIES:
            return "premium_selling"
    if iv_percentile >= 60:
        return "premium_selling"
    if iv_percentile <= 35:
        return "premium_buying"
    return "neutral"


def compute_return_projection(
    entry_option_price: float,
    underlying_price: float,
    strike: float,
    dte: int,
    iv: float,                # annualized implied volatility (0.35 = 35%)
    direction: str,           # "bullish" | "bearish" | "neutral"
    conviction_score: float,  # 0–100 — used only as confidence_pct passthrough
    iv_percentile: float,     # 0–100 — used for stream classification fallback
    *,
    strategy: str | None = None,  # NEW: 'long_call', 'iron_condor', etc.
) -> ReturnProjection:
    """
    IV-implied projection. The conviction_score is NOT used to bend probabilities —
    it's just carried through as confidence_pct for the UI. The market's
    distribution (sigma = IV) is what we use.
    """
    if entry_option_price <= 0:
        entry_option_price = 0.01
    if underlying_price <= 0 or strike <= 0 or dte <= 0 or iv <= 0:
        return _empty_projection(entry_option_price)

    is_call = direction != "bearish"
    t = dte / 365.0
    sigma_sqrt_t = iv * math.sqrt(t)
    sigma_sq_t = iv * iv * t

    # Risk-neutral median (50th pct) and ±1σ percentiles of the lognormal
    s_bear = _terminal_price(underlying_price, sigma_sqrt_t, sigma_sq_t, z=-1.0)
    s_base = _terminal_price(underlying_price, sigma_sqrt_t, sigma_sq_t, z=0.0)
    s_bull = _terminal_price(underlying_price, sigma_sqrt_t, sigma_sq_t, z=+1.0)

    # Probabilities = IV-implied probabilities of finishing in each 1σ band
    # using the standard-normal CDF on Z:
    #   P(Z < -1) ≈ 0.1587, P(-1 ≤ Z < 1) ≈ 0.6827, P(Z ≥ 1) ≈ 0.1587
    p_bear = float(norm.cdf(-1.0))
    p_base = float(norm.cdf(1.0) - norm.cdf(-1.0))
    p_bull = float(1.0 - norm.cdf(1.0))

    def _payoff(s_t: float) -> float:
        return max(s_t - strike, 0.0) if is_call else max(strike - s_t, 0.0)

    val_bear, val_base, val_bull = _payoff(s_bear), _payoff(s_base), _payoff(s_bull)

    scenarios = [
        Scenario("bear", (s_bear - underlying_price) / underlying_price,
                 val_bear, (val_bear - entry_option_price) / entry_option_price * 100, p_bear),
        Scenario("base", (s_base - underlying_price) / underlying_price,
                 val_base, (val_base - entry_option_price) / entry_option_price * 100, p_base),
        Scenario("bull", (s_bull - underlying_price) / underlying_price,
                 val_bull, (val_bull - entry_option_price) / entry_option_price * 100, p_bull),
    ]

    # IV-implied expected payoff (Gauss-Hermite over the full lognormal)
    e_payoff = _expected_payoff(underlying_price, strike, sigma_sqrt_t, sigma_sq_t, is_call)
    ev_pct = (e_payoff - entry_option_price) / entry_option_price * 100

    # IV-implied P(ITM) and P(profit at expiry, ignoring time value remaining).
    # ln(S_T / S) ~ N(-0.5σ²t, σ²t). For a call to be ITM: S_T >= K
    log_kS = math.log(strike / underlying_price)
    mean_log = -0.5 * sigma_sq_t
    z_itm = (log_kS - mean_log) / sigma_sqrt_t
    if is_call:
        prob_itm = float(1.0 - norm.cdf(z_itm))
    else:
        prob_itm = float(norm.cdf(z_itm))

    # P(intrinsic >= premium paid) — the actual break-even at expiry
    target_underlying = strike + entry_option_price if is_call else strike - entry_option_price
    if target_underlying <= 0:
        prob_profit = 1.0
    else:
        log_target = math.log(target_underlying / underlying_price)
        z_target = (log_target - mean_log) / sigma_sqrt_t
        prob_profit = float(1.0 - norm.cdf(z_target)) if is_call else float(norm.cdf(z_target))

    # Stream classification — STRATEGY-FIRST (Phase H.7).
    # Previously this looked at IV-rank only, mis-labeling a long call on a 70th-pct
    # IV stock as "premium_selling". Now: the strategy itself decides the stream,
    # IV-rank is only a fallback when the strategy is unknown.
    moneyness = abs(underlying_price - strike) / underlying_price
    stream = _classify_stream(strategy, iv_percentile)
    if stream == "premium_selling":
        rationale = (
            f"{strategy or 'short premium'} — selling premium. IV rank {iv_percentile:.0f}th. "
            f"Entry mid ${entry_option_price:.2f}. IV-implied EV at expiry: {ev_pct:+.0f}%. "
            f"P(profit) = {prob_profit:.0%}."
        )
    elif stream == "premium_buying":
        rationale = (
            f"{strategy or 'long premium'} — buying premium. IV rank {iv_percentile:.0f}th. "
            f"Entry mid ${entry_option_price:.2f}. IV-implied EV at expiry: "
            f"{ev_pct:+.0f}%. P(ITM) = {prob_itm:.0%}, P(profit) = {prob_profit:.0%}."
        )
    else:
        rationale = (
            f"{strategy or 'unspecified'} — neutral stream. IV rank {iv_percentile:.0f}th. "
            f"Entry mid ${entry_option_price:.2f}, moneyness {moneyness:.1%}. "
            f"IV-implied EV: {ev_pct:+.0f}%, P(profit) {prob_profit:.0%}."
        )

    return ReturnProjection(
        stream=stream,
        entry_price=entry_option_price,
        target_price_50pct=entry_option_price * 1.50,
        target_price_2x=entry_option_price * 2.0,
        scenarios=scenarios,
        expected_value_pct=ev_pct,
        prob_itm=prob_itm,
        prob_profit=prob_profit,
        confidence_pct=conviction_score,
        stream_rationale=rationale,
    )


def _empty_projection(entry_price: float) -> ReturnProjection:
    return ReturnProjection(
        stream="neutral",
        entry_price=entry_price,
        target_price_50pct=entry_price * 1.5,
        target_price_2x=entry_price * 2.0,
        scenarios=[],
        expected_value_pct=0.0,
        prob_itm=0.0,
        prob_profit=0.0,
        confidence_pct=50.0,
        stream_rationale="Insufficient data for projection.",
    )
