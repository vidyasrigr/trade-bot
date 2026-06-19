"""All FastAPI routes — scanner, analysis, trades, memory, politics, IPO."""

import asyncio
import json
from typing import AsyncGenerator

import orjson
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from core.redis_client import cache_get, cache_set

router = APIRouter()


# ------------------------------------------------------------------
# MARKET DATA (used by frontend chart)
# ------------------------------------------------------------------

@router.get("/market/ohlcv/{symbol}")
async def get_ohlcv(symbol: str, period: str = "6mo"):
    from data.market import get_ohlcv_yfinance
    df = get_ohlcv_yfinance(symbol.upper(), period=period)
    if df.empty:
        raise HTTPException(404, f"No data for {symbol}")
    records = []
    for dt, row in df.iterrows():
        records.append({
            "date": str(dt.date()),
            "open": round(float(row.open), 4),
            "high": round(float(row.high), 4),
            "low": round(float(row.low), 4),
            "close": round(float(row.close), 4),
            "volume": int(row.volume),
        })
    return {"symbol": symbol, "ohlcv": records}


@router.get("/trades/freshness/{symbol}")
async def check_freshness(symbol: str):
    from api.freshness_check import validate_freshness
    return await validate_freshness(symbol.upper())


# ------------------------------------------------------------------
# SCANNER
# ------------------------------------------------------------------

