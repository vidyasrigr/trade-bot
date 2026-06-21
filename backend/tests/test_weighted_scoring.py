"""
Conviction multiplier + Kelly tiers + confirmation gate.
The phase-I.1 tail-stacking logic — if these break, sizing breaks.
"""

import pytest

from scoring.weighted import (
    BASE_WEIGHTS, _choose_kelly_fraction, _detect_tail_alignment, _kelly_size,
)


def test_base_weights_sum_to_100():
    active = sum(v for v in BASE_WEIGHTS.values() if v > 0)
    assert active == 100, f"BASE_WEIGHTS active sum {active}, expected 100"


# 0620.3 Phase 4.3: the conviction-stack Kelly LIFT is DISABLED until paper calibration.
# The fraction now stays at base (tenth-Kelly) regardless of stacking, hard-capped at 0.25.

def test_kelly_lift_disabled_stays_at_base():
    from core.config import settings
    base = settings.KELLY_FRACTION
    assert base == 0.10
    for n in (3, 4, 5, 6, 10):
        for tail in (False, True):
            assert _choose_kelly_fraction(n, tail) == base, (
                f"Kelly lift must be disabled: n={n} tail={tail} -> expected {base}")


def test_kelly_fraction_never_exceeds_cap():
    from core.config import settings
    for n in (3, 5, 8, 12):
        assert _choose_kelly_fraction(n, True) <= settings.KELLY_FRACTION_MAX


def test_kelly_size_zero_when_confirmation_fails():
    pct, contracts, kelly = _kelly_size(
        conviction_score=85, portfolio_value=100_000,
        confirmation_met=False, independent_signals_count=5,
    )
    assert pct == 0.0
    assert contracts == 0


def test_kelly_size_zero_when_conviction_below_60():
    pct, contracts, kelly = _kelly_size(
        conviction_score=55, portfolio_value=100_000,
        confirmation_met=True, independent_signals_count=5,
    )
    assert pct == 0.0
    assert contracts == 0


def test_kelly_size_capped_at_max():
    """Full Kelly at conviction 100 must not exceed MAX_POSITION_SIZE_PCT."""
    from core.config import settings
    pct, _, _ = _kelly_size(
        conviction_score=100, portfolio_value=1_000_000,
        confirmation_met=True, independent_signals_count=8,
        tail_signal_aligned=True,
    )
    assert pct <= settings.MAX_POSITION_SIZE_PCT


def test_kelly_size_lift_disabled_stacking_does_not_increase_size():
    """0620.3 Phase 4.3: with the lift disabled, 6 stacked + tail sizes the SAME as 3."""
    pct_3, _, _ = _kelly_size(
        conviction_score=80, portfolio_value=100_000,
        confirmation_met=True, independent_signals_count=3,
    )
    pct_6, _, _ = _kelly_size(
        conviction_score=80, portfolio_value=100_000,
        confirmation_met=True, independent_signals_count=6,
        tail_signal_aligned=True,
    )
    assert pct_6 == pct_3


class _FakeCat:
    """Minimal stand-in for CategoryScore, only exposes .signals like the real one."""
    def __init__(self, signals):
        self.signals = signals


def test_tail_alignment_detects_vrp_z():
    cats = {
        "iv_analysis": _FakeCat([{"name": "vrp_z", "value": 1.5}])
    }
    assert _detect_tail_alignment(cats) is True


def test_tail_alignment_detects_whale_sweep():
    cats = {"sentiment": _FakeCat([{"name": "unusual_call_volume"}])}
    assert _detect_tail_alignment(cats) is True


def test_tail_alignment_false_when_no_tail_signal():
    cats = {
        "iv_analysis": _FakeCat([{"name": "atm_iv", "value": 25}]),
        "sentiment": _FakeCat([{"name": "neutral"}]),
    }
    assert _detect_tail_alignment(cats) is False
