"""IPO Halo Effect Scorer — boosts public comps when mega-IPOs file."""

from loguru import logger


async def get_halo_boost(symbol: str) -> float:
    """Returns score boost (0-10) based on IPO halo exposure."""
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT ihm.halo_score, ip.company_name, ip.status
                FROM ipo_halo_mappings ihm
                JOIN ipo_pipeline ip ON ip.id = ihm.ipo_id
                WHERE ihm.symbol = :sym
                  AND ip.status IN ('filed', 'roadshow', 'priced')
                ORDER BY ihm.halo_score DESC
                LIMIT 1
            """), {"sym": symbol})
            row = result.fetchone()

        if not row:
            return 0.0

        halo_score, company_name, status = row
        multiplier = {"filed": 0.8, "roadshow": 1.0, "priced": 1.2}.get(status, 0.8)
        return round(float(halo_score) * multiplier, 1)
    except Exception:
        return 0.0
