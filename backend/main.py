"""
Options Trading Bot — FastAPI entry point.
Runs the API server, registers all routes, initializes the DB pool,
starts the APScheduler for nightly scans and background monitors.
"""

import asyncio
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routes import router
from api.auth_routes import router as auth_router
from api.lt_routes import router as lt_router
from api.portfolio_import import router as portfolio_router
from core.config import settings
from core.database import init_db, close_db
from core.redis_client import init_redis, close_redis


scheduler = AsyncIOScheduler(timezone="America/New_York")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Options Trading Bot...")

    await init_db()
    await init_redis()

    # Nightly DNA batch: 7:00 PM ET (after nightly scan completes)
    scheduler.add_job(
        run_nightly_dna_batch,
        CronTrigger(hour=19, minute=0, timezone="America/New_York"),
        id="nightly_dna",
        replace_existing=True,
    )

    # Nightly scan: 6:00 PM ET (after market close, before next open)
    scheduler.add_job(
        run_nightly_scan,
        CronTrigger(hour=18, minute=0, timezone="America/New_York"),
        id="nightly_scan",
        replace_existing=True,
    )

    # Position monitor: every 15 min during market hours (9:30–16:00 ET weekdays)
    scheduler.add_job(
        run_position_monitor,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/15",
            timezone="America/New_York",
        ),
        id="position_monitor",
        replace_existing=True,
    )

    # Catalyst detector: every 30 min during market hours
    scheduler.add_job(
        run_catalyst_detector,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-16",
            minute="*/30",
            timezone="America/New_York",
        ),
        id="catalyst_detector",
        replace_existing=True,
    )

    # Watchlist refresh: every 30 min during market hours
    scheduler.add_job(
        run_watchlist_refresh,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-16",
            minute="0,30",
            timezone="America/New_York",
        ),
        id="watchlist_refresh",
        replace_existing=True,
    )

    # Weekly IC weight compaction: Sunday 8 PM ET
    scheduler.add_job(
        run_weekly_compaction,
        CronTrigger(day_of_week="sun", hour=20, timezone="America/New_York"),
        id="weekly_compaction",
        replace_existing=True,
    )

    # Weekly meta-research: Sunday 9 PM ET (after compaction)
    scheduler.add_job(
        run_meta_research,
        CronTrigger(day_of_week="sun", hour=21, timezone="America/New_York"),
        id="meta_research",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")

    yield

    scheduler.shutdown(wait=False)
    await close_db()
    await close_redis()
    logger.info("Shutdown complete")


async def run_nightly_scan():
    from data.scanner import run_scan
    try:
        await run_scan()
    except Exception as e:
        logger.error(f"Nightly scan failed: {e}")


async def run_position_monitor():
    from agents.position_monitor import check_all_positions
    try:
        await check_all_positions()
    except Exception as e:
        logger.error(f"Position monitor failed: {e}")


async def run_catalyst_detector():
    from agents.catalyst import detect_catalysts
    try:
        await detect_catalysts()
    except Exception as e:
        logger.error(f"Catalyst detector failed: {e}")


async def run_watchlist_refresh():
    from agents.watchlist_agent import refresh_all_watchlist
    try:
        await refresh_all_watchlist()
    except Exception as e:
        logger.error(f"Watchlist refresh failed: {e}")


async def run_weekly_compaction():
    from agents.postmortem import compact_memory
    from agents.agent_monitor import flush_to_db
    try:
        await compact_memory()
        await flush_to_db()
    except Exception as e:
        logger.error(f"Weekly compaction failed: {e}")


async def run_meta_research():
    from agents.meta_researcher import run_meta_research as _run
    try:
        path = await _run()
        logger.info(f"Meta-research proposal written: {path}")
    except Exception as e:
        logger.error(f"Meta-research failed: {e}")


async def run_nightly_dna_batch():
    """
    Nightly incremental DNA refresh.
    Targets: watchlist + recent high-score scanner stocks + any stock not refreshed in 30 days.
    NOT the full universe — that's a one-time seed job (run_initial_dna_seed).
    """
    from analysis.stock_dna import run_nightly_dna_batch as _run
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT DISTINCT symbol FROM (
                    -- Watchlist stocks (always fresh)
                    SELECT symbol FROM stocks WHERE tier <= 2 AND is_active = TRUE

                    UNION

                    -- Recent high-score analysis results
                    SELECT DISTINCT symbol FROM analysis_results
                    WHERE analyzed_at > NOW() - INTERVAL '7 days'
                    AND total_score >= 60

                    UNION

                    -- Stocks with stale DNA (not refreshed in 30 days)
                    SELECT symbol FROM stock_dna
                    WHERE updated_at < NOW() - INTERVAL '30 days'
                ) sq
                LIMIT 200
            """))
            symbols = [r[0] for r in result.fetchall()]

        if symbols:
            await _run(symbols, max_concurrent=5)
            logger.info(f"Nightly DNA batch: refreshed {len(symbols)} stocks")
    except Exception as e:
        logger.error(f"Nightly DNA batch failed: {e}")


async def run_initial_dna_seed():
    """
    One-time job: seed DNA for entire scanner universe (5000+ stocks).
    Run manually once: POST /api/admin/seed-dna
    Runs in background, takes 8-12 hours, rate-limited.
    """
    from data.scanner import get_scanner_universe
    from analysis.stock_dna import run_nightly_dna_batch as _run
    try:
        universe = await get_scanner_universe(limit=5000)
        symbols = [s["symbol"] for s in universe]
        logger.info(f"Initial DNA seed: starting {len(symbols)} stocks")
        await _run(symbols, max_concurrent=3)  # slower to be yfinance-friendly
    except Exception as e:
        logger.error(f"Initial DNA seed failed: {e}")


app = FastAPI(
    title="Options Trading Bot",
    version="0.1.0",
    description="Agentic options trading system with LangGraph + Claude",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router, prefix="/api")
app.include_router(lt_router)
app.include_router(portfolio_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
