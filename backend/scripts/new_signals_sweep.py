"""
0621.2 Part B — NEW_SIGNALS_SWEEP: evidenced signals x {no-regime / oracle / app} arms.

Correct machinery: realistic equal-weight sizing (run_long_only_account for timing strategies,
run_daily_portfolio for XS/market-neutral), true account DD, multiple-testing deflation against
the REAL grid, benchmark-relative, A3 three-arm regime testing (oracle = factual ex-post ceiling,
app = live GMM classifier). ORACLE_ONLY = clears under oracle but not app/unconditional.

Windows: train 2010-2019, wf 2020-2026 (multiple regime instances). Output
NEW_SIGNALS_SWEEP_2026-06-21.{md,json,csv} with git_sha.
"""

from __future__ import annotations

import asyncio
import csv
import json
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.portfolio_mtm import run_long_only_account, run_daily_portfolio
from backtest.strategies.momentum_xs_v2 import _close_panel
from backtest.liquid_universe import liquid_top
from backtest import equity_cache
from research.regime import regime_state as rs_mod
from research.regime import factual as fac
from research.signals import new_signals as ns
from research.signals.gpt18_fmp import generate_earnings_announcement_premium_trades
from research.signals.research_registry import RESEARCH_SIGNALS

REPORTS = Path(__file__).resolve().parents[2] / "data" / "backtest_reports"
TRAIN = (date(2010, 1, 1), date(2019, 12, 31))
WF = (date(2020, 1, 1), date(2026, 6, 18))
COST = 2.0 * 5.0 / 1e4
_GIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()


def _net(t):
    return t.direction * (t.exit_price / t.entry_price - 1.0) - COST


def _series_at(series, d):
    sub = series[series.index <= pd.Timestamp(d)]
    return sub.iloc[-1] if len(sub) else None


def _occurrences(series, allowed, lo, hi, by_trades=None, min_days=20):
    """Contiguous episodes of allowed regimes in [lo,hi]; returns (n_episodes, max_trade_share)."""
    win = series[(series.index >= pd.Timestamp(lo)) & (series.index <= pd.Timestamp(hi))]
    inq = win.isin(allowed).astype(int)
    eps, run = [], 0
    for v in inq:
        if v: run += 1
        elif run: eps.append(run); run = 0
    if run: eps.append(run)
    eps = [e for e in eps if e >= min_days]
    return len(eps)


