"""
Cross-sectional ranking — rank Tier-1 signals across the universe nightly.

Why: per-symbol absolute thresholds (`iv_hv_ratio > 1.3` → sell premium) are
blind to regime. A 1.3 IV/HV in low-vol 2017 is genuinely rich; the same 1.3 in
March 2020 is cheap. Cross-sectional ranks fix this — act on the tails of the
universe distribution, not arbitrary cut-offs.

Public API:
  rank_values(values: dict[symbol, value]) -> dict[symbol, {value, z, pct, decile}]
  persist_ranks(signal_type, ranks, as_of_date, session) -> int (rows written)
  load_latest_ranks(symbol, signal_types, session) -> dict[signal_type, percentile]

The nightly orchestrator lives in analysis/cross_section_job.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from loguru import logger


@dataclass
class Rank:
    value: float
    z_score: float
    percentile: float
    decile: int


def rank_values(values: dict[str, float]) -> dict[str, Rank]:
    """
    Convert {symbol: raw_value} -> {symbol: Rank}. Drops NaN/inf.
    Percentile = (rank - 1) / (n - 1) in [0, 1]. Decile = floor(percentile * 10), capped at 9.
    """
    clean = {s: float(v) for s, v in values.items()
             if v is not None and math.isfinite(float(v))}
    n = len(clean)
    if n == 0:
        return {}
    if n == 1:
        s, v = next(iter(clean.items()))
        return {s: Rank(value=v, z_score=0.0, percentile=0.5, decile=4)}

    sorted_items = sorted(clean.items(), key=lambda kv: kv[1])
    mean = sum(clean.values()) / n
    var = sum((v - mean) ** 2 for v in clean.values()) / n
    std = math.sqrt(var) if var > 0 else 1.0

    out: dict[str, Rank] = {}
    for ordinal, (sym, val) in enumerate(sorted_items):
        pct = ordinal / (n - 1)
        z = (val - mean) / std if std > 0 else 0.0
        decile = min(9, int(pct * 10))
        out[sym] = Rank(value=val, z_score=z, percentile=pct, decile=decile)
    return out


async def persist_ranks(
    signal_type: str,
    ranks: dict[str, Rank],
    as_of_date: date,
    session,
) -> int:
    """Upsert ranks for one signal_type into signal_ranks. Returns row count."""
    if not ranks:
        return 0
    from sqlalchemy import text

    rows = [
        {
            "symbol": s, "signal_type": signal_type,
            "value": r.value, "z_score": r.z_score,
            "percentile": r.percentile, "decile": r.decile,
            "as_of_date": as_of_date,
        }
        for s, r in ranks.items()
    ]
    await session.execute(text("""
        INSERT INTO signal_ranks
            (symbol, signal_type, value, z_score, percentile, decile, as_of_date)
        VALUES
            (:symbol, :signal_type, :value, :z_score, :percentile, :decile, :as_of_date)
        ON CONFLICT (symbol, signal_type, as_of_date) DO UPDATE SET
            value = EXCLUDED.value,
            z_score = EXCLUDED.z_score,
            percentile = EXCLUDED.percentile,
            decile = EXCLUDED.decile
    """), rows)
    await session.commit()
    logger.info(f"cross_section: persisted {len(rows)} ranks for {signal_type} on {as_of_date}")
    return len(rows)


async def load_latest_ranks(
    symbol: str,
    signal_types: Iterable[str] | None = None,
    session=None,
) -> dict[str, dict]:
    """
    {signal_type: {value, percentile, z_score, decile, as_of_date}} for a symbol
    using the most recent as_of_date per signal_type. Empty dict on any error.
    """
    if session is None:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await load_latest_ranks(symbol, signal_types, s)

    from sqlalchemy import text
    try:
        params: dict = {"symbol": symbol}
        type_clause = ""
        if signal_types is not None:
            types = list(signal_types)
            if not types:
                return {}
            placeholders = ", ".join(f":t{i}" for i in range(len(types)))
            type_clause = f"AND signal_type IN ({placeholders})"
            for i, t in enumerate(types):
                params[f"t{i}"] = t

        result = await session.execute(text(f"""
            SELECT DISTINCT ON (signal_type)
                signal_type, value, z_score, percentile, decile, as_of_date
            FROM signal_ranks
            WHERE symbol = :symbol {type_clause}
            ORDER BY signal_type, as_of_date DESC
        """), params)
        rows = result.mappings().all()
    except Exception as e:
        logger.debug(f"load_latest_ranks failed for {symbol}: {e}")
        return {}

    return {
        r["signal_type"]: {
            "value": float(r["value"]),
            "z_score": float(r["z_score"]) if r["z_score"] is not None else None,
            "percentile": float(r["percentile"]),
            "decile": int(r["decile"]),
            "as_of_date": r["as_of_date"].isoformat() if r["as_of_date"] else None,
        }
        for r in rows
    }


def format_rank_context(ranks: dict[str, dict]) -> str:
    """Compact text block injected into the trader's prompt — one line per signal."""
    if not ranks:
        return ""
    lines = ["Cross-sectional ranks (universe percentile, 0.0=bottom, 1.0=top):"]
    for sig_type, r in sorted(ranks.items()):
        lines.append(
            f"  {sig_type}: {r['value']:+.3f} | pct={r['percentile']:.2f} | "
            f"decile={r['decile']} | z={r['z_score']:+.2f}"
            if r.get("z_score") is not None
            else f"  {sig_type}: {r['value']:+.3f} | pct={r['percentile']:.2f} | decile={r['decile']}"
        )
    return "\n".join(lines)
