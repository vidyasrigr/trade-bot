"""
Information Coefficient (IC) tracker — Phase F.2 rewrite.

After every closed trade, update per-(category, regime) IC. The previous
implementation halved a category's weight only after 100 trades per cell AND
an EWMA-IC below 0.05. With 20 categories × 4 regimes = 80 cells, that gate
required ~8,000 trades to even *start* converging.

New rules:
  - EWMA on the last 30 trades per cell (alpha ≈ 0.10) instead of an infinite tail
  - Hierarchical pooling: regime-specific IC is shrunk toward the regime='all'
    baseline using effective sample size n_eff = n / (1 + autocorr_proxy)
  - Halve weight on |t-stat| > 2 AND smoothed IC < 0.02 (with t-stat replacing
    the fixed 100-trade gate)
"""

import math
from loguru import logger


HISTORY_WINDOW = 30      # EWMA over last N updates per cell
EWMA_ALPHA = 0.10        # smoothing
T_STAT_FLOOR = 2.0       # |t-stat| above which we trust the demotion signal
IC_DEMOTION = 0.02       # demote when smoothed IC drops below this
WEIGHT_FLOOR = 0.25      # never below this multiplier
SHRINKAGE_K = 5          # pseudo-sample weight for the pooling prior


def _ewma_update(prev: float, sample: int, alpha: float = EWMA_ALPHA) -> float:
    return (1 - alpha) * prev + alpha * sample


def _t_stat(ic: float, std: float, n: int) -> float:
    if std <= 0 or n <= 1:
        return 0.0
    return ic / (std / math.sqrt(n))


def _pool_with_baseline(per_regime_ic: float, baseline_ic: float, n_eff: int) -> float:
    """
    Empirical-Bayes shrinkage: weighted average of the regime-specific IC and
    the cross-regime baseline (Markov-stationary-weighted when available).
    Higher n_eff trusts the regime-specific number.
    """
    weight_regime = n_eff / (n_eff + SHRINKAGE_K)
    return weight_regime * per_regime_ic + (1 - weight_regime) * baseline_ic


async def _build_pooling_baselines(session, categories: list[str]) -> dict[str, float]:
    """
    For each category, build a single 'expected IC across regimes' baseline:
      baseline_c = Σ_r stationary(r) * IC(c, r)
    using the Markov stationary distribution from regime_forecasts (scope=market).
    Falls back to the regime='all' row (or 0.0) when the Markov model isn't ready.
    """
    from sqlalchemy import text

    baselines: dict[str, float] = {}

    # 1. Pull the latest stationary distribution from the market Markov model
    try:
        result = await session.execute(text("""
            SELECT stationary
            FROM regime_forecasts
            WHERE scope = 'market'
            ORDER BY as_of_date DESC
            LIMIT 1
        """))
        row = result.mappings().first()
        stationary = dict(row["stationary"]) if row and row["stationary"] else {}
    except Exception:
        stationary = {}

    # 2. Stationary-weighted baseline (preferred path)
    if stationary:
        result = await session.execute(text("""
            SELECT category, regime, ic_score
            FROM factor_ic_scores
            WHERE category = ANY (:cats) AND regime <> 'all'
        """), {"cats": categories})
        by_cat: dict[str, dict[str, float]] = {}
        for cat, reg, ic in result.fetchall():
            by_cat.setdefault(cat, {})[reg] = float(ic or 0.0)
        for cat in categories:
            regime_ics = by_cat.get(cat, {})
            if regime_ics:
                weighted = sum(
                    stationary.get(reg, 0.0) * regime_ics.get(reg, 0.0)
                    for reg in stationary
                )
                # Re-normalize when not every regime has an IC row yet
                weight_sum = sum(
                    stationary.get(reg, 0.0)
                    for reg in stationary if reg in regime_ics
                )
                if weight_sum > 0:
                    baselines[cat] = weighted / weight_sum

    # 3. Fall back to the flat regime='all' row for categories we didn't fill
    missing = [c for c in categories if c not in baselines]
    if missing:
        result = await session.execute(text("""
            SELECT category, ic_score
            FROM factor_ic_scores
            WHERE regime = 'all' AND category = ANY (:cats)
        """), {"cats": missing})
        for cat, ic in result.fetchall():
            baselines[cat] = float(ic or 0.0)

    # 4. Final fallback for anything still missing
    for cat in categories:
        baselines.setdefault(cat, 0.0)
    return baselines


