"""Postmortem R-multiple denominator — H1 fix verification."""

from agents.postmortem import _compute_r_multiple


def test_naked_long_call_with_max_loss():
    trade = {"strategy": "long_call", "entry_price": 1.00,
              "contracts": 1, "max_loss": 100, "realized_pnl": 50}
    assert abs(_compute_r_multiple(trade) - 0.5) < 1e-9


def test_naked_long_call_falls_back_to_entry_basis():
    """Without max_loss, $1 entry × 1 contract = $100 risk; pnl=$50 -> 0.5R."""
    trade = {"strategy": "long_call", "entry_price": 1.00,
              "contracts": 1, "max_loss": None, "realized_pnl": 50}
    assert abs(_compute_r_multiple(trade) - 0.5) < 1e-9


def test_credit_spread_requires_max_loss():
    trade = {"strategy": "bull_put_spread", "entry_price": -1.50,
              "contracts": 1, "max_loss": 300, "realized_pnl": 150}
    assert abs(_compute_r_multiple(trade) - 0.5) < 1e-9


def test_credit_spread_no_max_loss_returns_zero():
    """Refuses to guess — better than fabricating a number."""
    trade = {"strategy": "bull_put_spread", "entry_price": -1.50,
              "contracts": 1, "max_loss": 0, "realized_pnl": 150}
    assert _compute_r_multiple(trade) == 0.0


def test_pre_h1_bug_does_not_recur():
    """The classic phantom: $1 entry calls with $50 pnl reported as 50R."""
    trade = {"strategy": "long_call", "entry_price": 1.00,
              "contracts": 1, "max_loss": None, "realized_pnl": 50}
    r = _compute_r_multiple(trade)
    assert r != 50.0  # the bug


def test_multiple_contracts_scale_risk():
    trade_1 = {"strategy": "long_call", "entry_price": 1.00,
                "contracts": 1, "max_loss": None, "realized_pnl": 100}
    trade_5 = {"strategy": "long_call", "entry_price": 1.00,
                "contracts": 5, "max_loss": None, "realized_pnl": 100}
    r1 = _compute_r_multiple(trade_1)
    r5 = _compute_r_multiple(trade_5)
    assert r1 == 5 * r5  # same pnl, 5x contracts = 5x risk = 1/5 R