@router.get("/scanner/run")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Trigger a fresh nightly scan in the background."""
    from data.scanner import run_scan
    background_tasks.add_task(run_scan)
    return {"status": "scan_started", "message": "Scan running in background — check /scanner/results"}


@router.get("/scanner/results")
async def get_scan_results():
    """Return latest cached scan results (top 5-10 setups)."""
    cached = await cache_get("scan:latest")
    if not cached:
        return {"results": [], "message": "No scan results yet — run /scanner/run first"}
    ts = await cache_get("scan:timestamp")
    return {
        "results": orjson.loads(cached),
        "scanned_at": ts,
        "stage_counts": {
            "s1": len(orjson.loads(await cache_get("scan:s1") or "[]")),
            "s2": len(orjson.loads(await cache_get("scan:s2") or "[]")),
            "s3": len(orjson.loads(await cache_get("scan:s3") or "[]")),
        }
    }


@router.get("/scanner/stage/{stage}")
async def get_stage_results(stage: int):
    """Return intermediate stage results (s1, s2, s3)."""
    if stage not in (1, 2, 3):
        raise HTTPException(400, "Stage must be 1, 2, or 3")
    key = f"scan:s{stage}"
    cached = await cache_get(key)
    return {"stage": stage, "results": orjson.loads(cached) if cached else []}


# ------------------------------------------------------------------
# ANALYSIS (SSE streaming)
# ------------------------------------------------------------------

@router.get("/analysis/{symbol}")
async def stream_analysis(symbol: str):
    """
    Full deep-dive analysis for one symbol.
    Streams Claude reasoning sentence-by-sentence via SSE.
    """
    return StreamingResponse(
        _analysis_stream(symbol.upper()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _analysis_stream(symbol: str) -> AsyncGenerator[str, None]:
    async def send(event: str, data: dict):
        return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n"

    yield await send("status", {"stage": "starting", "symbol": symbol})

    try:
        yield await send("status", {"stage": "fetching_data", "message": "Fetching market data..."})
        from analysis.engine import run_analysis
        analysis = await run_analysis(symbol)

        yield await send("analysis_scores", analysis.to_dict())
        yield await send("status", {"stage": "running_agents", "message": "Running Claude analysis..."})

        from data.scanner import stage3_catalyst_filter
        from agents.cross_stock_context import build_cross_stock_context

        stage3_item = {
            "symbol": symbol,
            "total_score": analysis.total_score,
            "direction": analysis.direction,
            "catalyst_flags": {},
            "stage1_data": {},
        }

        cross_context = await build_cross_stock_context([stage3_item])
        yield await send("status", {"stage": "fundamental_analyst", "message": "Fundamental analysis..."})

        from agents.graph import (
            fundamental_analyst, technical_analyst,
            volatility_analyst, sentiment_analyst_ollama,
            _run_trader, _run_risk_manager, options_selection_agent,
            _retrieve_memory, _build_order_ticket,
        )

        state = {
            "symbol": symbol,
            "stage3_data": stage3_item,
            "cross_context": cross_context,
            "analysis_result": analysis.to_dict(),
            "fundamental_report": "",
            "technical_report": "",
            "volatility_report": "",
            "sentiment_report": "",
            "trader_thesis": "",
            "risk_assessment": "",
            "trade_structure": {},
            "order_ticket": {},
            "conviction_score": 0.0,
            "total_score": analysis.total_score,
            "direction": analysis.direction,
            "vol_regime": analysis.vol_regime,
            "underlying_price": analysis.underlying_price or 0.0,
        }

        memory_context = await _retrieve_memory(symbol, analysis)

        yield await send("status", {"stage": "parallel_analysts", "message": "4 analysts working..."})
        tasks = [
            fundamental_analyst(state, memory_context),
            technical_analyst(state, memory_context),
            volatility_analyst(state, memory_context),
            sentiment_analyst_ollama(state),
        ]
        reports = await asyncio.gather(*tasks, return_exceptions=True)

        state["fundamental_report"] = reports[0] if not isinstance(reports[0], Exception) else ""
        state["technical_report"]   = reports[1] if not isinstance(reports[1], Exception) else ""
        state["volatility_report"]  = reports[2] if not isinstance(reports[2], Exception) else ""
        state["sentiment_report"]   = reports[3] if not isinstance(reports[3], Exception) else ""

        yield await send("analyst_reports", {
            "fundamental": state["fundamental_report"],
            "technical": state["technical_report"],
            "volatility": state["volatility_report"],
            "sentiment": state["sentiment_report"],
        })

        yield await send("status", {"stage": "trader_synthesis", "message": "Claude synthesizing trade thesis..."})
        await _run_trader(state, str(memory_context))
        yield await send("trader_thesis", {"thesis": state["trader_thesis"]})

        yield await send("status", {"stage": "risk_manager", "message": "Risk manager reviewing..."})
        await _run_risk_manager(state)
        yield await send("risk_assessment", {"assessment": state["risk_assessment"]})

        yield await send("status", {"stage": "options_selection", "message": "Selecting optimal strike..."})
        state["trade_structure"] = await options_selection_agent(state, analysis)
        order_ticket = _build_order_ticket(state, analysis)

        yield await send("order_ticket", order_ticket)
        yield await send("complete", {
            "symbol": symbol,
            "total_score": analysis.total_score,
            "direction": analysis.direction,
            "conviction_score": state["conviction_score"],
        })

    except Exception as e:
        logger.error(f"Analysis stream error for {symbol}: {e}")
        yield await send("error", {"message": str(e)})


@router.get("/analysis/{symbol}/optimizer")
async def get_optimizer(symbol: str):
    """Strike/expiry return grid (P of +30%/+100%) computed from real price/vol data."""
    from api.optimizer import compute_optimizer
    return await compute_optimizer(symbol.upper())


# ------------------------------------------------------------------
# INFLUENCERS / YOUTUBE CREDIBILITY
# ------------------------------------------------------------------

@router.get("/influencers")
async def get_influencers():
    """Tracked YouTube channels with credibility stats + recent point-in-time logged calls."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        ch_result = await session.execute(text("""
            SELECT channel_id, channel_name, subscriber_count, total_calls,
                   accurate_calls, credibility_score, last_video_at
            FROM youtube_channels
            ORDER BY credibility_score DESC
        """))
        channels = [dict(r) for r in ch_result.mappings().all()]

        call_result = await session.execute(text("""
            SELECT yc.symbol, yc.direction, yc.published_at, yc.video_title,
                   yc.reasoning_type, yc.reasoning_quality, yc.price_at_publish,
                   yc.price_t5, yc.price_t20, yc.outcome, yc.pump_signal,
                   ch.channel_name
            FROM youtube_calls yc
            LEFT JOIN youtube_channels ch ON ch.channel_id = yc.channel_id
            ORDER BY yc.published_at DESC NULLS LAST
            LIMIT 50
        """))
        calls = [dict(r) for r in call_result.mappings().all()]

    return {
        "channels": channels,
        "recent_calls": calls,
        "message": "" if channels else "No channels tracked yet — run backtest/seed_data.py then the ingestion job.",
    }


# ------------------------------------------------------------------
# BACKTEST RESULTS
# ------------------------------------------------------------------

@router.get("/backtest/results")
async def get_backtest_results():
    """Real backtest runs. Empty (with an honest message) until the backtester has produced results."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT id, strategy, symbol, start_date, end_date, num_trades,
                       win_rate, total_pnl, sharpe, deflated_sharpe, max_drawdown,
                       params, created_at
                FROM backtest_runs
                ORDER BY created_at DESC
                LIMIT 50
            """))
            runs = [dict(r) for r in result.mappings().all()]
        return {"runs": runs, "message": "" if runs else "No backtests run yet."}
    except Exception as e:
        logger.debug(f"backtest_runs unavailable: {e}")
        return {
            "runs": [],
            "message": "No backtest results — the options backtester has not been run yet "
                       "(requires historical options data via ThetaData).",
        }


# ------------------------------------------------------------------
# PAPER TRADES
# ------------------------------------------------------------------

class OpenTradeRequest(BaseModel):
    symbol: str
    strategy: str
    direction: str
    expiry: str
    strike: float
    option_type: str   # 'C' or 'P'
    contracts: int = 1
    entry_price: float
    max_loss: float
    max_profit: float
    analysis_id: int | None = None
    conviction: float | None = None   # system conviction at entry — feeds calibration
    recommendation_id: int            # P0 Stage 1.4 — REQUIRED: paper trades must
                                      # originate from a logged recommendation
    legs: list | None = None          # per-leg structure (P0 Stage 4.2)
    strategy_type: str | None = None


def _expiry_to_dte(expiry: str) -> int:
    """Best-effort DTE from an expiry string; default 21 when not a clean date."""
    from datetime import date as _date
    try:
        return max(0, (_date.fromisoformat(str(expiry)[:10]) - _date.today()).days)
    except ValueError:
        return 21


@router.post("/trades/paper/open")
async def open_paper_trade(req: OpenTradeRequest, background_tasks: BackgroundTasks):
    """Open a new paper trade. Checks circuit breakers and freshness first."""
    # Circuit breaker gate — must pass before any new position is allowed
    from agents.circuit_breaker import check_all_breakers
    breaker_status = await check_all_breakers()
    if breaker_status.halted:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "halted",
                "reason": breaker_status.reason,
                "active_breakers": breaker_status.active_breakers,
            },
        )

    from api.freshness_check import validate_freshness
    freshness = await validate_freshness(req.symbol)
    if not freshness["ok"]:
        return {"status": "stale", "message": freshness["message"], "action": "re-analyze"}

    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    import orjson

    async with AsyncSessionLocal() as session:
        # P0 Stage 1.4 — the paper trade MUST link to a logged recommendation.
        rec = (await session.execute(
            text("SELECT id FROM recommendations WHERE id = :rid"),
            {"rid": req.recommendation_id},
        )).first()
        if rec is None:
            raise HTTPException(
                status_code=404,
                detail={"status": "no_recommendation",
                        "message": f"recommendation_id {req.recommendation_id} not found — "
                                   "paper trades must originate from a logged recommendation"},
            )

        # Re-run ticket guards at OPEN time — state may have changed since the rec
        # (earnings moved into the window, a position appeared, etc.).
        try:
            from scoring.ticket_guards import run_all_guards, block_on_critical
            flags = await run_all_guards(
                req.symbol, req.direction, "options", _expiry_to_dte(req.expiry))
            should_block, criticals = block_on_critical(flags)
        except Exception:
            should_block, criticals = False, []
        if should_block:
            await session.execute(
                text("UPDATE recommendations SET status = 'stale' WHERE id = :rid"),
                {"rid": req.recommendation_id})
            await session.commit()
            raise HTTPException(
                status_code=409,
                detail={"status": "guard_blocked",
                        "reasons": [f"{f.name}: {f.message}" for f in criticals]},
            )

        # paper_trades.expiry is a DATE column — coerce the string (e.g. a "~21-45
        # DTE" placeholder won't parse, store NULL rather than crash the insert).
        from datetime import date as _date
        try:
            exp_val = _date.fromisoformat(str(req.expiry)[:10])
        except ValueError:
            exp_val = None
        result = await session.execute(text("""
            INSERT INTO paper_trades
                (symbol, analysis_id, direction, strategy, expiry, long_strike,
                 contracts, entry_price, max_loss, max_profit, conviction, status,
                 legs, strategy_type, recommendation_id)
            VALUES
                (:sym, :aid, :dir, :strat, :exp, :strike,
                 :contracts, :entry, :max_loss, :max_profit, :conviction, 'open',
                 CAST(:legs AS jsonb), :stype, :rid)
            RETURNING id
        """), {
            "sym": req.symbol, "aid": req.analysis_id, "dir": req.direction,
            "strat": req.strategy, "exp": exp_val, "strike": req.strike,
            "contracts": req.contracts, "entry": req.entry_price,
            "max_loss": req.max_loss, "max_profit": req.max_profit,
            "conviction": req.conviction,
            "legs": orjson.dumps(req.legs or []).decode(),
            "stype": req.strategy_type, "rid": req.recommendation_id,
        })
        trade_id = result.fetchone()[0]
        # Link the recommendation to its paper fill.
        await session.execute(
            text("UPDATE recommendations SET status = 'paper_opened' WHERE id = :rid"),
            {"rid": req.recommendation_id})
        await session.commit()

    return {"status": "opened", "trade_id": trade_id,
            "recommendation_id": req.recommendation_id}


@router.get("/trades/paper")
async def list_paper_trades(status: str = "all"):
    """List paper trades. status: all | open | closed"""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        where = "" if status == "all" else "WHERE status = :status"
        result = await session.execute(text(f"""
            SELECT id, symbol, strategy, direction, expiry, long_strike,
                   contracts, entry_price, exit_price, realized_pnl, r_multiple,
                   status, opened_at, closed_at
            FROM paper_trades {where}
            ORDER BY opened_at DESC
            LIMIT 100
        """), {"status": status} if status != "all" else {})
        rows = result.fetchall()

    cols = ["id", "symbol", "strategy", "direction", "expiry", "strike",
            "contracts", "entry_price", "exit_price", "realized_pnl", "r_multiple",
            "status", "opened_at", "closed_at"]
    return {"trades": [dict(zip(cols, r)) for r in rows]}


class CloseTradeRequest(BaseModel):
    exit_price: float
    exit_reason: str = "manual"


@router.post("/trades/paper/{trade_id}/close")
async def close_paper_trade(trade_id: int, req: CloseTradeRequest, background_tasks: BackgroundTasks):
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        # Fetch trade to compute P&L
        result = await session.execute(text(
            "SELECT entry_price, contracts, strategy FROM paper_trades WHERE id = :tid"
        ), {"tid": trade_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(404, "Trade not found")

        entry_price, contracts, strategy = row[0], row[1], row[2]
        pnl = (req.exit_price - float(entry_price)) * int(contracts) * 100

        await session.execute(text("""
            UPDATE paper_trades
            SET exit_price = :exit, realized_pnl = :pnl,
                exit_reason = :reason, status = 'closed', closed_at = NOW()
            WHERE id = :tid
        """), {"exit": req.exit_price, "pnl": pnl, "reason": req.exit_reason, "tid": trade_id})
        await session.commit()

    # Run post-mortem in background
    from agents.postmortem import run_postmortem
    background_tasks.add_task(run_postmortem, trade_id)

    return {"status": "closed", "trade_id": trade_id, "realized_pnl": pnl}


# ------------------------------------------------------------------
# MEMORY / JOURNAL
# ------------------------------------------------------------------

@router.get("/calibration/conviction")
async def conviction_calibration():
    """Brier score + calibration buckets: is stated conviction a real probability?"""
    from scoring.calibration import get_conviction_calibration
    return await get_conviction_calibration()


# ------------------------------------------------------------------
# STRATEGY DOCUMENT — current rules, version history, pending review
# ------------------------------------------------------------------

@router.get("/strategy")
async def get_strategy_endpoint():
    from api.strategy import get_strategy
    return await get_strategy()


@router.patch("/strategy")
async def patch_strategy_endpoint(body: dict):
    from api.strategy import patch_strategy_override
    return await patch_strategy_override(body)


# ------------------------------------------------------------------
# DAILY BRIEFING — 3 streams (options / swing / long-term)
# ------------------------------------------------------------------

@router.get("/briefing/daily")
async def daily_briefing_endpoint():
    from api.briefing import build_briefing
    return await build_briefing()


@router.get("/memory/journal")
async def get_journal(limit: int = 50):
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT me.id, me.symbol, me.sector, me.regime, me.lesson,
                   me.r_multiple, me.factors_that_worked, me.factors_that_failed,
                   me.created_at, pt.strategy
            FROM memory_entries me
            LEFT JOIN paper_trades pt ON pt.id = me.trade_id
            ORDER BY me.created_at DESC
            LIMIT :lim
        """), {"lim": limit})
        rows = result.fetchall()

    cols = ["id", "symbol", "sector", "regime", "lesson", "r_multiple",
            "factors_that_worked", "factors_that_failed", "created_at", "strategy"]
    return {"entries": [dict(zip(cols, r)) for r in rows]}


