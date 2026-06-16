"""
IV-implied lognormal projection.
The fix that removed invented 25/45/30 probabilities — must stay honest.
"""

import math

from scoring.return_projection import (
    _classify_stream, compute_return_projection,
)


def test_scenario_probabilities_sum_to_one():
    proj = compute_return_projection(
        entry_option_price=1.20, underlying_price=100, strike=105,
        dte=30, iv=0.40, direction="bullish",
        conviction_score=65, iv_percentile=40,
    )
    total = sum(s.probability for s in proj.scenarios)
    assert abs(total - 1.0) < 0.01


def test_conviction_does_not_bend_probabilities():
    """conviction is UI passthrough only — never tilts the IV-implied distribution."""
    p1 = compute_return_projection(
        entry_option_price=1.20, underlying_price=100, strike=105,
        dte=30, iv=0.40, direction="bullish",
        conviction_score=20, iv_percentile=40,
    )
    p2 = compute_return_projection(
        entry_option_price=1.20, underlying_price=100, strike=105,
        dte=30, iv=0.40, direction="bullish",
        conviction_score=95, iv_percentile=40,
    )
    for s1, s2 in zip(p1.scenarios, p2.scenarios):
        assert abs(s1.probability - s2.probability) < 1e-9


def test_conviction_does_not_bend_ev():
    p1 = compute_return_projection(
        entry_option_price=1.20, underlying_price=100, strike=105,
        dte=30, iv=0.40, direction="bullish",
        conviction_score=20, iv_percentile=40,
    )
    p2 = compute_return_projection(
        entry_option_price=1.20, underlying_price=100, strike=105,
        dte=30, iv=0.40, direction="bullish",
        conviction_score=95, iv_percentile=40,
    )
    assert abs(p1.expected_value_pct - p2.expected_value_pct) < 0.01


def test_otm_call_has_lower_p_itm_than_atm():
    spot, dte, iv = 100, 30, 0.30
    atm = compute_return_projection(1.0, spot, 100, dte, iv, "bullish", 70, 50)
    otm = compute_return_projection(1.0, spot, 110, dte, iv, "bullish", 70, 50)
    assert atm.prob_itm > otm.prob_itm


def test_higher_iv_widens_scenario_spread():
    low_iv = compute_return_projection(1.0, 100, 100, 30, 0.20, "bullish", 70, 50)
    high_iv = compute_return_projection(1.0, 100, 100, 30, 0.80, "bullish", 70, 50)
    # The bull scenario underlying move must be larger when IV is higher
    assert abs(high_iv.scenarios[2].move_pct) > abs(low_iv.scenarios[2].move_pct)


def test_classify_stream_long_premium_overrides_iv():
    """Long call on a high-IV stock → still premium_buying (strategy-first)."""
    assert _classify_stream("long_call", iv_percentile=85) == "premium_buying"


def test_classify_stream_short_premium_overrides_iv():
    """Iron condor on a low-IV stock → still premium_selling (strategy-first)."""
    assert _classify_stream("iron_condor", iv_percentile=20) == "premium_selling"


def test_classify_stream_unknown_strategy_falls_back_to_iv():
    assert _classify_stream(None, iv_percentile=70) == "premium_selling"
    assert _classify_stream(None, iv_percentile=20) == "premium_buying"
    assert _classify_stream(None, iv_percentile=50) == "neutral"


def test_legacy_target_price_10x_gone():
    proj = compute_return_projection(1.0, 100, 105, 30, 0.30, "bullish", 70, 40)
    d = proj.to_dict()
    assert "target_price_10x" not in d, "Phase F.4 removed this; wire should not carry it."
    assert "target_price_2x" in d
