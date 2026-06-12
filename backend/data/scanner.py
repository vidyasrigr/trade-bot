"""
5-stage signal funnel — filters ~5,000 stocks down to 5-10 actionable setups.

Stage 0: Full universe (~5,000 stocks) — static list filtered by options liquidity
Stage 1: Fast numerical pre-screen (nightly, zero LLM)
Stage 2: Technical factor scoring (20 categories, pandas-ta)
Stage 3: Catalyst + signal layer (Ollama local, free)
Stage 4: Deep analysis (Claude + LangGraph, ~90 sec/stock)
Stage 5: Human confirmation → paper trade
"""

import asyncio
from datetime import date, datetime
from typing import Any

import pandas as pd
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set
from data.market import get_ohlcv_yfinance, get_multi_ohlcv_yfinance, get_av
from data.tradier import get_tradier
from data.validators import validate_ohlcv


# ------------------------------------------------------------------
# STATIC UNIVERSE — 4 tiers
# All symbols with adequate options liquidity across 11 sectors
# ------------------------------------------------------------------

TIER1_UNIVERSE = [
    # S&P500 + Nasdaq100 backbone
    "SPY", "QQQ", "IWM", "TLT", "GLD", "USO",  # macro ETFs (also tradeable)
    "UVXY", "VIXY",                               # VIX products for hedge
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AVGO",
    "AMD", "INTC", "MU", "TSM", "ASML", "QCOM", "TXN", "AMAT", "LRCX",
    "JPM", "BAC", "GS", "MS", "WFC", "BRK.B",
    "UNH", "LLY", "JNJ", "ABBV", "PFE", "MRK",
    "XOM", "CVX", "COP",
    "COST", "WMT", "HD", "NKE",
    "NEE", "DUK",
    "BA", "LMT", "RTX", "NOC", "GD",
    "V", "MA", "PYPL", "SQ",
    "CRM", "ORCL", "SAP", "NOW", "SNOW",
    "NFLX", "DIS", "CMCSA",
]

TIER2_THEME_STOCKS = {
    # AI Full-Stack Infrastructure
    "ai_infra": [
        "NVDA", "AMD", "INTC", "MU", "SNDK", "NBIS", "ANET",
        "VRT", "NVT", "EQIX", "DLR", "STRL",
    ],
    # Photonics (2nd-order AI — copper→light supercycle)
    "photonics": ["LITE", "COHR", "FN", "TSEM"],
    # Semis supply chain (2nd-order)
    "semis_supply": ["AMAT", "ENTG", "ONTO", "AMKR", "ASML", "LRCX"],
    # Space economy
    "space": ["RDW", "RKLB", "ASTS", "VORB"],
    # Nuclear / energy
    "nuclear_energy": ["OKLO", "SMR", "LEU", "CCJ", "CEG", "BWXT", "ATI"],
    # Defense / autonomous drones
    "defense_drone": ["ONDS", "KTOS", "PLTR", "LMT", "RTX", "NOC"],
    # Quantum computing
    "quantum": ["IONQ", "RGTI", "QUBT", "IBM"],
    # Biotech / pharma / GLP-1
    "biotech_pharma": [
        "LLY", "NVO", "VKTX", "CRSP", "NTLA", "BEAM",
        "HIMS",         # GLP-1 2nd-order WIN (telehealth)
        "LULU", "NKE",  # fitness 2nd-order WIN
    ],
    # Robotics / humanoid
    "robotics": ["TSLA", "BOTT"],
    # Auto / EV / manufacturing
    "auto_ev": ["GM", "F", "RACE", "RIVN"],
    # AI software / fintech
    "ai_software_fintech": ["HOOD", "NOW", "CRM", "ORCL", "IBM", "SAP"],
    # Presidential alpha tracker
    "presidential_alpha": ["PLTR", "NVDA", "META", "MSFT"],
}

