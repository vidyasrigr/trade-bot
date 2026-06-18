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
from data.marketdata import get_tradier
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
    # Space economy (VORB removed — Virgin Orbit delisted/bankrupt 2023)
    "space": ["RDW", "RKLB", "ASTS"],
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
    "robotics": ["TSLA"],
    # Auto / EV / manufacturing
    "auto_ev": ["GM", "F", "RACE", "RIVN"],
    # AI software / fintech
    "ai_software_fintech": ["HOOD", "NOW", "CRM", "ORCL", "IBM", "SAP"],
    # Presidential alpha tracker
    "presidential_alpha": ["PLTR", "NVDA", "META", "MSFT"],
}

TIER3_CATALYST_WATCHLIST: list[str] = []  # populated dynamically by catalyst.py


def get_full_universe() -> list[str]:
    """Static always-include set: tier lists + catalyst watchlist (~150 symbols)."""
    symbols = set(TIER1_UNIVERSE)
    for group in TIER2_THEME_STOCKS.values():
        symbols.update(group)
    symbols.update(TIER3_CATALYST_WATCHLIST)
    return sorted(symbols)


def _theme_symbols() -> set[str]:
    s: set[str] = set()
    for group in TIER2_THEME_STOCKS.values():
        s.update(group)
    return s