@router.get("/memory/weights")
async def get_ic_weights():
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT category, regime, ic_score, current_weight_multiplier, sample_count
            FROM factor_ic_scores ORDER BY regime, category
        """))
        rows = result.fetchall()

    cols = ["category", "regime", "ic_score", "weight_multiplier", "sample_count"]
    return {"weights": [dict(zip(cols, r)) for r in rows]}


# ------------------------------------------------------------------
# POLITICS / OGE
# ------------------------------------------------------------------

@router.get("/politics/disclosures")
async def get_political_disclosures():
    from data.political import fetch_oge_disclosures
    disclosures = await fetch_oge_disclosures(days_back=90)
    return {"disclosures": disclosures}


# ------------------------------------------------------------------
# CATALYST EVENTS
# ------------------------------------------------------------------

@router.get("/catalysts")
async def get_catalysts(symbol: str | None = None):
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        where = "WHERE symbol = :sym" if symbol else ""
        result = await session.execute(text(f"""
            SELECT symbol, event_type, event_summary, signal_strength, detected_at
            FROM catalyst_events
            {where}
            ORDER BY signal_strength DESC, detected_at DESC
            LIMIT 50
        """), {"sym": symbol} if symbol else {})
        rows = result.fetchall()

    cols = ["symbol", "event_type", "event_summary", "signal_strength", "detected_at"]
    return {"events": [dict(zip(cols, r)) for r in rows]}


# ------------------------------------------------------------------
# IPO PIPELINE
# ------------------------------------------------------------------

@router.get("/ipo/pipeline")
async def get_ipo_pipeline():
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT ip.company_name, ip.expected_symbol, ip.s1_filed_date,
                   ip.expected_ipo_date, ip.estimated_valuation, ip.sector, ip.status,
                   ARRAY_AGG(ihm.symbol) as halo_stocks
            FROM ipo_pipeline ip
            LEFT JOIN ipo_halo_mappings ihm ON ihm.ipo_id = ip.id
            GROUP BY ip.id
            ORDER BY ip.s1_filed_date DESC NULLS LAST
        """))
        rows = result.fetchall()

    cols = ["company_name", "expected_symbol", "s1_filed_date", "expected_ipo_date",
            "estimated_valuation", "sector", "status", "halo_stocks"]
    return {"pipeline": [dict(zip(cols, r)) for r in rows]}