async def update_ic_after_trade(
    trade_id: int,
    symbol: str,
    direction: str,
    pnl: float,
    regime: str,
    factor_scores: dict[str, float],
):
    """
    Called by postmortem.py when a trade closes. EWMA-smooths IC per (factor,
    regime), then pools toward (factor, regime='all') so cells with little
    data lean on the cross-regime baseline rather than overfitting.
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    outcome = 1 if pnl > 0 else -1

    async with AsyncSessionLocal() as session:
        # Pre-load per-category baselines so we can pool every cell in one pass.
        # Baseline = weighted average of cross-regime ICs using the Markov
        # stationary distribution as weights (Phase G.2). Falls back to the
        # flat regime='all' row when no forecast exists yet.
        baselines = await _build_pooling_baselines(session, list(factor_scores.keys()))

        for category, score in factor_scores.items():
            factor_direction = 1 if score > 5 else -1
            ic_contribution = factor_direction * outcome

            # Fetch / initialize the cell
            row_res = await session.execute(text("""
                SELECT ic_score, sample_count, current_weight_multiplier, history,
                       signal_status
                FROM factor_ic_scores
                WHERE category = :cat AND regime = :regime
            """), {"cat": category, "regime": regime})
            row = row_res.fetchone()
            if row is None:
                await session.execute(text("""
                    INSERT INTO factor_ic_scores
                        (category, regime, ic_score, sample_count,
                         current_weight_multiplier, history, signal_status)
                    VALUES
                        (:c, :r, 0, 0, 1.0, '[]'::jsonb, 'proposed')
                    ON CONFLICT (category, regime) DO NOTHING
                """), {"c": category, "r": regime})
                ic_score, count, multiplier, history, status = 0.0, 0, 1.0, [], "proposed"
            else:
                ic_score, count, multiplier, history, status = row
                if isinstance(history, str):
                    import orjson
                    history = orjson.loads(history) or []
                history = list(history or [])

            count += 1
            ewma_ic = round(_ewma_update(float(ic_score), ic_contribution), 6)

            # Window of recent contributions for the std/t-stat estimate
            history.append({
                "count": count, "ic": ewma_ic, "trade_id": trade_id,
                "contribution": ic_contribution,
            })
            history = history[-HISTORY_WINDOW * 2:]
            recent = [h["contribution"] for h in history[-HISTORY_WINDOW:]
                       if "contribution" in h]
            n_recent = len(recent) or 1
            mean = sum(recent) / n_recent if recent else ewma_ic
            var = sum((x - mean) ** 2 for x in recent) / n_recent if recent else 0.0
            std = math.sqrt(var) if var > 0 else 0.0
            t_stat = _t_stat(mean, std, n_recent)

            # Hierarchical pooling toward regime='all' (unless THIS row IS the baseline)
            if regime != "all":
                pooled_ic = _pool_with_baseline(ewma_ic, baselines.get(category, ewma_ic), n_recent)
            else:
                pooled_ic = ewma_ic

            # Demotion gate — fires when smoothed IC is meaningfully below floor
            # with enough samples that the t-stat is trustworthy.
            new_multiplier = float(multiplier)
            if abs(t_stat) > T_STAT_FLOOR and pooled_ic < IC_DEMOTION:
                new_multiplier = max(WEIGHT_FLOOR, float(multiplier) * 0.5)
                logger.info(
                    f"IC tracker[{category}/{regime}]: IC={pooled_ic:.3f} t={t_stat:+.2f} → "
                    f"halve weight {multiplier:.2f} → {new_multiplier:.2f}"
                )

            import orjson
            await session.execute(text("""
                UPDATE factor_ic_scores
                SET ic_score = :ic, sample_count = :count,
                    current_weight_multiplier = :mult,
                    history = :history::jsonb,
                    last_halved_at = CASE WHEN :halved THEN NOW() ELSE last_halved_at END,
                    updated_at = NOW()
                WHERE category = :cat AND regime = :regime
            """), {
                "ic": pooled_ic, "count": count, "mult": new_multiplier,
                "history": orjson.dumps(history).decode(),
                "halved": new_multiplier != float(multiplier),
                "cat": category, "regime": regime,
            })

            # Evaluate promotion ladder side-effect (idempotent within a state)
            try:
                from scoring.promotion import evaluate_transitions
                await evaluate_transitions(category, regime)
            except Exception as e:
                logger.debug(f"promotion check skipped for {category}/{regime}: {e}")

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

    multipliers: dict[str, float] = {}
    for cat, mult in rows:
        if cat not in multipliers:
            multipliers[cat] = float(mult)
    return multipliers
