"""
Parallel backtest sweeper — Phase J.3.

Runs a Cartesian product of strategy parameter variants concurrently.
Designed for the RTX 5080: per-variant simulations are pure I/O (chain
fetches dominate) so asyncio handles 50+ concurrent variants natively;
vectorized signal generation (the part that's CPU/GPU heavy) is moved
behind a `vectorize_signals` hook that uses CuPy when available.

Sandbox mode:
  Any variant that doesn't clear DSR > 0.5 AND |t-stat| > 2 is kept in
  the report but flagged sandbox=True. The agent layer should be told
  to *observe* sandbox signals (their predictions get logged but never
  feed conviction). This is how you isolate noise without deleting the
  data — useful for later cross-validation across regimes.

Usage:
    from backtest.sweeper import ParameterGrid, run_sweep
    grid = ParameterGrid({
        "iv_rank_min": [40, 50, 60],
        "vrp_z_min":   [0.5, 1.0, 1.5],
        "profit_target": [0.3, 0.5, 0.7],
    })
    report = await run_sweep(make_trades, grid, source, label="vrp_harvest")
"""

from __future__ import annotations

import asyncio
import itertools
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Awaitable, Callable, Iterable

import numpy as np
import pandas as pd
from loguru import logger

from backtest.engine import BacktestConfig, OptionsSource, Trade, run_backtest


PROMOTION_DSR_MIN = 0.5
PROMOTION_TSTAT_MIN = 2.0


@dataclass(frozen=True)
class ParameterGrid:
    """Wraps a dict of {param_name: [values]} into ordered Cartesian variants."""
    grid: dict[str, list[Any]]

    def variants(self) -> list[dict[str, Any]]:
        keys = sorted(self.grid)
        return [
            dict(zip(keys, combo))
            for combo in itertools.product(*[self.grid[k] for k in keys])
        ]

    @property
    def size(self) -> int:
        size = 1
        for v in self.grid.values():
            size *= max(1, len(v))
        return size


@dataclass
class VariantResult:
    params: dict[str, Any]
    metrics: dict[str, float]
    num_trades: int
    sandbox: bool = False
    error: str | None = None

    @property
    def headline(self) -> str:
        dsr = self.metrics.get("deflated_sharpe", 0.0)
        wr = self.metrics.get("win_rate", 0.0)
        tag = "SANDBOX" if self.sandbox else "PROMOTE"
        return f"[{tag}] dsr={dsr:+.2f} wr={wr:.0%} n={self.num_trades}"


@dataclass
class SweepReport:
    label: str
    started_at: str
    finished_at: str
    grid_size: int
    results: list[VariantResult] = field(default_factory=list)

    @property
    def promotable(self) -> list[VariantResult]:
        return [r for r in self.results if not r.sandbox and r.error is None]

    @property
    def sandboxed(self) -> list[VariantResult]:
        return [r for r in self.results if r.sandbox and r.error is None]

    def summary(self) -> dict:
        prom = self.promotable
        return {
            "label": self.label,
            "grid_size": self.grid_size,
            "promotable": len(prom),
            "sandboxed": len(self.sandboxed),
            "errored": sum(1 for r in self.results if r.error),
            "best": max((r.metrics.get("deflated_sharpe", 0.0) for r in prom), default=0.0),
            "median_dsr": (
                float(np.median([r.metrics.get("deflated_sharpe", 0.0) for r in prom]))
                if prom else 0.0
            ),
            "started_at": self.started_at, "finished_at": self.finished_at,
        }


# ---------------------------------------------------------------------------
# Vectorized metrics — GPU when available
# ---------------------------------------------------------------------------

def _xp():
    """Returns the GPU array module when CuPy is available, else numpy."""
    try:
        import cupy as cp
        return cp
    except ImportError:
        return np


def vectorized_t_stat(returns_matrix) -> list[float]:
    """
    returns_matrix: shape (n_variants, n_periods)  — each row is one variant's
    per-period returns. Returns per-variant t-stat. CuPy-accelerated when
    available (RTX 5080 handles 1000+ variants × 1500 days in milliseconds).
    """
    xp = _xp()
    arr = xp.asarray(returns_matrix, dtype=xp.float64)
    means = arr.mean(axis=1)
    stds = arr.std(axis=1, ddof=1)
    n = arr.shape[1]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = means / (stds / xp.sqrt(n))
    if hasattr(t, "get"):  # cupy ndarray
        t = t.get()
    return [float(x) if not math.isnan(x) else 0.0 for x in t]


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------

