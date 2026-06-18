"""
Synthetic 2020-COVID stress test for short-vol signals (P0 Stage 3.4).

Our MarketData history (Starter, 5y) never saw a real vol crisis, so a short
strangle's worst case is untested. This replays a synthetic Feb-Mar 2020 path —
SPY -34% over ~33 trading days while IV ramps 12% -> 82% — and prices a 45-DTE
16-delta short strangle through it via Black-Scholes (backtest/iv_inversion).

Pass criteria (runbook): max drawdown under stress < 40% of posted margin AND no
margin-call event (unrealized loss never exceeds posted collateral). A naked
short strangle is EXPECTED to fail this — which is the point: it must not advance
sandbox -> paper without defined-risk wings or a regime kill-switch.

Self-contained: no MarketData credits, no external data.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import math

from scipy.stats import norm

from backtest.iv_inversion import bs_price
from backtest.strategies.vrp_harvest import VrpConfig


def _delta_strikes(spot: float, iv: float, t_years: float, target_delta: float) -> tuple[float, float]:
    """
    (put_strike, call_strike) at +/- target_delta, consistent with the ENTRY IV.
    The vrp_harvest _strangle_strikes formula is calibrated for ~30% vol; using it
    at a calm 12% entry IV places strikes ~4 sigma OTM (worthless, credit ~0). This
    uses the lognormal 1-sigma move scaled by the delta's z-score instead.
    """
    z = norm.ppf(1.0 - target_delta)        # 16-delta -> ~0.99 sigma
    sigma_t = iv * math.sqrt(t_years)
    return (round(spot * math.exp(-z * sigma_t), 2),
            round(spot * math.exp(+z * sigma_t), 2))


def synthetic_covid_path(start_spot: float = 100.0, days: int = 33,
                         drop: float = 0.34, vix_start: float = 0.12,
                         vix_peak: float = 0.82) -> tuple[list[float], list[float]]:
    """SPY price path (linear -drop over `days`) and IV ramp (vix_start->vix_peak)."""
    spots, ivs = [], []
    for d in range(days + 1):
        f = d / days
        spots.append(start_spot * (1.0 - drop * f))
        ivs.append(vix_start + (vix_peak - vix_start) * f)
    return spots, ivs


@dataclass
class StressResult:
    credit_per_contract: float
    max_loss_per_contract: float
    loss_to_credit_multiple: float
    posted_margin_per_contract: float
    max_drawdown_vs_margin: float
    margin_call: bool
    stress_test_passed: bool
    detail: str


def stress_test_short_strangle(config: VrpConfig | None = None, *, dte: int = 45,
                               r: float = 0.04, naked_margin_pct: float = 0.20) -> StressResult:
    config = config or VrpConfig()
    spots, ivs = synthetic_covid_path()
    spot0, iv0 = spots[0], ivs[0]
    put_k, call_k = _delta_strikes(spot0, iv0, dte / 365.0, config.target_short_delta)

    def strangle_value(spot: float, iv: float, t_years: float) -> float:
        return (bs_price(spot, put_k, t_years, r, iv, is_call=False)
                + bs_price(spot, call_k, t_years, r, iv, is_call=True))

    credit = strangle_value(spot0, iv0, dte / 365.0)           # received up front
    # Reg-T-ish naked margin on the short put side (the side a crash hits).
    posted_margin = naked_margin_pct * spot0                    # per share
    worst_loss = 0.0
    margin_call = False
    for d, (spot, iv) in enumerate(zip(spots, ivs)):
        t = max(1e-6, (dte - d) / 365.0)
        cur = strangle_value(spot, iv, t)
        unrealized_loss = max(0.0, cur - credit)               # short: lose when value rises
        worst_loss = max(worst_loss, unrealized_loss)
        if unrealized_loss > posted_margin:
            margin_call = True

    mult = (worst_loss / credit) if credit > 0 else float("inf")
    dd_vs_margin = (worst_loss / posted_margin) if posted_margin > 0 else float("inf")
    passed = (dd_vs_margin < 0.40) and not margin_call
    detail = (f"SPY {spots[0]:.0f}->{spots[-1]:.0f} (-{(1-spots[-1]/spots[0]):.0%}), "
              f"IV {ivs[0]:.0%}->{ivs[-1]:.0%}; strangle {put_k:.0f}P/{call_k:.0f}C; "
              f"credit {credit:.2f}, worst loss {worst_loss:.2f} ({mult:.1f}x credit)")
    return StressResult(
        credit_per_contract=round(credit * 100, 2),
        max_loss_per_contract=round(worst_loss * 100, 2),
        loss_to_credit_multiple=round(mult, 2),
        posted_margin_per_contract=round(posted_margin * 100, 2),
        max_drawdown_vs_margin=round(dd_vs_margin, 4),
        margin_call=margin_call,
        stress_test_passed=passed,
        detail=detail,
    )


def stress_summary() -> dict:
    res = stress_test_short_strangle()
    return asdict(res)
