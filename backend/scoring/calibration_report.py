"""
Monthly calibration report (P0 Stage 3.5).

"If 90-conviction trades only win 61%, the model is overconfident." This rolls up
predicted win-probability vs realized win rate (via v_calibration_buckets) plus a
Brier score, and flags overconfident deciles. Cheap (SQL aggregation), high value
later — locked in now so the cadence exists before months of paper data accrue.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from loguru import logger

REPORTS_DIR = Path(__file__).resolve().parents[2] / "data" / "reports"


async def generate_calibration_report(month: str | None = None) -> str | None:
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    month = month or date.today().strftime("%Y-%m")
    try:
        async with AsyncSessionLocal() as s:
            buckets = (await s.execute(text("SELECT * FROM v_calibration_buckets"))).mappings().all()
            rows = (await s.execute(text("""
                SELECT predicted_win_prob AS p,
                       CASE WHEN actual_outcome > 0 THEN 1.0 ELSE 0.0 END AS y
                FROM recommendations
                WHERE predicted_win_prob IS NOT NULL AND actual_outcome IS NOT NULL
            """))).fetchall()
    except Exception as e:
        logger.warning(f"calibration report skipped (db): {e}")
        return None

    brier = (sum((float(r[0]) - float(r[1])) ** 2 for r in rows) / len(rows)) if rows else None
    lines = [
        f"# Calibration report — {month}",
        "",
        f"Closed labeled recommendations: {len(rows)}",
        f"Brier score: {brier:.4f}" if brier is not None else "Brier score: n/a (no labels yet)",
        "",
        "| prob decile | n | avg predicted | realized win rate | gap (pred-real) |",
        "|---|---|---|---|---|",
    ]
    for b in buckets:
        lines.append(
            f"| {b['prob_decile']} | {b['n']} | {b['avg_predicted_prob']} | "
            f"{b['realized_win_rate']} | {b['calibration_gap']} |"
        )
    flagged = [b for b in buckets if (b["n"] or 0) >= 30 and abs(float(b["calibration_gap"] or 0)) > 0.15]
    if flagged:
        lines += ["", "## Overconfidence flags (>15pp off, n>=30)"]
        for b in flagged:
            lines.append(f"- decile {b['prob_decile']}: predicted {b['avg_predicted_prob']} "
                         f"vs realized {b['realized_win_rate']}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"calibration_{month}.md"
    path.write_text("\n".join(lines))
    logger.info(f"calibration report written: {path}")
    return str(path)
