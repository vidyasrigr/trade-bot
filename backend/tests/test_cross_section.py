"""Cross-sectional ranking math — the substrate Phase C through I rest on."""

import math

import pytest

from scoring.cross_section import Rank, rank_values


def test_empty_returns_empty():
    assert rank_values({}) == {}


def test_single_value_returns_midpoint():
    out = rank_values({"X": 5.0})
    assert out["X"].percentile == 0.5
    assert out["X"].decile == 4


def test_ranks_are_in_unit_interval():
    out = rank_values({f"S{i}": float(i) for i in range(100)})
    for r in out.values():
        assert 0.0 <= r.percentile <= 1.0


def test_deciles_are_0_to_9():
    out = rank_values({f"S{i}": float(i) for i in range(100)})
    deciles = {r.decile for r in out.values()}
    assert deciles <= set(range(10))
    assert 0 in deciles and 9 in deciles


def test_highest_value_gets_highest_percentile():
    out = rank_values({"low": 1.0, "mid": 50.0, "high": 100.0})
    assert out["low"].percentile < out["mid"].percentile < out["high"].percentile
    assert out["high"].percentile == 1.0
    assert out["low"].percentile == 0.0


def test_nan_and_inf_dropped():
    out = rank_values({"a": 1.0, "b": float("nan"), "c": float("inf"), "d": 2.0})
    assert set(out.keys()) == {"a", "d"}


def test_z_score_mean_is_zero():
    out = rank_values({f"S{i}": float(i) for i in range(50)})
    zs = [r.z_score for r in out.values()]
    assert abs(sum(zs) / len(zs)) < 1e-9


def test_constant_values_z_zero():
    out = rank_values({f"S{i}": 5.0 for i in range(10)})
    for r in out.values():
        assert r.z_score == 0.0
