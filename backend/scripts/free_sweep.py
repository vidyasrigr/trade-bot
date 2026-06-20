"""
Track 3 — free-signal sweep on a curated LIQUID universe (CONSTRAINT_RUNBOOK).

Runs the pure-free equity generators (momentum family, lead_lag) on the liquid_264
set, reading close panels from the persistent equity cache (backfilled, throttle-free).
MTM equity (run_equity_backtest computes drawdown on the cohort equity curve).

Survivorship: the liquid universe is currently-listed names only -> every result is
labelled SURVIVORSHIP-BIASED and capped at SANDBOX (never PASS), per the runbook's
PIT gap. DSRs are upper bounds.

Signals needing FMP/MarketData (pead, insider, squeeze, skew) are NOT here — they run
as those banks fill. trend/candles/etc. have no backtest adapter yet (the ~15-adapter
primitive-decomposition build is a later night).

Output:
  data/backtest_reports/FREE_SWEEP_2026-06-19.md
  data/backtest_reports/free_sweep_progress.json   (trackers ingest this)
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from backtest.equity_engine import run_equity_backtest
from backtest.strategies.momentum_xs_v2 import generate_momentum_trades, _close_panel
from backtest.strategies.lead_lag_bt import generate_lead_lag_trades

TRAIN = (date(2021, 7, 1), date(2024, 12, 31))
WF = (date(2025, 1, 1), date(2026, 6, 30))
REPORTS = Path(__file__).resolve().parents[2] / "data" / "backtest_reports"

# (signal, variant_name, generator, kwargs). Fast variants first; lead_lag last
# (O(n^2) correlations) and capped to a smaller liquid subset to stay tractable.
VARIANTS = [
    ("momentum_12_1", "momentum lookback=252", generate_momentum_trades,
     {"lookback_days": 252, "rebalance_days": 21}),
    ("momentum_12_1", "momentum lookback=189", generate_momentum_trades,
     {"lookback_days": 189, "rebalance_days": 21}),
    ("momentum_12_1", "momentum lookback=126", generate_momentum_trades,
     {"lookback_days": 126, "rebalance_days": 21}),
    ("momentum_12_1", "momentum lookback=63", generate_momentum_trades,
     {"lookback_days": 63, "rebalance_days": 21}),
    ("supply_chain_lead_lag", "lead_lag (top120)", generate_lead_lag_trades,
     {"_universe_cap": 120}),
]

NUM_TRIALS = len(VARIANTS)   # honest multiple-testing penalty across the sweep


def _verdict(tr, wf, dd) -> str:
    # survivorship-capped: a passing signal is SANDBOX, never PASS, until PIT re-test.
    passes = (tr or 0) >= 0.50 and (wf or 0) >= 0.30 and (dd or 1) < 0.25
    if passes:
        return "SANDBOX (survivorship-capped)"
    if (dd or 0) >= 0.25 and (wf or 0) >= 0.30:
        return "SANDBOX (DD>25%)"
    if (wf or 0) >= 0.30 or (tr or 0) >= 0.50:
        return "SANDBOX (partial)"
    return "NO_EDGE"


async def run() -> None:
    from scripts.backfill_equity_daemon import liquid_universe
    universe = liquid_universe()
    panel = _close_panel(universe)   # from disk cache (write-through for any misses)
    n_names = panel.shape[1] if not panel.empty else 0

    rows = []
    progress = {"updated_at": date.today().isoformat(), "universe_liquid": n_names,
                "variants": []}
    for signal, name, gen, kw in VARIANTS:
        cap = kw.pop("_universe_cap", None)
        uni = universe[:cap] if cap else universe
        sub_panel = panel[[c for c in panel.columns if c in set(uni)]] if cap else panel
        tr_trades = await gen(uni, TRAIN[0], TRAIN[1], panel=sub_panel, **kw)
        wf_trades = await gen(uni, WF[0], WF[1], panel=sub_panel, **kw)
        tr = await run_equity_backtest(tr_trades, num_trials=NUM_TRIALS)
        wf = await run_equity_backtest(wf_trades, num_trials=NUM_TRIALS)
        tdsr = tr.metrics.get("deflated_sharpe")
        wdsr = wf.metrics.get("deflated_sharpe")
        wdd = wf.metrics.get("max_drawdown")
        verdict = _verdict(tdsr, wdsr, wdd)
        rows.append((name, tr.metrics.get("num_trades", 0), wf.metrics.get("num_trades", 0),
                     tdsr, wdsr, tr.metrics.get("max_drawdown"), wdd, verdict))
        progress["variants"].append({
            "signal": signal, "name": name, "needs_marketdata": False,
            "universe_size": n_names, "status": verdict.split()[0].lower(),
            "result": {"train": tr.metrics, "walk_forward": wf.metrics},
        })
        _write_outputs(rows, progress, n_names)   # incremental persist per variant
        print(f"  done: {name}  train_dsr={_f(tdsr)} wf_dsr={_f(wdsr)} -> {verdict}")

    print(f"\nwritten -> FREE_SWEEP_2026-06-19.md + free_sweep_progress.json")


def _write_outputs(rows, progress, n_names) -> None:
    # markdown
    L = [f"# FREE SWEEP — liquid_{n_names} (2026-06-19, Track 3)", "",
         f"Universe: {n_names} curated liquid names (chain-bank CORE_200 + get_full_universe), "
         "read from the persistent equity cache. MTM equity.",
         f"Windows: train {TRAIN[0]}..{TRAIN[1]} | wf {WF[0]}..{WF[1]}. num_trials={NUM_TRIALS}.",
         "",
         "**SURVIVORSHIP-BIASED**: currently-listed names only. All DSRs are upper bounds; "
         "every result is capped at SANDBOX (never PASS) until re-tested on a point-in-time "
         "universe with delisted names.",
         "",
         "| variant | n_tr | n_wf | train DSR | wf DSR | train MTM-DD | wf MTM-DD | verdict |",
         "|---|---|---|---|---|---|---|---|"]
    for nm, ntr, nwf, td, wd, tdd, wdd, v in rows:
        L.append(f"| {nm} | {ntr} | {nwf} | {_f(td)} | {_f(wd)} | {_p(tdd)} | {_p(wdd)} | {v} |")
    L += ["",
          "## Notes",
          "- Only the pure-free generators (momentum, lead_lag) run here; they need no FMP/MarketData.",
          "- pead/insider/short_squeeze run as the FMP bank + disk-readers land; skew is options-bound.",
          "- trend/candles/chart_patterns/support_resistance/risk/volatility_regime have no backtest "
          "adapter yet (the ~15-adapter primitive-decomposition build is a later night).",
          "- True 500/1000/2000 breadth needs an ADV-ranked universe (volume ranking); the alphabetical "
          "directory head is illiquid junk, so liquid_264 is the honest scale tonight."]

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "FREE_SWEEP_2026-06-19.md").write_text("\n".join(L) + "\n")
    (REPORTS / "free_sweep_progress.json").write_text(json.dumps(progress, indent=2, default=str))


def _f(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) else "-"


def _p(x):
    return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "-"


if __name__ == "__main__":
    asyncio.run(run())