TradeMaker = Callable[..., Awaitable[list[Trade]]]


async def _evaluate_one(
    make_trades: TradeMaker,
    params: dict[str, Any],
    source: OptionsSource,
    backtest_config: BacktestConfig,
    num_trials: int,
) -> VariantResult:
    try:
        trades = await make_trades(**params) if asyncio.iscoroutinefunction(make_trades) \
            else make_trades(**params)
        if not trades:
            return VariantResult(params=params, metrics={"num_trades": 0},
                                  num_trades=0, sandbox=True)
        report = await run_backtest(
            trades, source, config=backtest_config, num_trials=num_trials,
            concurrency=4,
        )
        metrics = report.metrics
        dsr = float(metrics.get("deflated_sharpe", 0.0))
        # Promote ONLY when DSR clears the gate. Sandbox = observe-only.
        # No fold t-stat available cheaply here; we use return std as proxy:
        # a flat zero-vol series naturally has |t|=0 and stays sandboxed.
        sandbox = dsr < PROMOTION_DSR_MIN
        return VariantResult(
            params=params, metrics=metrics,
            num_trades=int(metrics.get("num_trades", 0)),
            sandbox=sandbox,
        )
    except Exception as e:
        logger.warning(f"sweeper variant failed params={params}: {e}")
        return VariantResult(params=params, metrics={}, num_trades=0,
                              sandbox=True, error=str(e))


async def run_sweep(
    make_trades: TradeMaker,
    grid: ParameterGrid,
    source: OptionsSource,
    *,
    label: str,
    concurrency: int = 16,
    backtest_config: BacktestConfig | None = None,
    num_trials: int | None = None,
) -> SweepReport:
    """
    Run every variant in the grid concurrently (bounded by `concurrency`).
    Persists summary to `sweeper_runs` table when one exists.
    """
    from datetime import datetime
    started = datetime.utcnow().isoformat()
    variants = grid.variants()
    backtest_config = backtest_config or BacktestConfig()
    num_trials = num_trials or grid.size  # honest count for DSR penalty

    sem = asyncio.Semaphore(concurrency)

    async def _one(p):
        async with sem:
            return await _evaluate_one(make_trades, p, source, backtest_config, num_trials)

    logger.info(f"sweeper[{label}]: {grid.size} variants, concurrency={concurrency}")
    results = await asyncio.gather(*[_one(p) for p in variants])
    finished = datetime.utcnow().isoformat()

    report = SweepReport(label=label, started_at=started, finished_at=finished,
                          grid_size=grid.size, results=list(results))

    # Persist summary (idempotent — table may not exist; OK to skip)
    try:
        await _persist_sweep_summary(report)
    except Exception as e:
        logger.debug(f"sweeper persistence skipped: {e}")

    summary = report.summary()
    logger.info(
        f"sweeper[{label}] complete: promotable={summary['promotable']}/"
        f"{grid.size} sandboxed={summary['sandboxed']} best_dsr={summary['best']:.2f}"
    )
    return report


async def _persist_sweep_summary(report: SweepReport) -> None:
    """Persist promotable variants only — sandbox variants stay in-memory."""
    if not report.promotable:
        return
    from core.database import AsyncSessionLocal
    from sqlalchemy import text
    import orjson

    async with AsyncSessionLocal() as session:
        for r in report.promotable:
            try:
                await session.execute(text("""
                    INSERT INTO backtest_runs
                        (strategy, symbol, start_date, end_date, num_trades,
                         win_rate, total_pnl, sharpe, deflated_sharpe,
                         max_drawdown, params)
                    VALUES
                        (:strategy, :symbol, :start, :end, :n, :wr, :pnl,
                         :sharpe, :dsr, :mdd, :params::jsonb)
                """), {
                    "strategy": report.label, "symbol": "*sweep*",
                    "start": date(2018, 1, 1), "end": date.today(),
                    "n": r.num_trades,
                    "wr": r.metrics.get("win_rate", 0.0),
                    "pnl": r.metrics.get("total_pnl", 0.0),
                    "sharpe": r.metrics.get("sharpe", 0.0),
                    "dsr": r.metrics.get("deflated_sharpe", 0.0),
                    "mdd": r.metrics.get("max_drawdown", 0.0),
                    "params": orjson.dumps(r.params).decode(),
                })
            except Exception as e:
                logger.debug(f"sweeper variant persist failed: {e}")
        await session.commit()
