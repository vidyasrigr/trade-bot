"""
Reddit sentiment cross-section job.

Builds on data/reddit.py — Boehmer-Jones-Zhang-Zhang (2021) retail-flow proxy.
Persists per-symbol counts to reddit_signals + cross-section ranks into
signal_ranks as two complementary tiles:

  - reddit_mentions     — universe rank by absolute mention volume (proxy for
                           retail attention)
  - reddit_polarity     — universe rank by net bullish - bearish polarity
                           (proxy for retail direction)

Anti-crowding: a name in the top decile of reddit_mentions gets flagged
crowded=true on the briefing UI (separate from the yt_mentions anti-crowding
already in compute_final_score — Reddit is a noisier signal so the gate is
ranking-based, not threshold-based).
"""

from __future__ import annotations

from datetime import date

from loguru import logger


async def run_reddit_sentiment_job() -> int:
    """Nightly cross-section over Reddit ticker mentions."""
    from data.reddit import fetch_mentions
    from scoring.cross_section import rank_values, persist_ranks
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    mentions = await fetch_mentions()
    if not mentions:
        logger.info("reddit_sentiment: no mentions to process")
        return 0

    today = date.today()
    async with AsyncSessionLocal() as session:
        for m in mentions:
            try:
                await session.execute(text("""
                    INSERT INTO reddit_signals
                        (symbol, as_of_date, total_mentions, bullish_mentions,
                         bearish_mentions, sources)
                    VALUES
                        (:sym, :d, :total, :bull, :bear, :sources)
                    ON CONFLICT (symbol, as_of_date) DO UPDATE SET
                        total_mentions = EXCLUDED.total_mentions,
                        bullish_mentions = EXCLUDED.bullish_mentions,
                        bearish_mentions = EXCLUDED.bearish_mentions,
                        sources = EXCLUDED.sources
                """), {
                    "sym": m.symbol, "d": today, "total": m.total_mentions,
                    "bull": m.bullish_mentions, "bear": m.bearish_mentions,
                    "sources": m.sources,
                })
            except Exception as e:
                logger.debug(f"reddit signal upsert failed for {m.symbol}: {e}")
        await session.commit()

        mention_scores = {m.symbol: float(m.total_mentions) for m in mentions
                           if m.total_mentions > 0}
        polarity_scores = {m.symbol: float(m.net_polarity) for m in mentions
                            if m.total_mentions >= 3}  # need >=3 mentions for polarity to mean anything
        if mention_scores:
            await persist_ranks("reddit_mentions", rank_values(mention_scores), today, session)
        if polarity_scores:
            await persist_ranks("reddit_polarity", rank_values(polarity_scores), today, session)

    logger.info(
        f"reddit_sentiment: {len(mentions)} symbols, "
        f"{sum(1 for m in mentions if m.total_mentions >= 3)} with sufficient mentions"
    )
    return len(mentions)
