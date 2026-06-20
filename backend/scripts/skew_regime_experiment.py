"""
Track 4b — skew_25d regime-conditioning experiment (CONSTRAINT_RUNBOOK_2026-06-19).

Hypothesis pre-registered in data/backtest_reports/SKEW_REGIME_PREREG_2026-06-19.md
BEFORE this was run. Reads only the cached 49/51-name chain bank (0 new credits).

Method:
  - generate skew_25d trades over 2021-07..2026-06 (the full train+wf span),
  - tag each closed trade with regime_classifier.regime_tag(entry_date) and its window,
  - compute per-bucket deflated Sharpe + MTM drawdown via the same run_equity_backtest
    used by the main validation, so the numbers are comparable.

num_trials for the deflation penalty = number of regime buckets evaluated (multiple-
comparison honesty). Buckets with < MIN_N trades are reported but flagged low-n and
excluded from the decision.
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from datetime import date

from backtest.equity_engine import EquityTrade, run_equity_backtest
from backtest.marketdata_source import DEFAULT_CACHE_ROOT
from backtest.strategies.skew_xs import generate_skew_trades
from analysis.regime_classifier import regime_tag

TRAIN = (date(2021, 7, 1), date(2024, 12, 31))
WF = (date(2025, 1, 1), date(2026, 6, 30))
MIN_N = 30
HOLDS = [21, 42]


def _cache_universe() -> list[str]:
    root = DEFAULT_CACHE_ROOT
    # skip metadata dirs (_CALENDAR, _EXPIRATIONS) — they are not symbols.
    return sorted(d for d in os.listdir(root)
                  if (root / d).is_dir() and not d.startswith("_"))


def _window(d: date) -> str:
    if TRAIN[0] <= d <= TRAIN[1]:
        return "train"
    if WF[0] <= d <= WF[1]:
        return "wf"
    return "other"


async def _bucket_metrics(trades: list[EquityTrade], num_trials: int) -> dict:
    rep = await run_equity_backtest(trades, num_trials=num_trials)
    m = rep.metrics
    return {
        "n": m.get("num_trades", 0),
        "cohorts": m.get("num_cohorts", 0),
        "dsr": m.get("deflated_sharpe"),
        "sharpe": m.get("sharpe"),
        "dd": m.get("max_drawdown"),
        "win": m.get("win_rate"),
    }


async def run() -> str:
    universe = _cache_universe()
    lines: list[str] = []
    lines.append("# skew_25d regime-conditioning RESULT (2026-06-19, Track 4b)")
    lines.append("")
    lines.append(f"Universe: {len(universe)} cached names. 0 new credits (cached chains only).")
    lines.append(f"Windows: train {TRAIN[0]}..{TRAIN[1]} | wf {WF[0]}..{WF[1]}. MIN_N={MIN_N}.")
    lines.append("Hypothesis pre-registered in SKEW_REGIME_PREREG_2026-06-19.md (committed first).")
    lines.append("")

    for hold in HOLDS:
        trades = await generate_skew_trades(
            universe, TRAIN[0], WF[1], rebalance_days=21, hold_days=hold,
        )
        # tag
        tagged = [(t, _window(t.entry_date), regime_tag(t.entry_date)) for t in trades]
        tagged = [x for x in tagged if x[1] in ("train", "wf")]

        # group: pooled by window, and per (window, regime)
        by_window: dict[str, list] = defaultdict(list)
        by_wr: dict[tuple, list] = defaultdict(list)
        for t, win, reg in tagged:
            by_window[win].append(t)
            by_wr[(win, reg)].append(t)

        n_buckets = max(1, len({reg for (_, reg) in by_wr}))

        lines.append(f"## hold={hold}d")
        lines.append("")
        lines.append("Pooled (baseline, reproduces MASTER_REPORT_MTM):")
        lines.append("")
        lines.append("| window | n | cohorts | DSR | Sharpe | MTM_DD | win |")
        lines.append("|---|---|---|---|---|---|---|")
        for win in ("train", "wf"):
            if by_window.get(win):
                m = await _bucket_metrics(by_window[win], num_trials=1)
                lines.append(f"| {win} | {m['n']} | {m['cohorts']} | "
                             f"{_f(m['dsr'])} | {_f(m['sharpe'])} | {_pct(m['dd'])} | {_pct(m['win'])} |")
        lines.append("")
        lines.append(f"By regime bucket (num_trials={n_buckets} for deflation):")
        lines.append("")
        lines.append("| window | regime | n | DSR | Sharpe | MTM_DD | win | note |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for win in ("train", "wf"):
            regs = sorted({reg for (w, reg) in by_wr if w == win})
            for reg in regs:
                tr = by_wr[(win, reg)]
                m = await _bucket_metrics(tr, num_trials=n_buckets)
                note = "" if m["n"] >= MIN_N else "LOW-N (excluded from decision)"
                lines.append(f"| {win} | {reg} | {m['n']} | {_f(m['dsr'])} | "
                             f"{_f(m['sharpe'])} | {_pct(m['dd'])} | {_pct(m['win'])} | {note} |")
        lines.append("")

    return "\n".join(lines)


def _f(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) else "-"


def _pct(x):
    return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "-"


if __name__ == "__main__":
    out = asyncio.run(run())
    path = "../data/backtest_reports/SKEW_REGIME_2026-06-19.md"
    with open(path, "w") as f:
        f.write(out + "\n")
    print(out)
    print(f"\nwritten -> {path}")
