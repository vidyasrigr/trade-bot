"""
Post-mortem agent — runs automatically when a trade closes.
Computes R-multiple, IC updates, RAG embedding, journal lesson.
"""

from loguru import logger
from core.config import settings


async def run_postmortem(trade_id: int):
    """Called when a paper trade closes."""
    trade = await _get_trade(trade_id)
    if not trade:
        return

    # R-multiple
    entry_risk = abs(float(trade.get("max_loss") or trade.get("entry_price") or 1))
    pnl = float(trade.get("realized_pnl") or 0)
    r_multiple = pnl / entry_risk if entry_risk > 0 else 0

    # Update trade with R-multiple
    await _update_r_multiple(trade_id, r_multiple)

    # Update IC scores for each factor
    factor_scores = await _get_factor_scores(trade_id)
    regime = trade.get("regime") or "unknown"
    if factor_scores:
        from scoring.ic_tracker import update_ic_after_trade
        await update_ic_after_trade(
            trade_id=trade_id,
            symbol=trade["symbol"],
            direction=trade.get("direction", "neutral"),
            pnl=pnl,
            regime=regime,
            factor_scores=factor_scores,
        )

    # Generate lesson via Claude
    lesson = await _generate_lesson(trade, r_multiple, factor_scores)

    # Store in memory with embedding
    await _store_memory(trade, r_multiple, lesson, factor_scores)

    logger.info(f"Post-mortem complete for trade {trade_id}: R={r_multiple:.2f}x")


async def _generate_lesson(trade: dict, r_multiple: float, factors: dict) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    outcome = "WIN" if r_multiple > 0 else "LOSS"
    worked = [k for k, v in factors.items() if v > 5] if factors else []
    failed = [k for k, v in factors.items() if v < 5] if factors else []

    prompt = f"""Write a 2-sentence trading lesson from this closed options trade.

Symbol: {trade['symbol']}
Strategy: {trade.get('strategy')}
Direction: {trade.get('direction')}
Regime at entry: {trade.get('regime')}
Outcome: {outcome} | R-multiple: {r_multiple:.2f}x
Factors that fired: {worked}
Factors that failed to predict: {failed}

Lesson should be specific and actionable for future similar setups."""

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        return f"Trade {'won' if r_multiple > 0 else 'lost'} {abs(r_multiple):.2f}R in {trade.get('strategy')} setup."


async def _store_memory(trade: dict, r_multiple: float, lesson: str, factors: dict):
    """Store memory entry with embedding for RAG retrieval."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    # Generate embedding via Ollama
    embedding = await _get_embedding(lesson)

    worked = [k for k, v in factors.items() if v > 5] if factors else []
    failed = [k for k, v in factors.items() if v < 5] if factors else []

    async with AsyncSessionLocal() as session:
        embedding_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None
        await session.execute(text("""
            INSERT INTO memory_entries
                (trade_id, symbol, sector, regime, lesson, r_multiple,
                 factors_that_worked, factors_that_failed, embedding)
            SELECT :tid, :sym, s.sector, :regime, :lesson, :r_mult,
                   :worked, :failed, :emb::vector
            FROM stocks s WHERE s.symbol = :sym
            ON CONFLICT DO NOTHING
        """), {
            "tid": trade["id"], "sym": trade["symbol"],
            "regime": trade.get("regime", "unknown"),
            "lesson": lesson, "r_mult": r_multiple,
            "worked": worked, "failed": failed,
            "emb": embedding_str,
        })
        await session.commit()


async def _get_embedding(text_content: str) -> list[float] | None:
    """Get embedding from Ollama nomic-embed-text (free, local)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text_content},
            )
            data = resp.json()
            return data.get("embedding")
    except Exception as e:
        logger.debug(f"Embedding failed: {e}")
        return None


async def compact_memory():
    """
    Weekly compaction: Claude distills last 20 lessons → 3-5 durable principles.
    Stores compacted principles as a strategy journal entry so they can feed
    the Pending Review tab on the Strategy page.
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    import json

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT lesson, r_multiple, regime
            FROM memory_entries
            WHERE compacted = false
            ORDER BY created_at DESC
            LIMIT 20
        """))
        rows = result.fetchall()

    if len(rows) < 5:
        return  # Not enough data yet

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    lessons_str = "\n".join(f"- [R={r:.2f}x, {regime}] {lesson}" for lesson, r, regime in rows)
    win_count = sum(1 for _, r, _ in rows if r > 0)
    avg_r = sum(r for _, r, _ in rows) / len(rows)

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"""Distill these {len(rows)} trade lessons into 3-5 durable strategy principles.
Focus on patterns that repeat across multiple trades.
Win rate: {win_count}/{len(rows)} ({round(win_count/len(rows)*100)}%). Avg R: {avg_r:.2f}x.

{lessons_str}

Format each principle as: "In [regime/condition]: [actionable rule]"
Also end with one line: "PROPOSED_CHANGE: [one specific parameter or rule to adjust, if any]" """
            }]
        )
        principles = response.content[0].text

        # Extract proposed change if present
        lines = principles.split("\n")
        proposed = next((l.replace("PROPOSED_CHANGE:", "").strip() for l in lines if "PROPOSED_CHANGE:" in l), None)

        logger.info(f"Compacted memory: {principles[:200]}")

        async with AsyncSessionLocal() as session:
            # Store compacted principles as a strategy journal entry
            await session.execute(text("""
                INSERT INTO strategy_journal
                    (entry_type, content, proposed_change, trade_count, win_rate, avg_r, created_at)
                VALUES
                    ('weekly_compaction', :content, :proposed, :tc, :wr, :ar, NOW())
            """), {
                "content": principles,
                "proposed": proposed,
                "tc": len(rows),
                "wr": round(win_count / len(rows), 3),
                "ar": round(avg_r, 3),
            })

            # Mark lessons as compacted
            await session.execute(text("""
                UPDATE memory_entries SET compacted = true
                WHERE compacted = false AND created_at < NOW() - INTERVAL '7 days'
            """))
            await session.commit()

    except Exception as e:
        logger.error(f"Memory compaction failed: {e}")


async def _get_trade(trade_id: int) -> dict | None:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT id, symbol, strategy, direction, entry_price, exit_price,
                   realized_pnl, max_loss, contracts, expiry, status,
                   vol_regime, entry_iv_rank, entry_delta, stream
            FROM paper_trades WHERE id = :tid
        """), {"tid": trade_id})
        row = result.fetchone()

    if not row:
        return None
    keys = ["id", "symbol", "strategy", "direction", "entry_price", "exit_price",
            "realized_pnl", "max_loss", "contracts", "expiry", "status",
            "vol_regime", "entry_iv_rank", "entry_delta", "stream"]
    d = dict(zip(keys, row))
    # Normalize regime field — postmortem uses "regime" key
    d["regime"] = d.pop("vol_regime") or "unknown"
    return d


async def _update_r_multiple(trade_id: int, r_multiple: float):
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        await session.execute(text(
            "UPDATE paper_trades SET r_multiple = :r WHERE id = :tid"
        ), {"r": r_multiple, "tid": trade_id})
        await session.commit()


async def _get_factor_scores(trade_id: int) -> dict[str, float]:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT category, signal_value FROM trade_factors WHERE trade_id = :tid
        """), {"tid": trade_id})
        rows = result.fetchall()
    return {row[0]: float(row[1] or 5) for row in rows}
