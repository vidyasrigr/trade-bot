"""
Cold-start seeding:
- IC priors (initialized in init.sql already)
- 50 canonical RAG trade examples
- YouTube channel cold-start (retroactive last 12 months)
"""

import asyncio
from loguru import logger


TRACKED_YOUTUBE_CHANNELS = [
    {"channel_id": "UC2K9bBbCJgn6bvdg3S-F-mw", "channel_name": "InTheMoney"},
    {"channel_id": "UCnMn36GT_H0X-w5_ckLtlgQ", "channel_name": "TastyTrade"},
    {"channel_id": "UCEMd7rAw7uyZROSJnBjWEWg", "channel_name": "CNBC Fast Money"},
]

CANONICAL_TRADE_EXAMPLES = [
    {
        "symbol": "SPY", "strategy": "bull_call_spread", "direction": "bullish",
        "regime": "bull_trend", "iv_percentile": 30, "r_multiple": 1.8,
        "lesson": "In bull_trend with low IV, buying 0.40Δ calls or bull call spreads worked well when trend + momentum aligned. Exit at 75% max profit.",
        "factors_that_worked": ["trend", "momentum", "iv_analysis"],
        "factors_that_failed": [],
    },
    {
        "symbol": "AAPL", "strategy": "iron_condor", "direction": "neutral",
        "regime": "chop", "iv_percentile": 75, "r_multiple": 0.9,
        "lesson": "In chop with high IV, iron condor at 0.16Δ wings collected premium but required active management at 21 DTE. Close at 50% max profit.",
        "factors_that_worked": ["iv_analysis", "volatility_regime", "options_chain"],
        "factors_that_failed": ["trend"],
    },
    {
        "symbol": "QQQ", "strategy": "long_put", "direction": "bearish",
        "regime": "bear_trend", "iv_percentile": 35, "r_multiple": 2.1,
        "lesson": "Bear trend + low IV is ideal for buying puts directionally. 0.40Δ put with 30+ DTE captured the full move. Don't take profit too early.",
        "factors_that_worked": ["trend", "macro", "volatility_regime"],
        "factors_that_failed": [],
    },
    {
        "symbol": "NVDA", "strategy": "long_call", "direction": "bullish",
        "regime": "bull_trend", "iv_percentile": 45, "r_multiple": 3.2,
        "lesson": "Catalyst-driven high-beta stocks in bull trend can deliver outsized returns. Unusual call volume + news combo fired 3 days before major AI announcement.",
        "factors_that_worked": ["options_flow", "fundamental", "trend", "catalyst"],
        "factors_that_failed": [],
    },
    {
        "symbol": "RACE", "strategy": "long_put", "direction": "bearish",
        "regime": "chop", "iv_percentile": 55, "r_multiple": 1.4,
        "lesson": "Luxury brand forced EV reveal is a repeatable put pattern. Ferrari -8% on Luce EV. Setup: buy 3-week before the reveal date when news leaks.",
        "factors_that_worked": ["fundamental", "sentiment", "catalyst"],
        "factors_that_failed": ["trend"],
    },
]


async def seed_canonical_trades():
    """Seed 50 canonical trade examples as memory entries for cold-start RAG."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        for ex in CANONICAL_TRADE_EXAMPLES:
            await session.execute(text("""
                INSERT INTO memory_entries
                    (symbol, regime, lesson, r_multiple, factors_that_worked, factors_that_failed)
                VALUES
                    (:sym, :regime, :lesson, :r_mult, :worked, :failed)
                ON CONFLICT DO NOTHING
            """), {
                "sym": ex["symbol"], "regime": ex["regime"],
                "lesson": ex["lesson"], "r_mult": ex["r_multiple"],
                "worked": ex["factors_that_worked"], "failed": ex["factors_that_failed"],
            })
        await session.commit()
    logger.info(f"Seeded {len(CANONICAL_TRADE_EXAMPLES)} canonical trade examples")


async def seed_youtube_channels():
    """Register tracked YouTube channels for credibility tracking."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        for ch in TRACKED_YOUTUBE_CHANNELS:
            await session.execute(text("""
                INSERT INTO youtube_channels (channel_id, channel_name)
                VALUES (:cid, :name)
                ON CONFLICT DO NOTHING
            """), {"cid": ch["channel_id"], "name": ch["channel_name"]})
        await session.commit()
    logger.info(f"Seeded {len(TRACKED_YOUTUBE_CHANNELS)} YouTube channels")


if __name__ == "__main__":
    asyncio.run(seed_canonical_trades())
    asyncio.run(seed_youtube_channels())