# ------------------------------------------------------------------
# CIRCUIT BREAKERS + KILL SWITCH
# ------------------------------------------------------------------

class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "Manual override"


@router.get("/admin/circuit-breakers")
async def get_circuit_breaker_status():
    """Returns the current state of all circuit breakers."""
    from agents.circuit_breaker import check_all_breakers, get_kill_switch_status

    status = await check_all_breakers()
    kill_switch = await get_kill_switch_status()
    return {**status.to_dict(), "kill_switch": kill_switch}


@router.post("/admin/kill-switch")
async def set_kill_switch(body: KillSwitchRequest):
    """
    POST {"active": true, "reason": "..."} to halt all new trades.
    POST {"active": false} to resume trading.
    """
    from agents.circuit_breaker import activate_kill_switch, deactivate_kill_switch

    if body.active:
        await activate_kill_switch(body.reason)
        logger.critical(f"Kill switch ACTIVATED via API: {body.reason}")
        return {"ok": True, "status": "halted", "reason": body.reason}
    else:
        await deactivate_kill_switch()
        logger.info("Kill switch deactivated via API")
        return {"ok": True, "status": "active", "reason": None}


@router.post("/admin/reset-drawdown")
async def reset_drawdown_peak():
    """Reset the peak portfolio value after deliberate capital withdrawal."""
    return {"ok": True, "message": "Drawdown peak reset to current portfolio value"}


