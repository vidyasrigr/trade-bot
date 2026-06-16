"""insider_flow — routine vs opportunistic classifier + cluster detection."""

from datetime import date, timedelta

from analysis.insider_flow import (
    _classify_routine, _is_open_market_buy, detect_cluster,
)


def _trade(name, d, txn="P-Purchase", shares=1000, price=100):
    return {
        "reportingName": name,
        "transactionDate": d,
        "transactionType": txn,
        "securitiesTransacted": shares,
        "price": price,
    }


def test_open_market_buy_detection():
    assert _is_open_market_buy({"transactionType": "P-Purchase"}) is True
    assert _is_open_market_buy({"transactionType": "P"}) is True
    assert _is_open_market_buy({"transactionType": "S-Sale"}) is False
    assert _is_open_market_buy({"transactionType": "A-Award"}) is False


def test_routine_classifier_marks_recurring_same_month_buys():
    """Same insider buying in March across 3 years = routine."""
    trades = [
        _trade("Alice", "2024-03-10"),
        _trade("Alice", "2023-03-12"),
        _trade("Alice", "2022-03-08"),
    ]
    routine = _classify_routine(trades)
    assert all(routine.values())


def test_classifier_marks_one_off_as_opportunistic():
    trades = [
        _trade("Bob", "2026-04-15"),
        _trade("Bob", "2026-03-20"),
    ]
    routine = _classify_routine(trades)
    # Two trades in the same calendar year — can't be 2+ prior-year matches
    assert not any(routine.values())


def test_cluster_needs_three_opportunistic():
    today = date(2026, 6, 15)
    trades = [
        _trade("X", "2026-06-10"),
        _trade("Y", "2026-06-08"),
        # Only 2 distinct insiders, 2 trades — below threshold
    ]
    assert detect_cluster(trades, today=today) is None


def test_cluster_fires_on_three_distinct_insiders_within_30d():
    today = date(2026, 6, 15)
    trades = [
        _trade("X", "2026-06-12", shares=2000, price=50),
        _trade("Y", "2026-06-10", shares=1500, price=50),
        _trade("Z", "2026-05-30", shares=1000, price=50),
    ]
    cluster = detect_cluster(trades, today=today)
    assert cluster is not None
    assert cluster["n_distinct"] == 3
    assert cluster["n_opportunistic"] == 3
    assert cluster["confidence"] > 60


def test_old_trades_excluded_from_window():
    today = date(2026, 6, 15)
    trades = [
        _trade("X", "2026-01-01"),  # outside 30-day window
        _trade("Y", "2026-02-15"),
        _trade("Z", "2026-03-20"),
    ]
    assert detect_cluster(trades, today=today) is None


def test_sales_dont_count_toward_cluster():
    today = date(2026, 6, 15)
    trades = [
        _trade("X", "2026-06-12", txn="S-Sale"),
        _trade("Y", "2026-06-10", txn="S-Sale"),
        _trade("Z", "2026-06-05", txn="S-Sale"),
    ]
    assert detect_cluster(trades, today=today) is None