async def get_scan_universe() -> list[str]:
    """
    Dynamic universe (full Nasdaq Trader directory, ~5,000+ names) unioned with
    the static always-include set. The static lists used to BE the universe,
    which made the scanner a mirror of pre-existing theme convictions —
    now themes are a stage-1 score boost, not the boundary.
    """
    from data.universe import get_dynamic_universe

    static = set(get_full_universe())
    dynamic = await get_dynamic_universe()
    if not dynamic:
        logger.warning(
            "Dynamic universe fetch FAILED — scanning static ~150-symbol list only. "
            "Results will be biased toward pre-existing themes."
        )
        return sorted(static)
    return sorted(static | set(dynamic))


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

    theme_set = _theme_symbols()

    # Chunked batch download (single 5,000-ticker yfinance call is unreliable)
    chunk_size = 250
    data: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i : i + chunk_size]
        data.update(get_multi_ohlcv_yfinance(chunk, period="3mo"))
        if len(symbols) > chunk_size:
            await asyncio.sleep(0.5)  # be polite to yfinance on full-universe scans

    results = []
    for symbol, df in data.items():
        q = validate_ohlcv(symbol, df)
        if not q.is_valid or df.empty or len(df) < 20:
            continue

        try:
            last_close = float(df["close"].iloc[-1])
            if not (5 <= last_close <= 2000):
                continue

            # Liquidity floor: $5M avg daily dollar volume — below this the
            # options chain (if any) will not pass the liquidity gate anyway
            avg_vol = df["volume"].iloc[-21:-1].mean()
            if avg_vol * last_close < 5_000_000:
                continue

            # 20-day momentum (simple return)
            ret_20d = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1) if len(df) >= 21 else 0

            # Volume anomaly: today vs 20-day avg
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

            # Theme boost — conviction themes get priority, not exclusivity
            is_theme = symbol in theme_set
            if is_theme:
                score += 2.0

            results.append({
                "symbol": symbol,
                "stage1_score": round(score, 3),
                "last_close": last_close,
                "ret_20d": round(ret_20d, 4),
                "vol_ratio": round(vol_ratio, 3),
                "price_pct_52range": round(price_pct_52range, 3),
                "theme_member": is_theme,
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

    SIDE EFFECT: persists a feature snapshot to the point-in-time feature store
    for today before returning. The snapshot includes every category raw_score
    + underlying_price + iv_percentile so downstream backtests can replay the
    exact state the scanner saw.
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

    # Persist today's feature snapshot for point-in-time backtests.
    await _persist_feature_snapshot(scored)

    logger.info(f"Stage 2 complete: {len(scored)} → {len(survivors)} survivors")
    return survivors


async def _persist_feature_snapshot(scored: list[dict]) -> None:
    """
    Append today's stage-2 scores to the point-in-time feature store.

    Long-format rows: (symbol, feature_name, value). Idempotent within a day
    (the store refuses overwrite unless explicit) — a second scan the same day
    is a no-op rather than corrupting history.
    """
    if not scored:
        return
    try:
        from store.feature_store import get_feature_store
        import pandas as pd
        from datetime import date

        rows: list[dict] = []
        for item in scored:
            symbol = item.get("symbol")
            if not symbol:
                continue
            stage1 = item.get("stage1_data") or {}

            # Scalar features that go straight in
            for name, value in (
                ("total_score", item.get("total_score")),
                ("ret_20d", stage1.get("ret_20d")),
                ("vol_ratio", stage1.get("vol_ratio")),
                ("price_pct_52range", stage1.get("price_pct_52range")),
                ("last_close", stage1.get("last_close")),
                ("theme_member", 1.0 if stage1.get("theme_member") else 0.0),
            ):
                if value is not None:
                    try:
                        rows.append({"symbol": symbol, "feature_name": name, "value": float(value)})
                    except (TypeError, ValueError):
                        continue

            # Per-category raw_scores from quick_score (Stage 2)
            for cat_key, cat in (item.get("category_scores") or {}).items():
                raw = cat.get("raw_score") if isinstance(cat, dict) else None
                if raw is not None:
                    try:
                        rows.append({"symbol": symbol, "feature_name": f"cat_{cat_key}",
                                     "value": float(raw)})
                    except (TypeError, ValueError):
                        continue

        if not rows:
            return
        df = pd.DataFrame(rows)
        store = get_feature_store()
        try:
            store.write_snapshot(date.today(), df)
        except FileExistsError:
            logger.debug(f"feature_store: snapshot for {date.today()} already exists, skipping")
    except Exception as e:
        logger.warning(f"feature_store snapshot write failed (non-fatal): {e}")


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
            # political_boost AND halo_boost are both captured as *features* surfaced
            # to the LLM and the UI, but NOT added to adjusted_score. Both are weak
            # signals (NBER on political disclosures; IPO halo edge ranges 0-5% in the
            # literature). Rolling them into ranking previously overweighted them; the
            # LightGBM ranker (Phase E) is the right place to learn their actual weight.
            political_boost = await get_political_boost(symbol)
            halo_boost = await get_halo_boost(symbol)

            adjusted_score = item["total_score"]
            adjusted_score += flags.get("score_delta", 0)

            # Crowding is flagged here but penalized ONCE, in scoring/weighted.py
            # (compute_final_score) — applying it in both places double-counted it.
            yt_mentions = flags.get("yt_mentions_this_week", 0)
            flags["crowded"] = yt_mentions >= 5

            item.update({
                "adjusted_score": round(adjusted_score, 2),
                "catalyst_flags": flags,
                "political_boost": political_boost,  # feature only, not in score
                "halo_boost": halo_boost,            # feature only, not in score
            })
            augmented.append(item)
        except Exception as e:
            logger.warning(f"Stage 3 augmentation failed for {symbol}: {e}")
            item["adjusted_score"] = item.get("total_score", 0)
            item["catalyst_flags"] = {}
            augmented.append(item)

    # Apply LightGBM ranker (Phase E) when a trained model is available — the
    # ranker's predicted excess return is added to adjusted_score as a multiplicative
    # tilt, so symbols the *learned* model expects to outperform get prioritized.
    # When no model exists (e.g. before the first weekly retrain), this is a no-op
    # and ranking falls back to the hand-tuned BASE_WEIGHTS × IC path.
    augmented = await _apply_ml_ranker(augmented)

    augmented.sort(key=lambda x: x.get("adjusted_score", 0), reverse=True)
    cutoff = min(25, len(augmented))
    survivors = augmented[:cutoff]

    logger.info(f"Stage 3 complete: {len(augmented)} → {len(survivors)} survivors")
    return survivors


async def _ranker_has_enough_labels(min_labels: int = 500) -> bool:
    """
    P0 Stage 2.2 — keep the LightGBM ranker in SHADOW MODE (no score tilt) until
    there are >= min_labels closed real outcomes. With a thin/biased label set the
    ranker would learn scanner bias instead of edge. Auto-enables once crossed.
    """
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as s:
            n = (await s.execute(text("SELECT count(*) FROM recommendation_outcomes"))).scalar() or 0
        if n < min_labels:
            logger.warning(f"ML ranker SHADOW MODE: {n}/{min_labels} closed labels — tilt disabled")
            return False
        return True
    except Exception as e:
        logger.debug(f"ranker label check failed ({e}); disabling tilt to be safe")
        return False


async def _apply_ml_ranker(augmented: list[dict]) -> list[dict]:
    """
    Multiply each stage-3 score by (1 + ranker_z) where ranker_z is the
    predicted forward 21d excess return standardized cross-sectionally.
    Tilt magnitude is capped at ±25% to keep the hand-tuned baseline
    influential until the ML model is calibrated.
    """
    if not await _ranker_has_enough_labels():
        return augmented  # shadow mode — no tilt
    try:
        from scoring.ranker import score_symbols, latest_artifact
        from store.feature_store import get_feature_store
    except ImportError:
        return augmented

    if latest_artifact(horizon=21) is None:
        return augmented

    try:
        store = get_feature_store()
        latest = store.latest_snapshot()
        if not latest:
            return augmented
        latest_d, _ = latest
        symbols = [item["symbol"] for item in augmented]
        panel = store.read_panel(
            features=[
                "total_score", "ret_20d", "vol_ratio", "price_pct_52range",
                "cat_iv_analysis", "cat_momentum", "cat_trend", "cat_options_flow",
                "cat_gex_dex", "cat_volatility_regime",
            ],
            start=latest_d, end=latest_d, symbols=symbols,
        )
        if panel.empty:
            return augmented
        rows = {r["symbol"]: {k: v for k, v in r.items()
                              if k not in ("as_of_date", "symbol")}
                for _, r in panel.iterrows()}
        preds = score_symbols(rows, horizon=21)
        if not preds:
            return augmented

        import numpy as np
        vals = np.array(list(preds.values()), dtype=float)
        mean, std = float(vals.mean()), float(vals.std(ddof=1) or 1.0)
        for item in augmented:
            sym = item["symbol"]
            if sym not in preds:
                item["ranker_score"] = None
                continue
            z = (float(preds[sym]) - mean) / std
            tilt = max(-0.25, min(0.25, z * 0.10))  # cap at ±25%
            item["ranker_score"] = round(float(preds[sym]), 6)
            item["ranker_tilt"] = round(tilt, 4)
            item["adjusted_score"] = round(item["adjusted_score"] * (1.0 + tilt), 2)
    except Exception as e:
        logger.debug(f"ML ranker tilt skipped: {e}")
    return augmented


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
        symbols = await get_scan_universe()

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