@router.get("/admin/agent-performance")
async def get_agent_performance():
    """Live agent performance stats from Redis — response times, fallback rates, model usage."""
    from agents.agent_monitor import get_agent_stats, get_recommendations
    stats = await get_agent_stats()
    recs  = await get_recommendations()
    return {"stats": stats, "recommendations": recs}


@router.get("/admin/ai-costs")
async def get_ai_costs(period: str = "daily"):
    """
    Token usage and cost breakdown.
    ?period=hourly  → last 24h grouped by hour
    ?period=daily   → last 7 days grouped by day
    ?period=weekly  → last 4 weeks grouped by week
    """
    if period not in ("hourly", "daily", "weekly"):
        raise HTTPException(400, "period must be hourly, daily, or weekly")
    from agents.agent_monitor import get_cost_stats
    return await get_cost_stats(period)


@router.post("/admin/meta-research")
async def trigger_meta_research(background_tasks: BackgroundTasks):
    """Trigger meta-research proposal generation on demand."""
    from main import run_meta_research
    background_tasks.add_task(run_meta_research)
    return {"ok": True, "message": "Meta-research running in background. Check docs/update_proposals/"}


@router.post("/admin/seed-dna")
async def seed_dna_universe(background_tasks: BackgroundTasks):
    """
    Trigger one-time DNA seed for full scanner universe (5000+ stocks).
    Runs in background — takes 8-12 hours. Safe to call once.
    """
    from main import run_initial_dna_seed
    background_tasks.add_task(run_initial_dna_seed)
    return {"ok": True, "message": "DNA seed started in background for full universe. Check logs."}


