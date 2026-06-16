"""
Analysis engine — orchestrates all 20 category analyzers.
Returns AnalysisResult with per-category scores, signals, and raw indicator values.

Category weights (total = 100%):
  1. Market & Macro         8%
  2. Seasonality/Calendar   7%
  3. Fundamental/Catalyst   8%
  4. Trend/Market Structure 10%
  5. Support & Resistance   8%
  6. Candlestick Patterns   7%
  7. Chart Patterns         7%
  8. Volume & Momentum      7%
  9. IV & Volatility        12%
  10. Options Chain         10%
  11. Greeks                 8%
  12. Trade Structure        5%
  13. Sentiment/Smart Money  5%
  14. Liquidity & Execution  5%
  15. Day of Week Bias        4%
  16. Risk Management         5%
  NEW. GEX/DEX/Vanna/Charm  (replaces weight from Risk when active)
  NEW. Institutional Flow    (included in Sentiment weight)
  NEW. Volatility Regime     (included in IV weight)
  NEW. Earnings-Adjusted IV  (included in IV weight)
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from loguru import logger

from data.market import get_ohlcv_yfinance, get_av
from data.tradier import get_tradier
from data.validators import validate_ohlcv


@dataclass
class CategoryScore:
    name: str
    weight: float
    raw_score: float       # 0–10
    weighted_score: float  # raw_score * weight / 10
    direction: str         # 'bullish', 'bearish', 'neutral'
    signals: list[dict]    # individual sub-signals that fired
    summary: str = ""


@dataclass
class AnalysisResult:
    symbol: str
    total_score: float = 0.0          # 0–100
    direction: str = "neutral"
    vol_regime: str = "unknown"
    iv_percentile: float | None = None
    underlying_price: float | None = None
    category_scores: dict[str, CategoryScore] = field(default_factory=dict)
    trade_thesis: str = ""
    catalyst_flags: list[str] = field(default_factory=list)
    recommended_structure: str = ""
    recommended_expiry: str = ""
    recommended_strike: float | None = None
    order_ticket: dict = field(default_factory=dict)
    raw_signals: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "total_score": self.total_score,
            "direction": self.direction,
            "vol_regime": self.vol_regime,
            "iv_percentile": self.iv_percentile,
            "underlying_price": self.underlying_price,
            "category_scores": {
                k: {
                    "name": v.name,
                    "weight": v.weight,
                    "raw_score": v.raw_score,
                    "weighted_score": v.weighted_score,
                    "direction": v.direction,
                    "signals": v.signals,
                    "summary": v.summary,
                }
                for k, v in self.category_scores.items()
            },
            "trade_thesis": self.trade_thesis,
            "catalyst_flags": self.catalyst_flags,
            "recommended_structure": self.recommended_structure,
            "order_ticket": self.order_ticket,
            "raw_signals": self.raw_signals,
        }


# Category weights — re-normalized 2026-06-15 to sum to exactly 100.
# These are *initial priors*. The LightGBM cross-sectional ranker (Phase E)
# learns the empirical weights from forward returns; until it has enough
# training data, these priors drive the conviction score.
# Previous version summed to 102 (hand-tuned, off-by-2).
CATEGORY_WEIGHTS = {
    "macro":              6.0,
    "calendar":           6.0,
    "fundamental":        7.0,
    "trend":              9.0,
    "support_resistance": 7.0,
    "candles":            5.0,
    "chart_patterns":     6.0,
    "momentum":           6.0,
    "iv_analysis":       11.0,
    "options_chain":      9.0,
    "greeks":             8.0,
    "trade_structure":    5.0,
    "sentiment":          5.0,
    "liquidity":          5.0,
    "risk":               5.0,
}
assert sum(CATEGORY_WEIGHTS.values()) == 100, (
    f"CATEGORY_WEIGHTS must sum to 100, got {sum(CATEGORY_WEIGHTS.values())}"
)


async def run_analysis(symbol: str, context: dict | None = None) -> AnalysisResult:
    """
    Full 20-category analysis for one symbol.
    Fetches all data needed and runs all category analyzers.
    """
    result = AnalysisResult(symbol=symbol)

    # Fetch base data (all analyzers need OHLCV)
    df = get_ohlcv_yfinance(symbol, period="1y")
    q = validate_ohlcv(symbol, df)
    result.data_quality = q.to_dict()
    if not q.is_valid or df.empty:
        logger.warning(f"Data quality failed for {symbol}: {q.issues}")
        return result

    result.underlying_price = float(df["close"].iloc[-1])

    # Fetch options data
    tradier = get_tradier()
    try:
        chain = await tradier.get_best_chain(symbol, min_dte=14, max_dte=60)
        iv_surface = await tradier.get_iv_surface(symbol) if chain else {}
    except Exception as e:
        logger.warning(f"Options data failed for {symbol}: {e}")
        chain, iv_surface = [], {}

    # Run all category analyzers (parallel where independent)
    from analysis import (
        macro as macro_mod,
        calendar as cal_mod,
        fundamental as fund_mod,
        trend as trend_mod,
        support_resistance as sr_mod,
        candles as candle_mod,
        chart_patterns as cp_mod,
        momentum as mom_mod,
        iv_analysis as iv_mod,
        options_chain as oc_mod,
        greeks as greek_mod,
        trade_structure_analysis as ts_mod,
        sentiment as sent_mod,
        liquidity as liq_mod,
        risk as risk_mod,
        gex_dex as gex_mod,
        options_flow as flow_mod,
        volatility_regime as vr_mod,
        earnings_adj_iv as eiv_mod,
    )

    # Independent analyzers run in parallel
    tasks = {
        "macro":              macro_mod.analyze(symbol, df),
        "calendar":           cal_mod.analyze(symbol, df),
        "fundamental":        fund_mod.analyze(symbol, df),
        "trend":              trend_mod.analyze(symbol, df),
        "support_resistance": sr_mod.analyze(symbol, df),
        "candles":            candle_mod.analyze(symbol, df),
        "chart_patterns":     cp_mod.analyze(symbol, df),
        "momentum":           mom_mod.analyze(symbol, df),
        "iv_analysis":        iv_mod.analyze(symbol, df, chain, iv_surface),
        "options_chain":      oc_mod.analyze(symbol, df, chain),
        "greeks":             greek_mod.analyze(symbol, df, chain),
        "trade_structure":    ts_mod.analyze(symbol, df, chain),
        "sentiment":          sent_mod.analyze(symbol, df, chain),
        "liquidity":          liq_mod.analyze(symbol, df, chain),
        "risk":               risk_mod.analyze(symbol, df),
        "gex_dex":            gex_mod.analyze(symbol, df, chain),
        "options_flow":       flow_mod.analyze(symbol, df, chain),
        "volatility_regime":  vr_mod.analyze(symbol, df),
        "earnings_adj_iv":    eiv_mod.analyze(symbol, df, chain),
    }

    task_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # Failed analyzers contribute ZERO — scoring them 5/10 neutral inflated
    # data-poor symbols (a symbol with every analyzer down used to score 50/100).
    analyzer_failures: list[str] = []
    for key, task_result in zip(tasks.keys(), task_results):
        if isinstance(task_result, Exception):
            logger.debug(f"Analyzer {key} failed for {symbol}: {task_result}")
            weight = CATEGORY_WEIGHTS.get(key, 5.0)
            analyzer_failures.append(key)
            result.category_scores[key] = CategoryScore(
                name=key, weight=weight, raw_score=0.0,
                weighted_score=0.0,
                direction="neutral", signals=[],
                summary=f"Analyzer unavailable: {type(task_result).__name__}",
            )
        else:
            result.category_scores[key] = task_result
    if analyzer_failures:
        result.data_quality["analyzer_failures"] = analyzer_failures

    # Compute total score
    total = sum(c.weighted_score for c in result.category_scores.values())
    result.total_score = round(min(total, 100.0), 2)

    # Determine overall direction by weighted directional vote
    bullish_weight = sum(
        c.weighted_score for c in result.category_scores.values() if c.direction == "bullish"
    )
    bearish_weight = sum(
        c.weighted_score for c in result.category_scores.values() if c.direction == "bearish"
    )
    if bullish_weight > bearish_weight * 1.3:
        result.direction = "bullish"
    elif bearish_weight > bullish_weight * 1.3:
        result.direction = "bearish"
    else:
        result.direction = "neutral"

    # Pull vol_regime from the volatility_regime analyzer
    vr = result.category_scores.get("volatility_regime")
    if vr and vr.signals:
        for sig in vr.signals:
            if "regime" in sig:
                result.vol_regime = sig["regime"]
                break

    # Pull IV percentile from iv_analysis
    iv_cat = result.category_scores.get("iv_analysis")
    if iv_cat and iv_cat.signals:
        for sig in iv_cat.signals:
            if "iv_percentile" in sig:
                result.iv_percentile = sig["iv_percentile"]
                break

    return result


async def quick_score(symbol: str) -> dict:
    """
    Lighter-weight scoring for Stage 2 — runs technical categories only (no options API calls).
    Returns {symbol, total_score, direction, signals}.
    """
    try:
        df = get_ohlcv_yfinance(symbol, period="6mo")
        if df.empty or len(df) < 20:
            return {"symbol": symbol, "total_score": 0, "direction": "neutral", "signals": []}

        from analysis import (
            trend as trend_mod,
            momentum as mom_mod,
            support_resistance as sr_mod,
            candles as candle_mod,
            volatility_regime as vr_mod,
        )

        tasks = {
            "trend":             trend_mod.analyze(symbol, df),
            "momentum":          mom_mod.analyze(symbol, df),
            "support_resistance": sr_mod.analyze(symbol, df),
            "candles":           candle_mod.analyze(symbol, df),
            "volatility_regime": vr_mod.analyze(symbol, df),
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        total = 0.0
        directions = {"bullish": 0, "bearish": 0, "neutral": 0}

        for key, r in zip(tasks.keys(), results):
            if isinstance(r, Exception):
                total += 5.0
                directions["neutral"] += 1
            else:
                total += r.raw_score
                directions[r.direction] += 1

        avg_score = total / len(tasks) * 10
        dominant_dir = max(directions, key=directions.get)

        return {
            "symbol": symbol,
            "total_score": round(avg_score, 2),
            "direction": dominant_dir,
            "category_scores": {},
            "signals": [],
        }
    except Exception as e:
        logger.debug(f"Quick score failed for {symbol}: {e}")
        return {"symbol": symbol, "total_score": 0, "direction": "neutral", "signals": []}
