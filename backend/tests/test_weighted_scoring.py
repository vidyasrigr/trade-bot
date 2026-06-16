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


def test_kelly_tier_3_groups_default():
    assert _choose_kelly_fraction(3, False) == 0.5


def test_kelly_tier_4_groups_with_tail_still_default():
    assert _choose_kelly_fraction(4, True) == 0.5


def test_kelly_tier_5_groups_bumped_to_075():
    assert _choose_kelly_fraction(5, False) == 0.75
    assert _choose_kelly_fraction(5, True) == 0.75


def test_kelly_tier_6plus_tail_aligned_full_kelly():
    assert _choose_kelly_fraction(6, True) == 1.0
    assert _choose_kelly_fraction(10, True) == 1.0


def test_kelly_tier_6_no_tail_capped_at_075():
    assert _choose_kelly_fraction(6, False) == 0.75


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


def test_kelly_size_full_kelly_returns_higher_pct_than_half():
    """Sanity — 6 stacked signals + tail should size BIGGER than 3 signals."""
    pct_half, _, _ = _kelly_size(
        conviction_score=80, portfolio_value=100_000,
        confirmation_met=True, independent_signals_count=3,
    )
    pct_full, _, _ = _kelly_size(
        conviction_score=80, portfolio_value=100_000,
        confirmation_met=True, independent_signals_count=6,
        tail_signal_aligned=True,
    )
    assert pct_full > pct_half


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