TIER3_CATALYST_WATCHLIST: list[str] = []  # populated dynamically by catalyst.py


def get_full_universe() -> list[str]:
    """Returns deduplicated full symbol universe across all tiers."""
    symbols = set(TIER1_UNIVERSE)
    for group in TIER2_THEME_STOCKS.values():
        symbols.update(group)
    symbols.update(TIER3_CATALYST_WATCHLIST)
    return sorted(symbols)


# ------------------------------------------------------------------
# STAGE 1: Fast Numerical Pre-Screen
# Input: ~2,500 (or subset), Output: ~300-400
# Zero LLM cost. Uses yfinance + basic pandas.
# ------------------------------------------------------------------

async def stage1_prescreen(symbols: list[str]) -> list[dict]:
    """
    Filters on:
    - Price $5–$2,000
    - 20-day avg options volume proxy (via price * volume as liquidity estimate)
    - Momentum Z-score: top/bottom 20% of 20-day returns
    - Volume anomaly ratio: today's vol > 1.2x 20-day avg vol
    - Not a stale ticker (has data within 3 days)

    Returns list of {symbol, score, signals} sorted by composite score descending.
    """
    logger.info(f"Stage 1: screening {len(symbols)} symbols...")

    # Batch download 1 year of history
    data = get_multi_ohlcv_yfinance(symbols, period="3mo")

    results = []
    for symbol, df in data.items():
        q = validate_ohlcv(symbol, df)
        if not q.is_valid or df.empty or len(df) < 20:
            continue

        try:
            last_close = float(df["close"].iloc[-1])
            if not (5 <= last_close <= 2000):
                continue

            # 20-day momentum (simple return)
            ret_20d = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1) if len(df) >= 21 else 0

            # Volume anomaly: today vs 20-day avg
            avg_vol = df["volume"].iloc[-21:-1].mean()
            today_vol = float(df["volume"].iloc[-1])
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0

            # 52-week proximity (distance to high/low)
            high_52 = df["high"].max()
            low_52 = df["low"].min()
            price_pct_52range = (last_close - low_52) / (high_52 - low_52) if (high_52 - low_52) > 0 else 0.5

            score = 0.0
            score += abs(ret_20d) * 30          # strong momentum (up or down) = signal
            score += min(vol_ratio, 3.0) * 10   # vol spike (capped at 3x)
            score += (1 - abs(price_pct_52range - 0.9)) * 10  # near 52-week high

            results.append({
                "symbol": symbol,
                "stage1_score": round(score, 3),
                "last_close": last_close,
                "ret_20d": round(ret_20d, 4),
                "vol_ratio": round(vol_ratio, 3),
                "price_pct_52range": round(price_pct_52range, 3),
            })
        except Exception as e:
            logger.debug(f"Stage 1 skip {symbol}: {e}")

    # Sort by score, take top 15%
    results.sort(key=lambda x: x["stage1_score"], reverse=True)
    cutoff = max(50, int(len(results) * 0.15))
    survivors = results[:cutoff]

    logger.info(f"Stage 1 complete: {len(results)} → {len(survivors)} survivors")
    return survivors


# ------------------------------------------------------------------
# STAGE 2: Technical Factor Scoring
# Input: ~300, Output: ~75
# Runs 20 weighted categories using pandas-ta + Tradier options data.
# ------------------------------------------------------------------

