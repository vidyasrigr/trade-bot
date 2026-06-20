"""
0619.3 Track B — FULL SWEEP. One harness, identical methodology (MTM, costs, train/WF,
SANDBOX-cap) so every signal verdict is comparable — the incumbent baseline the GPT-18
research sweep (0619.2) must beat.

Sections:
  DEPTH (leads first, per V): momentum neighborhood x ADV multi-slice; options XS family.
  BREADTH: equity adapters + primitives (added as built); FMP-backed (added as built).

Writes incrementally after each variant:
  data/backtest_reports/FULL_SWEEP_2026-06-20.md
  data/backtest_reports/full_sweep_progress.json   (trackers ingest this)

Labels (never NO_EDGE when data-gated): CACHE_LIMITED (options, 169-name chain cache),
FUNDAMENTALS_PENDING, CHAINS_LIMITED (term structure). Everything SANDBOX-capped
(survivorship) until a PIT universe exists.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from pathlib import Path

from backtest.equity_engine import run_equity_backtest
from backtest.strategies.momentum_xs_v2 import generate_momentum_trades, _close_panel
from backtest.strategies.skew_xs import generate_skew_trades
from backtest.strategies.options_xs import (
    generate_vrp_z_trades, generate_vrp_level_trades,
    generate_iv_cp_spread_trades, generate_iv_term_slope_trades,
)
from backtest.strategies import equity_xs
from backtest.liquid_universe import liquid_top
from backtest.marketdata_source import DEFAULT_CACHE_ROOT

TRAIN = (date(2021, 7, 1), date(2024, 12, 31))
WF = (date(2025, 1, 1), date(2026, 6, 30))
REPORTS = Path(__file__).resolve().parents[2] / "data" / "backtest_reports"

_ROWS: list[dict] = []


def _load_existing():
    """Resume: load prior rows from the progress json so sections append, not overwrite."""
    p = REPORTS / "full_sweep_progress.json"
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text())
        for v in data.get("variants", []):
            res = v.get("result", {})
            tr, wf = res.get("train", {}), res.get("walk_forward", {})
            _ROWS.append({
                "signal": v["signal"], "name": v["name"],
                "n_tr": tr.get("num_trades", 0), "n_wf": wf.get("num_trades", 0),
                "train_dsr": tr.get("deflated_sharpe"), "wf_dsr": wf.get("deflated_sharpe"),
                "train_dd": tr.get("max_drawdown"), "wf_dd": wf.get("max_drawdown"),
                "verdict": v.get("verdict", v.get("status", "")), "label": v.get("label", ""),
                "result": res,
            })
    except Exception:
        pass


def _seen(name: str) -> bool:
    return any(r["name"] == name for r in _ROWS)


def _chain_universe() -> list[str]:
    return sorted(d for d in os.listdir(DEFAULT_CACHE_ROOT)
                  if (DEFAULT_CACHE_ROOT / d).is_dir() and not d.startswith("_"))


def _verdict(tr, wf, dd, label: str) -> str:
    passes = (tr or 0) >= 0.50 and (wf or 0) >= 0.30 and (dd or 1) < 0.25
    tag = f" [{label}]" if label else ""
    if passes:
        return "SANDBOX(survivorship-capped)" + tag
    if (dd or 0) >= 0.25 and (wf or 0) >= 0.30:
        return "SANDBOX(DD>25%)" + tag
    if (wf or 0) >= 0.30 or (tr or 0) >= 0.50:
        return "SANDBOX(partial)" + tag
    return "NO_EDGE" + tag


async def _run(signal, name, gen, universe, panel, kw, num_trials, label=""):
    if _seen(name):
        print(f"  {name:34} (already in report, skip)")
        return
    tr = await run_equity_backtest(
        await gen(universe, TRAIN[0], TRAIN[1], panel=panel, **kw), num_trials=num_trials)
    wf = await run_equity_backtest(
        await gen(universe, WF[0], WF[1], panel=panel, **kw), num_trials=num_trials)
    td, wd = tr.metrics.get("deflated_sharpe"), wf.metrics.get("deflated_sharpe")
    tdd, wdd = tr.metrics.get("max_drawdown"), wf.metrics.get("max_drawdown")
    n_tr, n_wf = tr.metrics.get("num_trades", 0), wf.metrics.get("num_trades", 0)
    v = _verdict(td, wd, wdd, label) if (n_tr or n_wf) else f"PENDING [{label or 'no-data'}]"
    _ROWS.append({"signal": signal, "name": name, "n_tr": n_tr, "n_wf": n_wf,
                  "train_dsr": td, "wf_dsr": wd, "train_dd": tdd, "wf_dd": wdd,
                  "verdict": v, "label": label,
                  "result": {"train": tr.metrics, "walk_forward": wf.metrics}})
    _flush()
    print(f"  {name:34} tr_dsr={_f(td)} wf_dsr={_f(wd)} wf_dd={_p(wdd)} -> {v}")


def _flush():
    REPORTS.mkdir(parents=True, exist_ok=True)
    L = ["# FULL SWEEP — 2026-06-20 (0619.3 Track B)", "",
         "Identical methodology across all signals (MTM equity, costs, train/WF, SANDBOX-cap) so "
         "verdicts are comparable — the incumbent baseline for the GPT-18 research sweep.",
         f"Windows: train {TRAIN[0]}..{TRAIN[1]} | wf {WF[0]}..{WF[1]}.",
         "**SURVIVORSHIP-BIASED** (currently-listed names) -> all capped at SANDBOX, DSRs are upper "
         "bounds, until a point-in-time universe exists. Labels: CACHE_LIMITED (169-name chain cache), "
         "CHAINS_LIMITED (term structure), FUNDAMENTALS_PENDING, *_PENDING = data-gated, NOT no-edge.",
         "",
         "| signal | variant | n_tr | n_wf | train DSR | wf DSR | train DD | wf DD | verdict |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in _ROWS:
        L.append(f"| {r['signal']} | {r['name']} | {r['n_tr']} | {r['n_wf']} | "
                 f"{_f(r['train_dsr'])} | {_f(r['wf_dsr'])} | {_p(r['train_dd'])} | "
                 f"{_p(r['wf_dd'])} | {r['verdict']} |")
    (REPORTS / "FULL_SWEEP_2026-06-20.md").write_text("\n".join(L) + "\n")
    prog = {"updated_at": date.today().isoformat(), "variants": [
        {"signal": r["signal"], "name": r["name"], "needs_marketdata": "CACHE" in r["label"],
         "status": r["verdict"].split("(")[0].split(" ")[0].lower(),
         "verdict": r["verdict"], "label": r["label"], "result": r["result"]}
        for r in _ROWS]}
    (REPORTS / "full_sweep_progress.json").write_text(json.dumps(prog, indent=2, default=str))


def _f(x): return f"{x:.3f}" if isinstance(x, (int, float)) else "-"
def _p(x): return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "-"


async def depth_section():
    print("== DEPTH: momentum neighborhood x ADV multi-slice ==")
    for n in (100, 250, 500):
        uni = liquid_top(n)
        panel = _close_panel(uni)
        avail = panel.shape[1] if not panel.empty else 0
        print(f"-- top-{n} ADV ({avail} names resolved) --")
        for lb in (105, 126, 147, 168):
            await _run("momentum_12_1", f"mom lb={lb} top{n}", generate_momentum_trades,
                       uni, panel, {"lookback_days": lb, "rebalance_days": 21}, num_trials=12,
                       label=f"top{n}")

    print("== DEPTH: options XS family (chain cache) ==")
    cu = _chain_universe()
    cpanel = _close_panel(cu)
    opts = [("skew_25d", "skew hold=21", generate_skew_trades, {"hold_days": 21}),
            ("vrp_z", "vrp_z", generate_vrp_z_trades, {}),
            ("vrp_level", "vrp_level", generate_vrp_level_trades, {}),
            ("iv_call_put_spread", "iv_cp_spread", generate_iv_cp_spread_trades, {}),
            ("iv_term_slope", "iv_term_slope", generate_iv_term_slope_trades, {})]
    for sig, nm, gen, kw in opts:
        await _run(sig, nm, gen, cu, cpanel, kw, num_trials=8, label="CACHE_LIMITED")


async def breadth_section():
    print("== BREADTH: equity primitives + rollups (top-250 ADV) ==")
    uni = liquid_top(250)
    panel = _close_panel(uni)
    print(f"-- top-250 ADV ({panel.shape[1] if not panel.empty else 0} names) --")
    # primitives (cross-sectional, hold=21)
    for prim in equity_xs._SCORERS:
        gen = equity_xs.make_generator(prim)
        await _run(prim, f"{prim}", gen, uni, panel, {}, num_trials=len(equity_xs._SCORERS),
                   label="primitive")
    # rollups
    await _run("trend", "trend(rollup)", equity_xs.generate_trend_trades, uni, panel, {},
               num_trials=5, label="rollup")
    await _run("risk", "risk(rollup)", equity_xs.generate_risk_trades, uni, panel, {},
               num_trials=5, label="rollup")


async def fmp_section():
    print("== FMP-backed (banked disk cache): pead + insider ==")
    from backtest.strategies.pead import generate_pead_trades
    from backtest.strategies.insider import generate_insider_trades
    uni = liquid_top(250)
    panel = _close_panel(uni)
    await _run("beat_and_raise_pead", "pead hold=10", generate_pead_trades, uni, panel,
               {"hold_days": 10}, num_trials=4, label="FMP")
    await _run("beat_and_raise_pead", "pead hold=5", generate_pead_trades, uni, panel,
               {"hold_days": 5}, num_trials=4, label="FMP")
    await _run("insider_cluster", "insider hold=60", generate_insider_trades, uni, panel,
               {"hold_days": 60}, num_trials=4, label="FMP")


async def run(sections):
    _load_existing()
    if "depth" in sections:
        await depth_section()
    if "breadth" in sections:
        await breadth_section()
    if "fmp" in sections:
        await fmp_section()
    print(f"\nwritten -> FULL_SWEEP_2026-06-20.md ({len(_ROWS)} variants)")


if __name__ == "__main__":
    import sys
    secs = sys.argv[1:] or ["depth", "breadth", "fmp"]
    asyncio.run(run(secs))