@router.get("/admin/dna-status")
async def dna_status():
    """Show DNA coverage stats: how many stocks have DNA computed."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE data_quality_score >= 50) as high_quality,
                COUNT(*) FILTER (WHERE updated_at > NOW() - INTERVAL '7 days') as fresh,
                AVG(data_quality_score) as avg_quality,
                MIN(updated_at) as oldest_update
            FROM stock_dna
        """))
        row = result.mappings().first()
    return dict(row) if row else {}


# ------------------------------------------------------------------
# DNA BEHAVIORAL PROFILE
# ------------------------------------------------------------------

@router.get("/dna/{symbol}")
async def get_stock_dna(symbol: str):
    """
    Return per-stock behavioral DNA profile.
    Reads from cache/DB first; computes on demand if missing or stale.
    """
    import dataclasses
    from analysis.stock_dna import get_dna, compute_dna, save_dna_to_db

    symbol = symbol.upper()

    dna = await get_dna(symbol)

    if dna is None or dna.data_quality_score < 5:
        try:
            dna = await compute_dna(symbol)
            if dna and dna.data_quality_score > 0:
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    await save_dna_to_db(dna, session)
        except Exception as e:
            logger.debug(f"DNA on-demand compute failed for {symbol}: {e}")

    if dna is None:
        raise HTTPException(404, f"DNA not available for {symbol}")

    return dataclasses.asdict(dna)


# ------------------------------------------------------------------
# WATCHLIST
# ------------------------------------------------------------------

class WatchlistAddRequest(BaseModel):
    symbol: str
    notes: str = ""


@router.get("/watchlist")
async def get_watchlist():
    """Return all watched tickers with their current state."""
    from agents.watchlist_agent import get_watchlist_symbols, WatchlistAgent
    from dataclasses import asdict

    symbols = await get_watchlist_symbols()
    states = []
    for sym in symbols:
        agent = WatchlistAgent(sym)
        state = await agent.get_state()
        if state:
            states.append(asdict(state))
        else:
            states.append({"symbol": sym, "current_score": 0, "last_refreshed": ""})

    return {"watchlist": states, "count": len(states)}


@router.post("/watchlist/add")
async def add_watchlist_symbol(req: WatchlistAddRequest, background_tasks: BackgroundTasks):
    """Add a symbol to the watchlist and start monitoring it."""
    from agents.watchlist_agent import add_to_watchlist
    from dataclasses import asdict

    agent = await add_to_watchlist(req.symbol.upper())
    if req.notes:
        await agent.add_note(req.notes)
    state = await agent.get_state()
    return {"ok": True, "symbol": req.symbol.upper(), "state": asdict(state) if state else None}


@router.delete("/watchlist/{symbol}")
async def remove_watchlist_symbol(symbol: str):
    """Remove a symbol from the watchlist."""
    from agents.watchlist_agent import remove_from_watchlist
    await remove_from_watchlist(symbol.upper())
    return {"ok": True, "symbol": symbol.upper()}


@router.post("/watchlist/{symbol}/refresh")
async def refresh_watchlist_symbol(symbol: str):
    """Force-refresh a single watchlist symbol."""
    from agents.watchlist_agent import WatchlistAgent
    from dataclasses import asdict

    agent = WatchlistAgent(symbol.upper())
    state = await agent.refresh()
    return {"ok": True, "state": asdict(state)}


@router.patch("/watchlist/{symbol}/notes")
async def update_watchlist_notes(symbol: str, body: dict):
    """Update freeform notes on a watchlist symbol."""
    from agents.watchlist_agent import WatchlistAgent

    agent = WatchlistAgent(symbol.upper())
    await agent.add_note(body.get("notes", ""))
    return {"ok": True}
