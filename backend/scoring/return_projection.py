"""
Return projection + stream classifier.

Computes:
  - Bear / Base / Bull scenario option prices at expiry (using IV × DTE expected move)
  - Expected return % per scenario
  - Probability of each scenario (from delta / IV distribution)
  - Stream classification: ALPHA (10x–100x, $0.10–$0.50 entry) vs INCOME (30–50%/wk, near-ATM)
  - Expected value (EV) as a weighted average of scenarios

All math is Black-Scholes approximations — directionally correct without requiring live option prices.
"""

import math
from dataclasses import dataclass, field


@dataclass
class Scenario:
    name: str                   # "bear" | "base" | "bull"
    move_pct: float             # underlying price move % (e.g. +0.08 = +8%)
    option_price_exit: float    # estimated option price at expiry
    return_pct: float           # (exit - entry) / entry × 100
    probability: float          # estimated probability 0–1


@dataclass
class ReturnProjection:
    stream: str                 # "alpha" | "income"
    entry_price: float          # option mid-price at entry
    target_price_10x: float     # option price for 10× return
    target_price_50pct: float   # option price for 50% return (income target)
    scenarios: list[Scenario] = field(default_factory=list)
    expected_value_pct: float = 0.0   # probability-weighted return %
    confidence_pct: float = 0.0       # how confident the system is (maps to conviction)
    stream_rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "stream": self.stream,
            "entry_price": round(self.entry_price, 2),
            "target_price_10x": round(self.target_price_10x, 2),
            "target_price_50pct": round(self.target_price_50pct, 2),
            "expected_value_pct": round(self.expected_value_pct, 1),
            "confidence_pct": round(self.confidence_pct, 1),
            "stream_rationale": self.stream_rationale,
            "scenarios": [
                {
                    "name": s.name,
                    "underlying_move_pct": round(s.move_pct * 100, 1),
                    "option_price_exit": round(s.option_price_exit, 2),
                    "return_pct": round(s.return_pct, 1),
                    "probability": round(s.probability, 2),
                }
                for s in self.scenarios
            ],
        }


