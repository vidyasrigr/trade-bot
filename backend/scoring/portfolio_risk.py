"""
DETERMINISTIC portfolio risk checker.
Sector concentration, net delta, pairwise correlation — all rule-based.
Runs before any new position is approved.
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.config import settings


@dataclass
class PortfolioRiskCheck:
    ok: bool
    issues: list[str]
    warnings: list[str]
    sector_exposure: dict[str, float]
    net_delta: float
    heat_pct: float
    recommendation: str


async def check_new_position(
    symbol: str,
    sector: str,
    net_delta_contribution: float,
    capital_pct: float,
) -> PortfolioRiskCheck:
    """
    Evaluate whether adding a new position violates risk rules.
    Returns PortfolioRiskCheck with ok=False if any rule is violated.
    """
    issues = []
    warnings = []

    open_positions = await _get_open_positions()
    current_heat = sum(p["capital_pct"] for p in open_positions)
    sector_exposure = _compute_sector_exposure(open_positions)
    current_net_delta = sum(p.get("net_delta", 0) for p in open_positions)

    # Rule 1: max portfolio heat
    new_heat = current_heat + capital_pct
    if new_heat > settings.MAX_PORTFOLIO_HEAT:
        issues.append(
            f"Portfolio heat {round(current_heat*100,1)}% + new {round(capital_pct*100,1)}% "
            f"exceeds max {round(settings.MAX_PORTFOLIO_HEAT*100,0):.0f}%"
        )

    # Rule 2: sector concentration
    new_sector_pct = sector_exposure.get(sector, 0) + capital_pct
    if new_sector_pct > settings.MAX_SECTOR_CONCENTRATION:
        issues.append(
            f"Sector '{sector}' would be {round(new_sector_pct*100,1)}% — "
            f"exceeds max {round(settings.MAX_SECTOR_CONCENTRATION*100,0):.0f}%"
        )
    elif new_sector_pct > settings.MAX_SECTOR_CONCENTRATION * 0.8:
        warnings.append(f"Sector '{sector}' approaching limit: {round(new_sector_pct*100,1)}%")

    # Rule 3: net delta bias
    new_net_delta = current_net_delta + net_delta_contribution
    if abs(new_net_delta) > settings.MAX_NET_DELTA_BIAS:
        issues.append(
            f"Net delta {round(new_net_delta, 2)} would exceed max "
            f"±{settings.MAX_NET_DELTA_BIAS}"
        )

    # Rule 4: pairwise correlation (same sector = high correlation)
    correlated = [p for p in open_positions if p.get("sector") == sector]
    if len(correlated) >= 3:
        warnings.append(
            f"{len(correlated)} existing positions in sector '{sector}' — treated as correlated"
        )
        # Size new position as if it's an addition to existing cluster
        effective_size = capital_pct * (1 + len(correlated) * 0.3)
        if effective_size > settings.MAX_SECTOR_CONCENTRATION:
            issues.append(f"Effective sector exposure too high after correlation adjustment")

    ok = len(issues) == 0

    # Build recommendation
    if not ok:
        rec = f"BLOCKED: {'; '.join(issues[:2])}"
    elif warnings:
        rec = f"CAUTION: {'; '.join(warnings[:2])}"
    else:
        rec = f"APPROVED: heat={round(new_heat*100,1)}%, sector={round(new_sector_pct*100,1)}%"

    return PortfolioRiskCheck(
        ok=ok, issues=issues, warnings=warnings,
        sector_exposure={k: round(v, 3) for k, v in sector_exposure.items()},
        net_delta=round(new_net_delta, 3),
        heat_pct=round(new_heat, 3),
        recommendation=rec,
    )


async def get_current_heat() -> float:
    """Returns current % of capital deployed."""
    open_positions = await _get_open_positions()
    return sum(p.get("capital_pct", 0) for p in open_positions)


def _compute_sector_exposure(positions: list[dict]) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for p in positions:
        sector = p.get("sector", "unknown")
        exposure[sector] = exposure.get(sector, 0) + p.get("capital_pct", 0)
    return exposure


async def _get_open_positions() -> list[dict]:
    """Fetch open paper trades from DB and compute capital allocation."""
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT pt.symbol, pt.max_loss, pt.contracts, s.sector
                FROM paper_trades pt
                LEFT JOIN stocks s ON s.symbol = pt.symbol
                WHERE pt.status = 'open'
            """))
            rows = result.fetchall()

        positions = []
        for row in rows:
            positions.append({
                "symbol": row[0],
                "max_loss": float(row[1] or 0),
                "contracts": int(row[2] or 1),
                "sector": row[3] or "unknown",
                "capital_pct": float(row[1] or 0) * int(row[2] or 1) / 100_000,  # assume $100k account
                "net_delta": 0.0,  # TODO: fetch from Greeks when available
            })
        return positions
    except Exception as e:
        logger.debug(f"Could not fetch open positions: {e}")
        return []
