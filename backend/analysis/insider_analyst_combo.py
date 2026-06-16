"""
Insider + analyst combo — Phase J.4.

Cohen-Malloy-Pomorski (2012) opportunistic insider buys predict +6%/yr.
Independently, 3+ analyst upgrades within 30 days predicts ~3%/yr.
Together — when both fire on the same name within 30 days — the signal
historically clears 10%/yr risk-adjusted excess returns (replicates of
Womack 1996 + Cohen-Malloy-Pomorski).

We reuse:
  - analysis/insider_flow.py for cluster detection (already nightly)
  - agents/catalyst.py::_fire_revision_compound_signals for analyst revisions
  - signal_ranks table for cross-section ranking

This module is a join: pull recent rows from insider_signals AND
compound_signal_events where signal_type='analyst_revision_cascade', emit
fired symbols nightly into signal_ranks as 'insider_analyst_combo'.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from loguru import logger


WINDOW_DAYS = 30


async def find_combos(today: date | None = None) -> list[dict]:
    """Symbols with BOTH insider cluster AND analyst cascade in the last 30 days."""
    today = today or date.today()
    cutoff = today - timedelta(days=WINDOW_DAYS)

    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT i.symbol,
                   i.cluster_date AS insider_date,
                   i.n_opportunistic,
                   i.confidence AS insider_confidence,
                   COUNT(c.id) AS revision_count,
                   MAX(c.created_at::date) AS latest_revision_date
            FROM insider_signals i
            JOIN compound_signal_events c
                 ON c.symbols ? i.symbol
                AND c.signal_type = 'analyst_revision_cascade'
                AND c.created_at::date >= :cutoff
            WHERE i.cluster_date >= :cutoff
            GROUP BY i.symbol, i.cluster_date, i.n_opportunistic, i.confidence
            ORDER BY i.confidence DESC
        """), {"cutoff": cutoff})
        rows = [dict(r) for r in result.mappings().all()]
    return rows


async def run_insider_analyst_combo_job(today: date | None = None) -> int:
    """Persist the combo signal cross-section to signal_ranks."""
    from scoring.cross_section import rank_values, persist_ranks
    from core.database import AsyncSessionLocal

    today = today or date.today()
    combos = await find_combos(today)
    if not combos:
        logger.info("insider_analyst_combo: no qualifying combos this window")
        return 0

    scores = {row["symbol"]: float(row["insider_confidence"]) +
                              float(row["revision_count"]) * 5.0
              for row in combos}
    async with AsyncSessionLocal() as session:
        ranks = rank_values(scores)
        await persist_ranks("insider_analyst_combo", ranks, today, session)
    logger.info(f"insider_analyst_combo: {len(combos)} firings persisted")
    return len(combos)