def _stats(trades):
    if not trades:
        return {}
    r = np.array([_net(t) for t in trades])
    wins, losses = r[r > 0], r[r < 0]
    return {"win_rate": float((r > 0).mean()), "expectancy": float(r.mean()),
            "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() else None}


def _account(trades, panel, sim):
    if sim == "long_only":
        return run_long_only_account(trades, panel)
    return run_daily_portfolio(trades, panel)


def _allowed_regimes(train_trades, series):
    """Regimes with positive mean trade return on TRAIN (the gate, chosen pre-WF)."""
    by = {}
    for t in train_trades:
        g = _series_at(series, t.entry_date)
        if g is None: continue
        by.setdefault(g, []).append(_net(t))
    return [g for g, v in by.items() if len(v) >= 20 and np.mean(v) > 0]


def _arm_metrics(wf_trades, panel, sim, num_trials):
    acct = _account(wf_trades, panel, sim)
    m = acct.metrics
    out = {"n": m.get("num_trades", 0), "sharpe": m.get("sharpe_daily"),
           "true_account_dd": m.get("true_account_dd"), "cagr": m.get("cagr")}
    out.update(_stats(wf_trades))
    return out


def _label(none_arm, oracle_arm, app_arm, train_sharpe, occ_app, occ_oracle,
           spy_train_sh=None, spy_wf_sh=None):
    # 0621.2: BENCHMARK-RELATIVE gate (the runbook's demand). A long-biased strategy that
    # underperforms buy-and-hold is NOT an edge — it's just beta. Require the strategy to
    # BEAT SPY's risk-adjusted return in BOTH windows (excess sharpe > 0), not just be positive.
    beats_bench = ((train_sharpe or -9) > (spy_train_sh or 0)
                   and (none_arm.get("sharpe") or -9) > (spy_wf_sh or 0))

    def clears(a):
        return (a.get("n", 0) >= 100 and (a.get("sharpe") or 0) >= 0.8
                and (a.get("true_account_dd") or 1) < 0.25)
    if clears(none_arm) and (train_sharpe or 0) > 0.3 and beats_bench:
        return "UNCONDITIONAL_CANDIDATE"
    # beats buy-and-hold (both windows) with strong sharpe + adequate n, but trips ONLY the
    # DD gate -> a genuine candidate whose drawdown needs a risk overlay (e.g. crisis cap).
    if (beats_bench and (none_arm.get("n", 0) >= 100) and (none_arm.get("sharpe") or 0) >= 0.8
            and (train_sharpe or 0) > (0.3)):
        return "CANDIDATE_DD_GATED"
    if clears(app_arm) and occ_app >= 3 and (none_arm.get("sharpe") or 0) > (spy_wf_sh or 0):
        return "REGIME_CONDITIONAL_CANDIDATE"
    if clears(oracle_arm) and occ_oracle >= 3:
        return "ORACLE_ONLY"          # works with perfect regime knowledge -> classifier gap
    if clears(none_arm) and not beats_bench:
        return "BETA_NOT_ALPHA"       # clears abs bar but loses to buy-and-hold = not an edge
    if (none_arm.get("sharpe") or 0) >= 0.5 or (oracle_arm.get("sharpe") or 0) >= 0.5:
        return "WEAK_LEAD"
    return "NO_EDGE"


SPECS = [
    # name, generator, universe_fn, sim, kwargs
    ("etf_mean_reversion_narrow", ns.generate_etf_mean_reversion_trades,
     lambda: ["SPY", "QQQ", "IWM"], "long_only", {"universe": ["SPY", "QQQ", "IWM"], "ibs_thresh": 0.2}),
    ("etf_mean_reversion_broad", ns.generate_etf_mean_reversion_trades,
     lambda: ns.ETF_UNIVERSE, "long_only", {"ibs_thresh": 0.2}),
    ("sector_relative_strength", ns.generate_sector_relative_strength_trades,
     lambda: liquid_top(250), "xs", {}),
    ("pairs_statarb", ns.generate_pairs_statarb_trades,
     lambda: liquid_top(150), "xs", {}),
    ("earnings_announcement_premium", generate_earnings_announcement_premium_trades,
     lambda: liquid_top(250), "xs", {}),
]


async def run():
    rseries = rs_mod.load()["regime_state"] if not rs_mod.load().empty else pd.Series(dtype=int)
    oseries = fac.oracle_series()
    spy = equity_cache.load_close("SPY")
    def bench(lo, hi):
        s = spy[(spy.index >= pd.Timestamp(lo)) & (spy.index <= pd.Timestamp(hi))]
        return float((s.iloc[-1] / s.iloc[0]) ** (365 / (s.index[-1] - s.index[0]).days) - 1) if len(s) > 30 else None
    def spy_sharpe(lo, hi):
        s = spy[(spy.index >= pd.Timestamp(lo)) & (spy.index <= pd.Timestamp(hi))].pct_change().dropna()
        return float(s.mean() / s.std() * np.sqrt(252)) if len(s) > 30 and s.std() > 0 else None
    spy_cagr = bench(*WF)
    spy_train_sh, spy_wf_sh = spy_sharpe(*TRAIN), spy_sharpe(*WF)
    num_trials = len(SPECS) * 3 * 2     # signals x arms x ~param variants (real-grid estimate)

    rows = []
    for name, gen, unifn, sim, kw in SPECS:
        uni = unifn()
        panel = pd.DataFrame({s: equity_cache.load_close(s) for s in uni
                              if equity_cache.load_close(s) is not None}).sort_index()
        kw2 = {k: v for k, v in kw.items() if k != "universe"}
        try:
            tr = await gen(uni, TRAIN[0], TRAIN[1], panel=panel, **kw2)
            wf = await gen(uni, WF[0], WF[1], panel=panel, **kw2)
        except Exception as e:
            rows.append({"signal": name, "label": f"ERROR:{e}"}); _write(rows, spy_cagr, num_trials); continue
        train_sh = _account(tr, panel, sim).metrics.get("sharpe_daily")
        none_arm = _arm_metrics(wf, panel, sim, num_trials)
        # oracle + app arms
        oa_allowed = _allowed_regimes(tr, oseries)
        oa_wf = [t for t in wf if _series_at(oseries, t.entry_date) in oa_allowed]
        oracle_arm = _arm_metrics(oa_wf, panel, sim, num_trials)
        occ_oracle = _occurrences(oseries, oa_allowed, *WF) if oa_allowed else 0
        ap_allowed = _allowed_regimes(tr, rseries)
        ap_wf = [t for t in wf if _series_at(rseries, t.entry_date) in ap_allowed]
        app_arm = _arm_metrics(ap_wf, panel, sim, num_trials)
        occ_app = _occurrences(rseries, ap_allowed, *WF) if ap_allowed else 0
        label = _label(none_arm, oracle_arm, app_arm, train_sh, occ_app, occ_oracle,
                       spy_train_sh, spy_wf_sh)
        rows.append({
            "signal": name, "sim": sim, "label": label, "train_sharpe": train_sh,
            "none": none_arm, "oracle": oracle_arm, "app": app_arm,
            "oracle_allowed": [str(x) for x in oa_allowed], "occ_oracle": occ_oracle,
            "app_allowed": [str(x) for x in ap_allowed], "occ_app": occ_app,
            "wf_excess_spy": (none_arm.get("cagr") - spy_cagr) if (none_arm.get("cagr") is not None and spy_cagr is not None) else None,
            "n_train": len(tr), "git_sha": _GIT,
        })
        _write(rows, spy_cagr, num_trials)
        print(f"  {name:30} -> {label}  none(sh={_f(none_arm.get('sharpe'))},dd={_f(none_arm.get('true_account_dd'))}) "
              f"oracle(sh={_f(oracle_arm.get('sharpe'))}) app(sh={_f(app_arm.get('sharpe'))})", flush=True)
    print(f"\nNEW_SIGNALS_SWEEP done: {len(rows)} signals", flush=True)


def _f(x): return f"{x:.2f}" if isinstance(x, (int, float)) else "-"
def _p(x): return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "-"


def _write(rows, spy_cagr, num_trials):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "NEW_SIGNALS_SWEEP_2026-06-21.json").write_text(json.dumps(
        {"windows": {"train": [str(d) for d in TRAIN], "wf": [str(d) for d in WF]},
         "spy_wf_cagr": spy_cagr, "num_trials": num_trials, "git_sha": _GIT,
         "arms": "no-regime | oracle(ex-post ceiling) | app(GMM)", "rows": rows}, indent=2, default=str))
    L = ["# NEW SIGNALS SWEEP — 2026-06-21 (0621.2 Part B)", "",
         f"git_sha {_GIT}. Windows train {TRAIN[0]}..{TRAIN[1]} / wf {WF[0]}..{WF[1]}. "
         f"SPY wf CAGR {_p(spy_cagr)}. num_trials={num_trials}. Realistic equal-weight sizing + costs.",
         "Arms: no-regime | ORACLE (ex-post factual regime = diagnostic ceiling) | APP (live GMM).",
         "",
         "| signal | label | none sh/dd/cagr | oracle sh/n/occ | app sh/n/occ | wf excess_SPY | train sh |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        if "none" not in r:
            L.append(f"| {r['signal']} | {r.get('label')} | - | - | - | - | - |"); continue
        n, o, a = r["none"], r["oracle"], r["app"]
        L.append(f"| {r['signal']} | {r['label']} | {_f(n.get('sharpe'))}/{_p(n.get('true_account_dd'))}/{_p(n.get('cagr'))} | "
                 f"{_f(o.get('sharpe'))}/{o.get('n')}/{r.get('occ_oracle')} | "
                 f"{_f(a.get('sharpe'))}/{a.get('n')}/{r.get('occ_app')} | {_p(r.get('wf_excess_spy'))} | {_f(r.get('train_sharpe'))} |")
    (REPORTS / "NEW_SIGNALS_SWEEP_2026-06-21.md").write_text("\n".join(L) + "\n")
    cols = ["signal", "sim", "label", "train_sharpe", "occ_oracle", "occ_app", "wf_excess_spy", "n_train", "git_sha"]
    with open(REPORTS / "NEW_SIGNALS_SWEEP_2026-06-21.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow(r)


if __name__ == "__main__":
    asyncio.run(run())
