"""Short squeeze confidence scoring."""

from analysis.short_squeeze import SqueezeSetup, _confidence


def test_high_si_setup_scores_above_zero():
    setup = SqueezeSetup(
        symbol="X", si_pct_float=0.25, days_to_cover=8.0,
        price_above_sma20=True, ret_5d=0.05, ret_20d=0.10,
        catalyst_within_5d=False, confidence=0,
    )
    assert _confidence(setup) > 40


def test_with_catalyst_scores_higher():
    base = SqueezeSetup(
        symbol="X", si_pct_float=0.20, days_to_cover=6.0,
        price_above_sma20=True, ret_5d=0.04, ret_20d=0.08,
        catalyst_within_5d=False, confidence=0,
    )
    with_cat = SqueezeSetup(
        symbol="X", si_pct_float=0.20, days_to_cover=6.0,
        price_above_sma20=True, ret_5d=0.04, ret_20d=0.08,
        catalyst_within_5d=True, confidence=0,
    )
    assert _confidence(with_cat) > _confidence(base)


def test_confidence_capped_at_100():
    setup = SqueezeSetup(
        symbol="X", si_pct_float=0.80, days_to_cover=20.0,
        price_above_sma20=True, ret_5d=0.20, ret_20d=0.40,
        catalyst_within_5d=True, confidence=0,
    )
    assert _confidence(setup) <= 100.0
