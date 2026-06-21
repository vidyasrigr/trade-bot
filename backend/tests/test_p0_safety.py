"""
P0 pre-paper safety regression suite (0620.3 Phase 4.6).

Locks in the safety invariants so they can't silently regress before paper:
  - Kelly lift disabled + capped (4.3)
  - validation-ledger gates conviction; legacy live_full label is NOT enough (4.1)
  - a blocked signal can't count toward the confirmation gate (4.2)
  - PaperFillModel rejects unfillable tickets / fills worse than the touch (4.4)
  - paper-open requires a recommendation_id (4.4 / P0)
"""

from __future__ import annotations

import asyncio

import pytest

from core.config import settings
from scoring.weighted import _choose_kelly_fraction, _kelly_size, compute_final_score
from scoring.signal_registry import contributes_in_mode
from backtest.fills import PaperFillModel
from analysis.engine import CategoryScore


# --- 4.3 Kelly -----------------------------------------------------------------

def test_kelly_lift_disabled():
    base = settings.KELLY_FRACTION
    for n in (3, 5, 6, 10):
        for tail in (False, True):
            assert _choose_kelly_fraction(n, tail) == base


def test_kelly_capped():
    assert settings.KELLY_FRACTION <= settings.KELLY_FRACTION_MAX
    for n in (3, 6, 12):
        assert _choose_kelly_fraction(n, True) <= settings.KELLY_FRACTION_MAX


# --- 4.1 validation ledger gates conviction ------------------------------------

def test_ledger_blocks_unvalidated_live_full_in_paper():
    # macro is live_full by legacy label, but the ledger is empty -> blocked in paper.
    assert contributes_in_mode("macro", "paper") is False
    # backtest bypasses the ledger (research evaluates raw).
    assert contributes_in_mode("macro", "backtest") is True


def test_ledger_allows_only_validated(monkeypatch):
    import scoring.validation_ledger as vl
    monkeypatch.setattr(vl, "validated_signals", lambda: frozenset({"macro"}))
    # with macro in the ledger AND live_full registry status, paper now allows it
    assert contributes_in_mode("macro", "paper") is True
    # a non-validated live_full signal stays blocked
    assert contributes_in_mode("trend", "paper") is False


# --- 4.2 blocked signal cannot satisfy confirmation ----------------------------

def _all_firing_scores():
    return {name: CategoryScore(name=name, weight=w, raw_score=9.0,
                                weighted_score=9.0 * w / 10, direction="bullish", signals=[{"x": 1}])
            for name, w in __import__("scoring.weighted", fromlist=["BASE_WEIGHTS"]).BASE_WEIGHTS.items()}


def test_blocked_signals_excluded_from_confirmation():
    scores = _all_firing_scores()
    saved = getattr(settings, "OPERATING_MODE", "paper")
    try:
        # backtest mode: everything contributes -> confirmation met (many groups fire)
        settings.OPERATING_MODE = "backtest"
        bt = asyncio.run(compute_final_score("TEST", scores, "bull_trend"))
        assert bt.independent_signals_count >= 3 and bt.confirmation_met
        # paper mode: empty ledger blocks every signal -> nothing counts -> fails
        settings.OPERATING_MODE = "paper"
        pp = asyncio.run(compute_final_score("TEST", scores, "bull_trend"))
        assert pp.independent_signals_count == 0
        assert not pp.confirmation_met
    finally:
        settings.OPERATING_MODE = saved


# --- 4.4 PaperFillModel realism -----------------------------------------------

def test_paperfill_rejects_no_quote():
    f = PaperFillModel().fill_ticket([{"bid": 0, "ask": 0, "qty": 1, "open_interest": 500}])
    assert not f.filled and f.reason == "no_quote"


def test_paperfill_rejects_wide_spread():
    f = PaperFillModel().fill_ticket([{"bid": 1.0, "ask": 2.0, "qty": 1, "open_interest": 500}])
    assert not f.filled and f.reason == "wide_spread"


def test_paperfill_rejects_low_oi():
    f = PaperFillModel().fill_ticket([{"bid": 1.00, "ask": 1.02, "qty": 1, "open_interest": 5}])
    assert not f.filled and f.reason == "low_oi"


def test_paperfill_fills_worse_than_touch():
    # buy-to-open should fill ABOVE the ask (pays slippage), not at mid
    f = PaperFillModel().fill_ticket([{"bid": 1.00, "ask": 1.02, "qty": 1, "open_interest": 500}])
    assert f.filled
    assert f.net_price > 1.02


def test_paperfill_any_leg_fail_rejects_whole_ticket():
    f = PaperFillModel().fill_ticket([
        {"bid": 1.00, "ask": 1.02, "qty": 1, "open_interest": 500},   # ok
        {"bid": 0, "ask": 0, "qty": -1, "open_interest": 500},        # no quote
    ])
    assert not f.filled


# --- 4.4 paper-open requires recommendation_id ---------------------------------

def test_open_trade_requires_recommendation_id():
    from api.routes import OpenTradeRequest
    from pydantic import ValidationError
    base = dict(symbol="AAPL", strategy="long_call", direction="bullish", expiry="2026-09-18",
                strike=200.0, option_type="C", contracts=1, entry_price=2.5,
                max_loss=250, max_profit=1000)
    with pytest.raises(ValidationError):
        OpenTradeRequest(**base)              # missing recommendation_id
    ok = OpenTradeRequest(**base, recommendation_id=123)
    assert ok.recommendation_id == 123
