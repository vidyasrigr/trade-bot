"""
Research signal registry (0620.2 Phase 2) — the GPT-18 research signals, ISOLATED from
the production scoring.signal_registry (which is untouched). Maps research signal name ->
(generator, data_class, caution). Consumed by the Phase 3 regime sweep.

data_class: EQUITY (OHLCV ready) | FMP_EARNINGS (earnings banked) | FMP_STATEMENT
(needs balance/cash-flow; FUNDAMENTALS_PENDING until banked) | OPTIONS (CACHE_LIMITED).
De-dup: rvol + iv_term_slope already NO_EDGE in 0619.3 -> excluded.
"""

from __future__ import annotations

from research.signals import gpt18_equity as eq
from research.signals import gpt18_fmp as fm
from backtest.strategies.options_xs import generate_rv_minus_iv_trades

# name -> (generator, data_class, caution)
RESEARCH_SIGNALS = {
    # --- equity / OHLCV (ready) ---
    "residual_momentum": (eq.make_generator("residual_momentum"), "EQUITY", "PIT rolling beta"),
    "high_52w_proximity": (eq.make_generator("high_52w_proximity"), "EQUITY", "George-Hwang"),
    "time_series_momentum": (eq.make_generator("time_series_momentum"), "EQUITY", "inverse-vol scaled"),
    "short_term_reversal": (eq.make_generator("short_term_reversal"), "EQUITY", "min-price filter"),
    "long_term_reversal": (eq.make_generator("long_term_reversal"), "EQUITY", "solvency filter"),
    "idiosyncratic_vol": (eq.make_generator("idiosyncratic_vol"), "EQUITY", "PIT residual vol"),
    "max_lottery_avoid": (eq.make_generator("max_lottery_avoid"), "EQUITY", "Bali MAX"),
    "vol_contraction_breakout": (eq.make_generator("vol_contraction_breakout"), "EQUITY", "2-cond + volume"),
    "betting_against_beta": (eq.make_generator("betting_against_beta"), "EQUITY", "Frazzini-Pedersen PIT beta"),
    "volume_confirmed_momentum": (eq.make_generator("volume_confirmed_momentum"), "EQUITY", "volume-confirmed"),
    # --- FMP earnings (testable now) ---
    "revenue_surprise_drift": (fm.generate_revenue_surprise_drift_trades, "FMP_EARNINGS", "available_at<=t"),
    "earnings_announcement_premium": (fm.generate_earnings_announcement_premium_trades, "FMP_EARNINGS", "calendar-known"),
    # --- FMP statement (FUNDAMENTALS_PENDING until balance/cash-flow bank) ---
    "accruals": (fm.generate_accruals_trades, "FMP_STATEMENT", "needs income+cashflow"),
    "piotroski_fscore": (fm.generate_piotroski_fscore_trades, "FMP_STATEMENT", "needs all 3 statements"),
    "net_payout_yield": (fm.generate_net_payout_yield_trades, "FMP_STATEMENT", "needs cashflow"),
    "net_operating_assets": (fm.generate_net_operating_assets_trades, "FMP_STATEMENT", "needs balance"),
    "distress_risk_avoid": (fm.generate_distress_risk_avoid_trades, "FMP_STATEMENT", "Altman-Z; needs balance"),
    # --- options-implied (CACHE_LIMITED) ---
    "rv_minus_iv": (generate_rv_minus_iv_trades, "OPTIONS", "Goyal-Saretto; chain cache"),
}