async def stage2_technical_scoring(stage1_results: list[dict]) -> list[dict]:
    """
    Scores each stock on 20 analysis categories.
    Returns top ~75 with per-category breakdown.
    """
    from analysis.engine import run_analysis
    from analysis.liquidity_gate import check_options_liquidity

    logger.info(f"Stage 2: technical scoring {len(stage1_results)} symbols...")
    scored = []

    # Batch these to avoid overwhelming APIs
    batch_size = 20
    for i in range(0, len(stage1_results), batch_size):
        batch = stage1_results[i : i + batch_size]
        tasks = [_score_single(s) for s in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for s1, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                logger.warning(f"Stage 2 failed for {s1['symbol']}: {result}")
                continue
            if result:
                scored.append(result)

    # Apply options liquidity gate
    passed_liquidity = []
    for item in scored:
        liq = await check_options_liquidity(item["symbol"])
        item["liquidity_ok"] = liq["ok"]
        item["liquidity_note"] = liq.get("note", "")
        if liq["ok"]:
            passed_liquidity.append(item)
        else:
            logger.debug(f"Liquidity gate rejected {item['symbol']}: {liq.get('note')}")

    passed_liquidity.sort(key=lambda x: x["total_score"], reverse=True)
    cutoff = min(75, len(passed_liquidity))
    survivors = passed_liquidity[:cutoff]

    logger.info(f"Stage 2 complete: {len(scored)} → {len(survivors)} survivors")
    return survivors


async def _score_single(s1: dict) -> dict | None:
    from analysis.engine import quick_score
    try:
        symbol = s1["symbol"]
        result = await quick_score(symbol)
        result["stage1_data"] = s1
        return result
    except Exception as e:
        logger.debug(f"Scoring failed for {s1['symbol']}: {e}")
        return None


# ------------------------------------------------------------------
# STAGE 3: Catalyst + Signal Layer
# Input: ~75, Output: ~25
# Ollama-powered news/catalyst overlay + anti-crowding.
# ------------------------------------------------------------------

async def stage3_catalyst_filter(stage2_results: list[dict]) -> list[dict]:
    """
    Augments with:
    - Recent news sentiment (Ollama-filtered)
    - YouTuber mentions count
    - Presidential OGE signal
    - IPO halo boost
    - Anti-crowding penalty (-20 score if 5+ YouTubers mentioned this week)
    """
    from agents.catalyst import get_catalyst_flags
    from data.political import get_political_boost
    from analysis.ipo_halo import get_halo_boost

    logger.info(f"Stage 3: catalyst filtering {len(stage2_results)} symbols...")

    augmented = []
    for item in stage2_results:
        symbol = item["symbol"]
        try:
            flags = await get_catalyst_flags(symbol)
            political_boost = await get_political_boost(symbol)
            halo_boost = await get_halo_boost(symbol)

            adjusted_score = item["total_score"]
            adjusted_score += flags.get("score_delta", 0)
            adjusted_score += political_boost
            adjusted_score += halo_boost

            # Anti-crowding: penalize over-hyped picks
            yt_mentions = flags.get("yt_mentions_this_week", 0)
            if yt_mentions >= 5:
                adjusted_score *= 0.80
                flags["crowded"] = True
            else:
                flags["crowded"] = False

            item.update({
                "adjusted_score": round(adjusted_score, 2),
                "catalyst_flags": flags,
                "political_boost": political_boost,
                "halo_boost": halo_boost,
            })
            augmented.append(item)
        except Exception as e:
            logger.warning(f"Stage 3 augmentation failed for {symbol}: {e}")
            item["adjusted_score"] = item.get("total_score", 0)
            item["catalyst_flags"] = {}
            augmented.append(item)

    augmented.sort(key=lambda x: x.get("adjusted_score", 0), reverse=True)
    cutoff = min(25, len(augmented))
    survivors = augmented[:cutoff]

    logger.info(f"Stage 3 complete: {len(augmented)} → {len(survivors)} survivors")
    return survivors


# ------------------------------------------------------------------
# STAGE 4: Deep LangGraph Analysis
# Input: ~25, Output: 5-10 ranked order tickets
# Claude does full analysis. Cross-stock context injected.
# ------------------------------------------------------------------

async def stage4_deep_analysis(stage3_results: list[dict]) -> list[dict]:
    """
    Runs LangGraph multi-agent analysis on each Stage 3 survivor.
    First builds cross-stock context document for Claude.
    Returns ranked final recommendations with full order tickets.
    """
    from agents.graph import run_analysis_graph
    from agents.cross_stock_context import build_cross_stock_context

    logger.info(f"Stage 4: deep LangGraph analysis on {len(stage3_results)} symbols...")

    cross_context = await build_cross_stock_context(stage3_results)

    tasks = [run_analysis_graph(item, cross_context) for item in stage3_results]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for item, result in zip(stage3_results, results):
        if isinstance(result, Exception):
            logger.warning(f"Stage 4 failed for {item['symbol']}: {result}")
            continue
        if result and result.get("trade_thesis"):
            final.append(result)

    # Rank by Claude's conviction score
    final.sort(key=lambda x: x.get("conviction_score", 0), reverse=True)
    top10 = final[:10]

    logger.info(f"Stage 4 complete: {len(final)} → {len(top10)} final recommendations")
    return top10


# ------------------------------------------------------------------
# MAIN SCAN ORCHESTRATOR
# ------------------------------------------------------------------

async def run_scan(symbols: list[str] | None = None) -> list[dict]:
    """
    Full 5-stage scan. Returns top 5-10 trade setups.
    Results are cached in Redis (TTL: 20 hours) and stored in DB.
    """
    logger.info("=== Starting nightly scan ===")

    if symbols is None:
        symbols = get_full_universe()

    logger.info(f"Universe: {len(symbols)} symbols")

    s1 = await stage1_prescreen(symbols)
    if not s1:
        logger.warning("Stage 1 returned no results")
        return []

    s2 = await stage2_technical_scoring(s1)
    if not s2:
        logger.warning("Stage 2 returned no results")
        return []

    s3 = await stage3_catalyst_filter(s2)
    if not s3:
        logger.warning("Stage 3 returned no results")
        return []

    final = await stage4_deep_analysis(s3)

    # Cache results
    import orjson
    await cache_set("scan:latest", orjson.dumps(final).decode(), ttl=72000)
    await cache_set("scan:s1", orjson.dumps(s1[:50]).decode(), ttl=72000)
    await cache_set("scan:s2", orjson.dumps(s2[:50]).decode(), ttl=72000)
    await cache_set("scan:s3", orjson.dumps(s3).decode(), ttl=72000)
    await cache_set("scan:timestamp", datetime.utcnow().isoformat(), ttl=72000)

    # Persist to DB
    await _persist_scan_results(final)

    logger.info(f"=== Scan complete: {len(final)} recommendations ===")
    return final


async def _persist_scan_results(results: list[dict]):
    """Store final scan results in analysis_results table."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        for r in results:
            try:
                await session.execute(text("""
                    INSERT INTO analysis_results
                        (symbol, analyzed_at, total_score, direction, vol_regime,
                         iv_percentile, category_scores, trade_thesis, catalyst_flags,
                         raw_signals, stage)
                    VALUES
                        (:symbol, NOW(), :total_score, :direction, :vol_regime,
                         :iv_percentile, :category_scores::jsonb, :trade_thesis,
                         :catalyst_flags, :raw_signals::jsonb, 4)
                """), {
                    "symbol": r["symbol"],
                    "total_score": r.get("total_score", 0),
                    "direction": r.get("direction", "neutral"),
                    "vol_regime": r.get("vol_regime", "unknown"),
                    "iv_percentile": r.get("iv_percentile"),
                    "category_scores": __import__("orjson").dumps(r.get("category_scores", {})).decode(),
                    "trade_thesis": r.get("trade_thesis", ""),
                    "catalyst_flags": __import__("orjson").dumps(r.get("catalyst_flags", [])).decode(),
                    "raw_signals": __import__("orjson").dumps(r.get("raw_signals", {})).decode(),
                })
            except Exception as e:
                logger.error(f"Failed to persist analysis for {r.get('symbol')}: {e}")
        await session.commit()
