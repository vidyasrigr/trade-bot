"""
Signal registry invariants — these are the rules that prevent silent
contamination of the trader prompt. If any of these break, the audit's
critical-findings check will start failing in production.
"""

from collections import Counter

from scoring.signal_registry import REGISTRY, by_name, by_category


def test_no_duplicate_names():
    names = [s.name for s in REGISTRY]
    dupes = [n for n, c in Counter(names).items() if c > 1]
    assert not dupes, f"Duplicate signal names: {dupes}"


def test_sandbox_signals_dont_influence_conviction():
    """CRITICAL invariant — sandbox = observe only, no scoring path."""
    leaks = [s.name for s in REGISTRY
             if s.promotion_status == "sandbox" and s.influences_conviction]
    assert not leaks, f"Sandbox signals leaking into conviction: {leaks}"


def test_feature_only_signals_dont_influence_conviction():
    """CRITICAL — feature_only is for LLM context, NEVER scoring."""
    leaks = [s.name for s in REGISTRY
             if s.category == "feature_only" and s.influences_conviction]
    assert not leaks, f"feature_only signals leaking into conviction: {leaks}"


def test_every_signal_has_data_sources_declared():
    missing = [s.name for s in REGISTRY if not s.data_sources]
    assert not missing, f"Signals without declared data sources: {missing}"


def test_every_promoted_signal_has_research_anchor():
    """`live_full` claims need a peer-reviewed citation — no exceptions."""
    weak = [s.name for s in REGISTRY
            if s.promotion_status == "live_full" and not s.research_anchor]
    # Engine categories are an exception — they're aggregators, not single signals
    weak = [n for n in weak if not n in {
        "support_resistance", "candles", "chart_patterns", "options_chain",
        "greeks", "trade_structure", "liquidity", "risk", "calendar",
        "fundamental", "macro", "trend", "volatility_regime", "earnings_adj_iv",
    }]
    assert not weak, f"live_full signals without citations: {weak}"


def test_category_distribution_makes_sense():
    by_cat = Counter(s.category for s in REGISTRY)
    # Must have at least one of each major category
    for cat in ("engine", "cross_section", "compound", "feature_only", "strategy"):
        assert by_cat.get(cat, 0) > 0, f"No signals in category={cat}"


def test_promotion_status_is_valid():
    valid_states = {"proposed", "paper", "live_small", "live_full",
                     "demoted", "sandbox", "feature_only"}
    invalid = [(s.name, s.promotion_status) for s in REGISTRY
               if s.promotion_status not in valid_states]
    assert not invalid, f"Invalid promotion statuses: {invalid}"


def test_output_destination_is_known():
    valid_dests = {"category_score", "signal_ranks", "compound_signal_events",
                    "factor_ic_scores", "feature_store", "briefing_only",
                    "lead_lag_edges", "backtest_runs"}
    invalid = [(s.name, s.output_destination) for s in REGISTRY
               if s.output_destination not in valid_dests]
    assert not invalid, f"Invalid output destinations: {invalid}"


def test_by_name_lookup_works():
    bn = by_name()
    assert len(bn) == len(REGISTRY)
    assert "vrp_z" in bn
    assert bn["vrp_z"].category == "cross_section"


def test_by_category_filter():
    engine = by_category("engine")
    assert all(s.category == "engine" for s in engine)
    assert len(engine) == 15
