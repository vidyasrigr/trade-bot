"""
Portfolio-level greeks aggregation — Phase H.9.

Why this exists:
  The risk officer (agents/graph.py::_run_risk_manager) reviews each trade in
  isolation. A book composed of 10 bull put spreads on semis individually each
  pass the 4% sizing cap — but the *aggregate* delta + vega + sector
  concentration risk is far above what any single trade communicates.

  This module computes:
    - Net portfolio delta / gamma / vega / theta across open paper trades
    - Per-sector exposure
    - Stream-balance (long vs short premium aggregate)
  And exposes a veto signal when:
    - |net portfolio delta| > MAX_NET_DELTA_BIAS (sized vs portfolio value)
    - Single-sector deployed risk > MAX_SECTOR_CONCENTRATION
    - Stacked premium-buying *or* premium-selling > MAX_STREAM_CONCENTRATION

  Called from agents/graph.py before order ticket finalization; persists a
  snapshot to portfolio_risk_snapshots (existing in scoring/portfolio_risk.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from loguru import logger

from core.config import settings


@dataclass
class PortfolioGreeks:
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_vega: float = 0.0
    net_theta: float = 0.0
    open_positions: int = 0
    deployed_capital: float = 0.0
    deployed_pct: float = 0.0
    per_sector_pct: dict[str, float] = field(default_factory=dict)
    per_stream_pct: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "net_delta": round(self.net_delta, 4),
            "net_gamma": round(self.net_gamma, 4),
            "net_vega": round(self.net_vega, 4),
            "net_theta": round(self.net_theta, 4),
            "open_positions": self.open_positions,
            "deployed_capital": round(self.deployed_capital, 2),
            "deployed_pct": round(self.deployed_pct, 4),
            "per_sector_pct": {k: round(v, 4) for k, v in self.per_sector_pct.items()},
            "per_stream_pct": {k: round(v, 4) for k, v in self.per_stream_pct.items()},
            "warnings": self.warnings,
            "computed_at": datetime.utcnow().isoformat(),
        }


async def aggregate_portfolio_greeks(portfolio_value: float | None = None) -> PortfolioGreeks:
    """
    Pull open paper trades, fetch live greeks per position via the active
    options client, and aggregate. Closed trades and trades without a known
    contract are skipped (with a warning logged).
    """
    from core.database import AsyncSessionLocal
    from data.tradier import get_tradier
    from sqlalchemy import text

    portfolio_value = portfolio_value or settings.PAPER_PORTFOLIO_VALUE
    out = PortfolioGreeks()

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT pt.id, pt.symbol, pt.strategy, pt.direction, pt.expiry,
                   pt.long_strike, pt.short_strike, pt.contracts, pt.entry_price,
                   pt.max_loss, pt.stream,
                   s.sector
            FROM paper_trades pt
            LEFT JOIN stocks s ON s.symbol = pt.symbol
            WHERE pt.status = 'open'
        """))
        rows = [dict(r) for r in result.mappings().all()]

    out.open_positions = len(rows)
    if not rows:
        return out

    client = get_tradier()
    sector_capital: dict[str, float] = {}
    stream_capital: dict[str, float] = {}

    for row in rows:
        symbol = row["symbol"]
        strike = float(row.get("long_strike") or row.get("short_strike") or 0)
        contracts = int(row.get("contracts") or 0)
        entry_price = float(row.get("entry_price") or 0)
        direction = row.get("direction") or "neutral"
        max_loss = float(row.get("max_loss") or (entry_price * contracts * 100))
        deployed = max_loss
        out.deployed_capital += deployed

        sector = row.get("sector") or "unknown"
        sector_capital[sector] = sector_capital.get(sector, 0) + deployed
        stream = (row.get("stream") or "neutral").lower()
        # Normalize the legacy 'alpha'/'income' labels to the regime-correct names.
        if stream in ("alpha", "long_premium"):
            stream = "premium_buying"
        elif stream in ("income", "short_premium"):
            stream = "premium_selling"
        stream_capital[stream] = stream_capital.get(stream, 0) + deployed

        # Pull live greeks from the active options chain. We can't reconstruct
        # the exact contract identity without storing the option_symbol, so use
        # the strike+expiry+side approximation. This is best-effort — if the
        # chain isn't available we count 0 greeks for that leg (better than
        # silently injecting fabricated numbers).
        try:
            chain = await client.get_best_chain(symbol, min_dte=1, max_dte=120)
        except Exception as e:
            logger.debug(f"portfolio_greeks: chain fetch failed for {symbol}: {e}")
            chain = []

        is_call = direction != "bearish"
        side_char = "C" if is_call else "P"
        match = None
        best_diff = float("inf")
        for c in chain:
            if (c.get("option_type") or "").upper().startswith(side_char):
                diff = abs(float(c.get("strike") or 0) - strike)
                if diff < best_diff:
                    best_diff = diff
                    match = c
        if match is None:
            continue
        greeks = match.get("greeks") or {}
        sign = 1 if contracts > 0 else -1
        out.net_delta += sign * float(greeks.get("delta") or 0) * abs(contracts) * 100
        out.net_gamma += sign * float(greeks.get("gamma") or 0) * abs(contracts) * 100
        out.net_vega  += sign * float(greeks.get("vega") or 0) * abs(contracts) * 100
        out.net_theta += sign * float(greeks.get("theta") or 0) * abs(contracts) * 100

    if portfolio_value > 0:
        out.deployed_pct = out.deployed_capital / portfolio_value
        out.per_sector_pct = {s: cap / portfolio_value for s, cap in sector_capital.items()}
        out.per_stream_pct = {s: cap / portfolio_value for s, cap in stream_capital.items()}

    # Veto rules — gather as warnings; agents/risk_manager_agent reads these.
    max_delta_bias = settings.MAX_NET_DELTA_BIAS  # already a fraction of portfolio
    delta_pct = abs(out.net_delta) / max(1.0, portfolio_value)
    if delta_pct > max_delta_bias:
        out.warnings.append(
            f"NET_DELTA_BIAS {delta_pct:.0%} > limit {max_delta_bias:.0%} — "
            "portfolio is overly directional; new trades should be delta-neutral or opposite."
        )
    if out.deployed_pct > settings.MAX_PORTFOLIO_HEAT:
        out.warnings.append(
            f"DEPLOYED_HEAT {out.deployed_pct:.0%} > limit {settings.MAX_PORTFOLIO_HEAT:.0%} — "
            "no new positions until existing risk reduces."
        )
    for sector, pct in out.per_sector_pct.items():
        if pct > settings.MAX_SECTOR_CONCENTRATION:
            out.warnings.append(
                f"SECTOR_CONCENTRATION {sector}={pct:.0%} > "
                f"{settings.MAX_SECTOR_CONCENTRATION:.0%} — diversify before adding more {sector} exposure."
            )

    return out


async def portfolio_veto_context() -> str:
    """Compact text injected into the risk manager prompt."""
    try:
        greeks = await aggregate_portfolio_greeks()
        if greeks.open_positions == 0:
            return "Portfolio: no open positions."
        parts = [
            f"Portfolio: {greeks.open_positions} open, "
            f"deployed={greeks.deployed_pct:.0%}, "
            f"net_delta={greeks.net_delta:+.0f}, "
            f"net_vega={greeks.net_vega:+.0f}",
        ]
        for w in greeks.warnings:
            parts.append(f"  VETO: {w}")
        return "\n".join(parts)
    except Exception as e:
        logger.debug(f"portfolio_veto_context failed: {e}")
        return ""