def compute_return_projection(
    entry_option_price: float,
    underlying_price: float,
    strike: float,
    dte: int,
    iv: float,           # annualized implied volatility (e.g. 0.35 = 35%)
    direction: str,      # "bullish" | "bearish" | "neutral"
    conviction_score: float,  # 0–100
    iv_percentile: float,     # 0–100
) -> ReturnProjection:
    """
    Estimate return scenarios and classify stream.

    Scenarios use simplified intrinsic + extrinsic value approximation:
      - Option intrinsic value at expiry = max(S_T - K, 0) for calls
      - Extrinsic (time value remaining) ≈ 0 at expiry
      - S_T estimated as S × exp(move × sqrt(dte/365))
    """
    if entry_option_price <= 0:
        entry_option_price = 0.01
    if underlying_price <= 0 or strike <= 0 or dte <= 0 or iv <= 0:
        return _empty_projection(entry_option_price)

    is_call = direction in ("bullish", "neutral")
    t = dte / 365.0
    sigma_sqrt_t = iv * math.sqrt(t)

    # One-standard-deviation move
    one_sd = underlying_price * sigma_sqrt_t
    two_sd = 2.0 * one_sd

    # Expected move at various percentiles (using log-normal approximation)
    def _underlying_at(sigma_mult: float) -> float:
        """Price at entry ± sigma_mult standard deviations."""
        direction_sign = 1 if is_call else -1
        return underlying_price * math.exp(direction_sign * sigma_mult * sigma_sqrt_t - 0.5 * iv**2 * t)

    def _option_value_at_expiry(s_t: float) -> float:
        """Intrinsic value of the option at expiry."""
        if is_call:
            return max(s_t - strike, 0.0)
        else:
            return max(strike - s_t, 0.0)

    # Build three scenarios
    # Bear: unfavorable 1σ move
    s_bear = _underlying_at(-0.8)
    # Base: at-the-money drift (delta-neutral)
    s_base = _underlying_at(0.5)
    # Bull: favorable 1.5σ move
    s_bull = _underlying_at(1.5)

    val_bear = _option_value_at_expiry(s_bear)
    val_base = _option_value_at_expiry(s_base)
    val_bull = _option_value_at_expiry(s_bull)

    # Probabilities: roughly Gaussian over the three buckets
    # (bear 25%, base 45%, bull 30%) skewed by conviction
    conviction_adj = (conviction_score - 50) / 200  # -0.25 to +0.25
    p_bear = max(0.05, 0.25 - conviction_adj)
    p_bull = max(0.05, 0.30 + conviction_adj)
    p_base = max(0.05, 1.0 - p_bear - p_bull)

    scenarios = [
        Scenario("bear", (s_bear - underlying_price) / underlying_price,
                 val_bear, (val_bear - entry_option_price) / entry_option_price * 100, p_bear),
        Scenario("base", (s_base - underlying_price) / underlying_price,
                 val_base, (val_base - entry_option_price) / entry_option_price * 100, p_base),
        Scenario("bull", (s_bull - underlying_price) / underlying_price,
                 val_bull, (val_bull - entry_option_price) / entry_option_price * 100, p_bull),
    ]

    ev_pct = sum(s.return_pct * s.probability for s in scenarios)

    # Stream classification
    # ALPHA: entry price very cheap + high potential move (OTM short-dated, catalyst play)
    # INCOME: near-ATM, moderate IV, consistent weekly target
    moneyness = abs(underlying_price - strike) / underlying_price  # 0 = ATM

    is_alpha = (
        entry_option_price <= 1.00             # cheap option
        and moneyness >= 0.03                  # at least slightly OTM
        and dte <= 21                          # short-dated
        and iv_percentile <= 40               # low IV → cheap to buy
    )
    is_income = (
        not is_alpha
        and 30 <= iv_percentile <= 65         # moderate IV
        and moneyness <= 0.05                 # near-ATM
        and dte <= 14                         # 1–2 weeks
    )

    if is_alpha:
        stream = "alpha"
        rationale = (
            f"Low-cost OTM play: entry ${entry_option_price:.2f}, IV rank {iv_percentile:.0f}th pct. "
            f"Bull case exits at ${val_bull:.2f} ({scenarios[2].return_pct:.0f}%). "
            f"Risk: full debit if OTM at expiry."
        )
    elif is_income:
        stream = "income"
        rationale = (
            f"Near-ATM income trade: entry ${entry_option_price:.2f}, {dte} DTE. "
            f"Base case: +{scenarios[1].return_pct:.0f}% in {dte} days. "
            f"Target: 50% of max profit (${entry_option_price * 0.50:.2f})."
        )
    else:
        stream = "alpha"  # default to alpha for high-conviction setups
        rationale = (
            f"Conviction play: entry ${entry_option_price:.2f}. "
            f"Expected value: {ev_pct:.0f}% across all scenarios."
        )

    target_10x  = entry_option_price * 10.0
    target_50pct = entry_option_price * 1.50

    return ReturnProjection(
        stream=stream,
        entry_price=entry_option_price,
        target_price_10x=target_10x,
        target_price_50pct=target_50pct,
        scenarios=scenarios,
        expected_value_pct=ev_pct,
        confidence_pct=conviction_score,
        stream_rationale=rationale,
    )


def _empty_projection(entry_price: float) -> ReturnProjection:
    return ReturnProjection(
        stream="alpha",
        entry_price=entry_price,
        target_price_10x=entry_price * 10,
        target_price_50pct=entry_price * 1.5,
        scenarios=[],
        expected_value_pct=0.0,
        confidence_pct=50.0,
        stream_rationale="Insufficient data for projection.",
    )
