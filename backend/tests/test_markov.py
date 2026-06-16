"""Markov regime model invariants — Phase G.2."""

import math

import numpy as np
import pytest

from analysis.regime_markov import (
    STATES, fit_transition_matrix, MarkovModel,
)


def test_transition_matrix_is_row_stochastic():
    labels = ["bull_trend", "bull_trend", "chop", "bull_trend", "bear_trend",
              "high_vol", "chop", "bull_trend", "chop", "chop"] * 25
    model = fit_transition_matrix(labels)
    rows = model.transition_matrix.sum(axis=1)
    assert all(abs(r - 1.0) < 1e-9 for r in rows)


def test_stationary_distribution_sums_to_one():
    labels = ["bull_trend"] * 200 + ["chop"] * 100 + ["bear_trend"] * 50
    model = fit_transition_matrix(labels)
    total = sum(model.stationary.values())
    assert abs(total - 1.0) < 1e-6


def test_stationary_values_are_probabilities():
    labels = ["bull_trend"] * 100 + ["chop"] * 100 + ["bear_trend"] * 100
    model = fit_transition_matrix(labels)
    for v in model.stationary.values():
        assert 0.0 <= v <= 1.0


def test_forecast_returns_a_distribution():
    labels = ["bull_trend", "chop", "bear_trend", "high_vol"] * 100
    model = fit_transition_matrix(labels)
    forecast_21 = model.forecast(21)
    assert abs(sum(forecast_21.values()) - 1.0) < 1e-6
    assert set(forecast_21.keys()) == set(STATES)


def test_forecast_at_horizon_zero_collapses_to_current_state():
    labels = ["bull_trend", "chop"] * 100
    model = fit_transition_matrix(labels)
    forecast = model.forecast(0)
    assert forecast[model.last_state] == 1.0
    assert all(v == 0.0 for s, v in forecast.items() if s != model.last_state)


def test_forecast_converges_to_stationary():
    """Long-horizon forecast should approach the stationary distribution."""
    labels = (["bull_trend"] * 50 + ["bear_trend"] * 50 + ["chop"] * 100
              + ["high_vol"] * 20) * 5
    model = fit_transition_matrix(labels)
    far_forecast = model.forecast(1000)
    for state, p in far_forecast.items():
        assert abs(p - model.stationary[state]) < 0.05


def test_too_few_labels_raises():
    with pytest.raises(RuntimeError):
        fit_transition_matrix(["bull_trend"])
