"""
Conviction calibration — is "conviction 85" actually an 85% trade?

Compares stated conviction at entry against realized win/loss outcomes:
  - Brier score: mean (conviction/100 − outcome)²; 0.25 = no better than coin-flip
    guessing 50%, lower is better.
  - Calibration buckets: realized win rate per conviction decile. A calibrated
    system shows win rates tracking the bucket midpoints.

Until enough closed trades accumulate (≥20), results are flagged low-sample.
"""

from loguru import logger

MIN_SAMPLE = 20


async def get_conviction_calibration() -> dict:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT conviction, realized_pnl
            FROM paper_trades
            WHERE status = 'closed'
              AND conviction IS NOT NULL
              AND realized_pnl IS NOT NULL
        """))
        rows = result.fetchall()

    n = len(rows)
    if n == 0:
        return {
            "num_closed_trades": 0,
            "brier_score": None,
            "buckets": [],
            "verdict": "No closed trades with recorded conviction yet — calibration unavailable.",
        }

    brier_sum = 0.0
    buckets: dict[int, dict] = {}
    for conviction, pnl in rows:
        p = float(conviction) / 100.0
        outcome = 1.0 if float(pnl) > 0 else 0.0
        brier_sum += (p - outcome) ** 2
        decile = min(9, int(float(conviction) // 10))
        b = buckets.setdefault(decile, {"trades": 0, "wins": 0})
        b["trades"] += 1
        b["wins"] += int(outcome)

    brier = brier_sum / n
    bucket_rows = [
        {
            "conviction_range": f"{d*10}-{d*10+9}",
            "implied_win_prob": (d * 10 + 5) / 100,
            "trades": b["trades"],
            "realized_win_rate": round(b["wins"] / b["trades"], 3),
        }
        for d, b in sorted(buckets.items())
    ]

    if n < MIN_SAMPLE:
        verdict = f"LOW SAMPLE ({n} trades, need {MIN_SAMPLE}+) — do not act on this yet."
    elif brier <= 0.20:
        verdict = f"Reasonably calibrated (Brier {brier:.3f})."
    elif brier <= 0.25:
        verdict = f"Barely better than coin-flip (Brier {brier:.3f}) — conviction numbers carry little information."
    else:
        verdict = (
            f"MISCALIBRATED (Brier {brier:.3f} > 0.25) — stated conviction is actively "
            "misleading; treat conviction as a rank, not a probability, until this improves."
        )

    return {
        "num_closed_trades": n,
        "brier_score": round(brier, 4),
        "buckets": bucket_rows,
        "verdict": verdict,
    }


async def log_calibration_snapshot() -> None:
    """Cheap post-close hook: log the current calibration state."""
    try:
        cal = await get_conviction_calibration()
        logger.info(
            f"Conviction calibration: n={cal['num_closed_trades']}, "
            f"Brier={cal['brier_score']}, verdict={cal['verdict']}"
        )
    except Exception as e:
        logger.debug(f"Calibration snapshot failed: {e}")
