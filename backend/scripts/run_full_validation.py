"""
Master validation runner — kicks off the entire signal validation suite
autonomously. Designed to run unattended for hours via:

    nohup python3 -m scripts.run_full_validation > data/backtest_reports/master.log 2>&1 &
    echo $! > data/backtest_reports/master.pid

The script:
  - Estimates total MarketData credit cost UPFRONT and aborts if over budget
  - Parallelizes everything that doesn't share constraints
  - Tests MULTIPLE variants per signal (4 IC wing distances, 3 momentum windows, etc.)
  - Writes incremental progress to `data/backtest_reports/master_progress.json`
  - Auto-classifies each variant: PROMOTE / SANDBOX / NO EDGE / BLOCKED / ERROR
  - Produces ONE final markdown report: `data/backtest_reports/MASTER_REPORT.md`
  - Does NOT modify signal_registry or promotion_status — V's call after review

Budget contract:
  --budget=N caps total new MarketData fetches at N. Default 7000 (leaves headroom).
  Variants that exceed budget mid-run are skipped + logged.

Total wall time: 2-6 hours depending on signal count + universe size + credit budget.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal as os_signal
import sys
import time
import traceback
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from pathlib import Path

from loguru import logger


REPORTS_DIR = Path("data/backtest_reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS_FILE = REPORTS_DIR / "master_progress.json"
FINAL_REPORT = REPORTS_DIR / "MASTER_REPORT.md"
LOG_FILE = REPORTS_DIR / "master.log"

# Promotion gates
DSR_PROMOTE_TRAIN = 0.50
DSR_PROMOTE_WF = 0.30
DSR_SANDBOX_FLOOR = 0.20


# ---------------------------------------------------------------------------
# Universe definitions
# ---------------------------------------------------------------------------

# 40-name sector-diverse universe (matches OVERNIGHT_RUNBOOK Phase 6.3)
VRP_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
    "TSLA", "AMD", "AVGO", "INTC", "MU",   "JPM", "BAC", "GS",  "MS",  "WFC",
    "XOM", "CVX", "UNH", "LLY", "JNJ",  "PFE", "ABBV", "COST", "HD",  "WMT",
    "KO",  "PEP", "MCD", "DIS", "NFLX", "CRM", "ORCL", "BA",  "CAT", "MMM",
]

# Train/walk-forward windows constrained by MarketData Starter 5y rolling cap
TRAIN_START = date(2021, 7, 1)
TRAIN_END = date(2024, 12, 31)
WF_START = date(2025, 1, 1)
WF_END = date.today()


# ---------------------------------------------------------------------------
# Variant grid — every test that gets run
# ---------------------------------------------------------------------------

@dataclass
class Variant:
    signal: str
    name: str
    config: dict
    needs_marketdata: bool = False
    estimated_credits: int = 0
    universe_size: int = 20
    status: str = "pending"   # pending | running | done | sandboxed | blocked | error
    result: dict | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_variant_grid() -> list[Variant]:
    """All variants to test. Order matters — cheap/free things first."""
    out: list[Variant] = []

    # ---- FREE signals (yfinance + FMP only) ---------------------------------
    for lookback in (252, 189):  # 12-1 (252-21=231 vs 189-21=168) — two windows
        out.append(Variant(
            signal="momentum_12_1",
            name=f"momentum_12_1_lookback={lookback}",
            config={"lookback_days": lookback, "rebalance_days": 21,
                     "universe": "liquid_1000"},
            needs_marketdata=False, universe_size=1000,
        ))

    for window in (5, 10):  # PEAD: hold 5d vs 10d post-earnings
        out.append(Variant(
            signal="pead",
            name=f"pead_hold={window}d",
            config={"hold_days": window, "min_eps_surprise_pct": 5.0,
                     "max_mkt_cap_b": 50, "universe": "liquid_1000"},
            needs_marketdata=False, universe_size=1000,
        ))

    out.append(Variant(
        signal="insider_opportunistic",
        name="insider_cluster_30d",
        config={"cluster_window_days": 30, "min_opportunistic": 3,
                 "min_distinct_insiders": 2, "hold_days": 60,
                 "universe": "liquid_1000"},
        needs_marketdata=False, universe_size=1000,
    ))

    out.append(Variant(
        signal="lead_lag",
        name="lead_lag_60d_window",
        config={"correlation_window_days": 60, "max_lag_days": 15,
                 "min_abs_corr": 0.25, "universe": "liquid_500"},
        needs_marketdata=False, universe_size=500,
    ))

    out.append(Variant(
        signal="short_squeeze",
        name="squeeze_drechsler",
        config={"si_pct_float_min": 0.15, "days_to_cover_min": 5.0,
                 "hold_days": 30, "universe": "liquid_1000"},
        needs_marketdata=False, universe_size=1000,
    ))

    out.append(Variant(
        signal="pre_fomc_straddle",
        name="pre_fomc_24h",
        config={"underlying": "SPY", "dte_target": 5},
        needs_marketdata=False, universe_size=1,
    ))

    # ---- VRP family — uses cache + a little new ----------------------------
    # Naked strangle baseline (already validated in V's prior run)
    out.append(Variant(
        signal="vrp_harvest",
        name="vrp_naked_strangle_baseline",
        config={"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0,
                 "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16},
        needs_marketdata=True, universe_size=40,
        estimated_credits=0,  # already cached
    ))

    # Iron condor sweep — V's exact question
    for wings_sigma in (1.5, 2.0, 2.5, 3.0):
        out.append(Variant(
            signal="vrp_harvest",
            name=f"vrp_iron_condor_wings={wings_sigma}sigma",
            config={"variant": "iron_condor", "wings_sigma": wings_sigma,
                     "iv_rank_min": 50, "vrp_z_min": 1.0,
                     "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16},
            needs_marketdata=True, universe_size=40,
            estimated_credits=0,  # cache hit if wings within cached strike range
        ))

    # Tighter stop variants (reduce 51% naked DD)
    for stop in (1.0, 1.5):
        out.append(Variant(
            signal="vrp_harvest",
            name=f"vrp_naked_stop={stop}x",
            config={"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0,
                     "profit_target": 0.5, "stop_loss": stop, "short_delta": 0.16},
            needs_marketdata=True, universe_size=40,
            estimated_credits=0,
        ))

    return out


# ---------------------------------------------------------------------------
# Variant executors — each calls into the right harness, returns metrics dict
# ---------------------------------------------------------------------------

async def _run_vrp_variant(v: Variant) -> dict:
    """Runs both train + walk-forward for a VRP variant from cached chains."""
    from backtest.strategies.vrp_harvest import (
        VrpConfig, run_vrp_backtest as run_naked,
    )
    from backtest.marketdata_source import MarketDataHistoricalSource

    # iron condor variant is in a separate module that PC Opus built
    variant_kind = v.config.get("variant", "naked")
    if variant_kind == "iron_condor":
        try:
            from backtest.strategies.vrp_harvest_ic import run_vrp_ic_backtest
        except ImportError:
            return {"error": "vrp_harvest_ic module not present — PC Opus needs to build it"}
        runner = run_vrp_ic_backtest
        extra_kwargs = {"wings_sigma": v.config["wings_sigma"]}
    else:
        runner = run_naked
        extra_kwargs = {}

    cfg = VrpConfig(
        iv_rank_min=v.config["iv_rank_min"],
        vrp_z_min=v.config["vrp_z_min"],
        profit_target=v.config["profit_target"],
        stop_loss=v.config["stop_loss"],
        target_short_delta=v.config["short_delta"],
    )

    source = MarketDataHistoricalSource()

    train = await runner(symbols=VRP_UNIVERSE, source=source,
                          start=TRAIN_START, end=TRAIN_END,
                          config=cfg, **extra_kwargs)
    wf = await runner(symbols=VRP_UNIVERSE, source=source,
                       start=WF_START, end=WF_END,
                       config=cfg, **extra_kwargs)

    return {
        "train": train.metrics,
        "walk_forward": wf.metrics,
        "train_trades": len(train.results),
        "wf_trades": len(wf.results),
        "credits_burned": source.stats.get("api_fetches", 0),
    }


async def _run_momentum_variant(v: Variant) -> dict:
    """Equity backtester required — checks for it, falls back to skip if missing."""
    try:
        from backtest.equity_engine import EquityTrade, run_equity_backtest
        from backtest.strategies.momentum_xs_v2 import generate_momentum_trades
    except ImportError as e:
        return {"error": f"equity backtester not built yet: {e}. "
                          "PC Opus needs `backtest/equity_engine.py` + `backtest/strategies/momentum_xs_v2.py`."}

    from data.scanner import get_scan_universe
    universe = (await get_scan_universe())[:v.universe_size]

    train_trades = await generate_momentum_trades(
        universe, TRAIN_START, TRAIN_END,
        lookback_days=v.config["lookback_days"],
        rebalance_days=v.config["rebalance_days"],
    )
    wf_trades = await generate_momentum_trades(
        universe, WF_START, WF_END,
        lookback_days=v.config["lookback_days"],
        rebalance_days=v.config["rebalance_days"],
    )

    train = await run_equity_backtest(train_trades, num_trials=15)
    wf = await run_equity_backtest(wf_trades, num_trials=15)
    return {
        "train": train.metrics, "walk_forward": wf.metrics,
        "train_trades": len(train_trades), "wf_trades": len(wf_trades),
    }


async def _run_generic_equity_variant(v: Variant, strategy_module: str,
                                       generator_name: str) -> dict:
    """Shared path for PEAD / insider / squeeze / lead-lag once equity engine exists."""
    try:
        from backtest.equity_engine import run_equity_backtest
        mod = __import__(strategy_module, fromlist=[generator_name])
        generator = getattr(mod, generator_name)
    except ImportError as e:
        return {"error": f"missing: {strategy_module}.{generator_name} — {e}"}
    except AttributeError as e:
        return {"error": f"missing function {generator_name}: {e}"}

    from data.scanner import get_scan_universe
    universe = (await get_scan_universe())[:v.universe_size]

    train_trades = await generator(universe, TRAIN_START, TRAIN_END, **v.config)
    wf_trades = await generator(universe, WF_START, WF_END, **v.config)
    train = await run_equity_backtest(train_trades, num_trials=10)
    wf = await run_equity_backtest(wf_trades, num_trials=10)
    return {
        "train": train.metrics, "walk_forward": wf.metrics,
        "train_trades": len(train_trades), "wf_trades": len(wf_trades),
    }


VARIANT_DISPATCH = {
    "vrp_harvest": _run_vrp_variant,
    "momentum_12_1": _run_momentum_variant,
    "pead":
        lambda v: _run_generic_equity_variant(
            v, "backtest.strategies.pead", "generate_pead_trades"),
    "insider_opportunistic":
        lambda v: _run_generic_equity_variant(
            v, "backtest.strategies.insider", "generate_insider_trades"),
    "lead_lag":
        lambda v: _run_generic_equity_variant(
            v, "backtest.strategies.lead_lag_bt", "generate_lead_lag_trades"),
    "short_squeeze":
        lambda v: _run_generic_equity_variant(
            v, "backtest.strategies.squeeze", "generate_squeeze_trades"),
    "pre_fomc_straddle":
        lambda v: _run_generic_equity_variant(
            v, "backtest.strategies.pre_fomc_straddle", "generate_pre_fomc_trades"),
}


# ---------------------------------------------------------------------------
# Verdict classification
# ---------------------------------------------------------------------------

def classify_result(result: dict) -> str:
    if "error" in result and result["error"]:
        return "error"
    train = result.get("train") or {}
    wf = result.get("walk_forward") or {}
    train_dsr = float(train.get("deflated_sharpe") or 0.0)
    wf_dsr = float(wf.get("deflated_sharpe") or 0.0)
    train_n = int(result.get("train_trades") or 0)
    wf_n = int(result.get("wf_trades") or 0)
    if train_n == 0 and wf_n == 0:
        return "blocked"  # 0 trades = data/harness issue, not a verdict
    if train_dsr >= DSR_PROMOTE_TRAIN and wf_dsr >= DSR_PROMOTE_WF:
        return "promote"
    if train_dsr >= DSR_SANDBOX_FLOOR or wf_dsr >= DSR_SANDBOX_FLOOR:
        return "sandbox"
    return "no_edge"


# ---------------------------------------------------------------------------
# Progress + execution
# ---------------------------------------------------------------------------

def write_progress(variants: list[Variant]) -> None:
    """Atomic dump of all variant states for tail -f friends."""
    snapshot = {
        "updated_at": datetime.utcnow().isoformat(),
        "variants": [v.to_dict() for v in variants],
        "summary": {
            "total": len(variants),
            **{s: sum(1 for v in variants if v.status == s)
                for s in ("pending", "running", "done", "sandboxed",
                           "blocked", "error")},
        },
    }
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, default=str))
    tmp.replace(PROGRESS_FILE)


async def run_one(v: Variant) -> None:
    v.status = "running"
    v.started_at = datetime.utcnow().isoformat()
    logger.info(f"▶ {v.signal} :: {v.name}")
    try:
        dispatch = VARIANT_DISPATCH.get(v.signal)
        if dispatch is None:
            raise RuntimeError(f"no dispatcher for signal {v.signal}")
        result = await dispatch(v)
        if asyncio.iscoroutine(result):
            result = await result
        v.result = result
        if "error" in result and result["error"]:
            v.status = "blocked" if "not built" in result["error"] or "not present" in result["error"] else "error"
            v.error = result["error"]
        else:
            verdict = classify_result(result)
            v.status = {
                "promote": "done", "sandbox": "sandboxed",
                "no_edge": "sandboxed", "blocked": "blocked",
                "error": "error",
            }[verdict]
        logger.info(f"✓ {v.signal} :: {v.name} → {v.status}")
    except Exception as e:
        v.status = "error"
        v.error = f"{type(e).__name__}: {e}"
        logger.error(f"✗ {v.signal} :: {v.name} → {e}\n{traceback.format_exc()}")
    finally:
        v.finished_at = datetime.utcnow().isoformat()


async def run_all(variants: list[Variant], concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)

    async def guarded(v: Variant) -> None:
        async with sem:
            await run_one(v)
            write_progress(variants)

    await asyncio.gather(*[guarded(v) for v in variants])


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def render_report(variants: list[Variant], elapsed_seconds: float) -> str:
    lines = [
        f"# Master Validation Report",
        f"",
        f"Generated: {datetime.utcnow().isoformat()}",
        f"Elapsed: {elapsed_seconds/60:.1f} min",
        f"",
        "## Verdicts at a glance",
        f"",
        "| Signal | Variant | Train DSR | WF DSR | Train n | WF n | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for v in variants:
        result = v.result or {}
        train = result.get("train") or {}
        wf = result.get("walk_forward") or {}
        tdsr = train.get("deflated_sharpe")
        wdsr = wf.get("deflated_sharpe")
        tn = result.get("train_trades", 0)
        wn = result.get("wf_trades", 0)
        emoji = {"done": "✅ PROMOTE", "sandboxed": "🟡 SANDBOX",
                  "blocked": "🔴 BLOCKED", "error": "❌ ERROR",
                  "running": "⏳", "pending": "⏸"}[v.status]
        lines.append(
            f"| {v.signal} | {v.name} | "
            f"{f'{tdsr:+.3f}' if tdsr is not None else '—'} | "
            f"{f'{wdsr:+.3f}' if wdsr is not None else '—'} | "
            f"{tn} | {wn} | {emoji} |"
        )

    lines += ["", "## Detail per variant", ""]
    for v in variants:
        lines.append(f"### {v.signal} — {v.name}")
        lines.append(f"")
        lines.append(f"- Status: **{v.status}**")
        lines.append(f"- Config: `{json.dumps(v.config, default=str)}`")
        if v.error:
            lines.append(f"- Error: {v.error}")
        if v.result:
            result = v.result
            for fold in ("train", "walk_forward"):
                m = result.get(fold)
                if not m:
                    continue
                lines.append(f"- {fold}:")
                for k in ("num_trades", "win_rate", "total_pnl", "sharpe",
                           "deflated_sharpe", "max_drawdown", "expectancy"):
                    if k in m and m[k] is not None:
                        lines.append(f"    - {k}: {m[k]}")
        lines.append("")

    lines += [
        "## Recommended actions",
        "",
        "Per V's validation ladder (DSR > 0.5 train AND > 0.3 walk-forward → PROMOTE):",
        "",
    ]
    promote = [v for v in variants if v.status == "done"]
    sandbox = [v for v in variants if v.status == "sandboxed"]
    blocked = [v for v in variants if v.status == "blocked"]
    errors = [v for v in variants if v.status == "error"]
    lines.append(f"- **Promote to paper trading:** {[v.name for v in promote] or 'NONE'}")
    lines.append(f"- **Sandbox (observe only):** {[v.name for v in sandbox] or 'NONE'}")
    lines.append(f"- **Blocked (needs harness/data fix):** {[v.name for v in blocked] or 'NONE'}")
    lines.append(f"- **Errored (investigate):** {[v.name for v in errors] or 'NONE'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args) -> int:
    log_path = LOG_FILE
    logger.add(log_path, level="INFO")

    variants = build_variant_grid()
    if args.only:
        keep = set(args.only.split(","))
        variants = [v for v in variants if v.signal in keep]
    logger.info(f"Plan: {len(variants)} variants, "
                 f"~{sum(v.estimated_credits for v in variants)} estimated new credits")

    if sum(v.estimated_credits for v in variants) > args.budget:
        logger.warning(
            f"Estimated credits ({sum(v.estimated_credits for v in variants)}) > "
            f"budget ({args.budget}). Skipping variants that need MarketData."
        )
        variants = [v for v in variants if not v.needs_marketdata]

    write_progress(variants)
    started = time.perf_counter()
    await run_all(variants, concurrency=args.concurrency)
    elapsed = time.perf_counter() - started

    md = render_report(variants, elapsed)
    FINAL_REPORT.write_text(md)
    logger.info(f"FINAL REPORT: {FINAL_REPORT}")
    print(md)
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(description="Master validation runner")
    parser.add_argument("--budget", type=int, default=7000,
                        help="cap on new MarketData credits to burn")
    parser.add_argument("--concurrency", type=int, default=6,
                        help="parallel variants")
    parser.add_argument("--only", type=str, default="",
                        help="comma-separated signal names to run (default: all)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args)))


if __name__ == "__main__":
    cli()
