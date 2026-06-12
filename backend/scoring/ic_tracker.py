"""
Information Coefficient (IC) tracker.
After every closed trade: computes IC per {factor, regime}, halves weight if IC < 0.05.
Regime-tagged so bull-run IC doesn't mislead during bear markets.
"""

from loguru import logger


async def update_ic_after_trade(
    trade_id: int,
    symbol: str,
    direction: str,
    pnl: float,
    regime: str,
    factor_scores: dict[str, float],
):
    """
    Called by postmortem.py when a trade closes.
    Computes per-factor IC update and persists to DB.
    IC = correlation between factor signal direction and actual outcome direction.
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    outcome = 1 if pnl > 0 else -1

    async with AsyncSessionLocal() as session:
        for category, score in factor_scores.items():
            factor_direction = 1 if score > 5 else -1  # score > 5 = bullish signal
            ic_contribution = factor_direction * outcome

            # Fetch current IC record
            result = await session.execute(text("""
                SELECT ic_score, sample_count, current_weight_multiplier, history
                FROM factor_ic_scores
                WHERE category = :cat AND regime = :regime
            """), {"cat": category, "regime": regime})
            row = result.fetchone()

            if row:
                ic_score, count, multiplier, history = row
                count += 1
                # Rolling IC: exponential moving average
                alpha = 0.1  # smoothing factor
                new_ic = (1 - alpha) * float(ic_score) + alpha * ic_contribution
                new_ic = round(new_ic, 6)

                import orjson
                hist = orjson.loads(history) if isinstance(history, str) else (history or [])
                hist.append({"count": count, "ic": new_ic, "trade_id": trade_id})
                hist = hist[-100:]  # keep last 100 entries

                # Auto-halve weight if IC < 0.05 after 100+ trades
                new_multiplier = float(multiplier)
                halved_at = None
                if count >= 100 and new_ic < 0.05:
                    new_multiplier = max(0.25, new_multiplier * 0.5)
                    halved_at = "NOW()"
                    logger.info(f"IC too low for {category}/{regime}: halving weight to {new_multiplier}")

                await session.execute(text("""
                    UPDATE factor_ic_scores
                    SET ic_score = :ic, sample_count = :count,
                        current_weight_multiplier = :mult,
                        history = :history::jsonb,
                        last_halved_at = CASE WHEN :halved THEN NOW() ELSE last_halved_at END,
                        updated_at = NOW()
                    WHERE category = :cat AND regime = :regime
                """), {
                    "ic": new_ic, "count": count, "mult": new_multiplier,
                    "history": orjson.dumps(hist).decode(),
                    "halved": new_multiplier != float(multiplier),
                    "cat": category, "regime": regime,
                })

        await session.commit()


async def get_weight_multipliers(regime: str) -> dict[str, float]:
    """Returns current weight multipliers per category for the given regime."""
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT category, current_weight_multiplier
            FROM factor_ic_scores
            WHERE regime = :regime OR regime = 'all'
            ORDER BY regime DESC  -- regime-specific takes precedence over 'all'
        """), {"regime": regime})
        rows = result.fetchall()

    multipliers = {}
    for cat, mult in rows:
        if cat not in multipliers:  # regime-specific overrides 'all'
            multipliers[cat] = float(mult)
    return multipliers
