"""
0620.2 Phase 3 — full regime re-test (both bars + D1/D2/D3 + multiple-testing control).

Re-tests incumbents (0619.3) + GPT-18 on post-Phase-0 clean data, ONE comparable harness:
  - cohort DSR (equity_engine) for train/wf,
  - TRUE account DD (portfolio_mtm, Phase 2.0) — the DD all verdicts are graded on,
  - win_rate / expectancy / profit_factor / turnover,
  - D2 regime-stratified: per causal regime_state, the signal's mean trade return + n,
  - D3 live-regime-gate: allowed regimes chosen on train_select, verified on train_validate,
    then WF traded ONLY in allowed regimes -> gated DSR/DD/n + regime-instance integrity,
  - THEME_BET: >40% of WF positive PnL from one emergent cluster,
  - benchmark-relative: WF CAGR excess vs SPY and QQQ,
  - multiple-testing: DSR deflated against the program-wide trial count.

Label taxonomy (no PASS/SANDBOX binary):
  UNCONDITIONAL_CANDIDATE | REGIME_CONDITIONAL_CANDIDATE | REGIME_CANDIDATE_PENDING_TEST |
  REGIME_SUSPECT | INSUFFICIENT_REGIME_INSTANCES | SMALL_N | SURVIVORSHIP_CAPPED |
  THEME_BET | DD_PROVISIONAL | DATA_GATED | NO_EDGE

Output (machine-readable so trackers never scrape markdown): REGIME_SWEEP_2026-06-20.md + .json + .csv
with git_sha + source_report per row. Everything SANDBOX/SURVIVORSHIP_CAPPED until PIT (Session 3).
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

from backtest.equity_engine import run_equity_backtest, EquityTrade
from backtest.portfolio_mtm import run_daily_portfolio
from backtest.strategies.momentum_xs_v2 import _close_panel, generate_momentum_trades
from backtest.strategies import equity_xs
from backtest.strategies.skew_xs import generate_skew_trades
from backtest.strategies.options_xs import (generate_vrp_z_trades, generate_iv_cp_spread_trades)
from backtest.strategies.pead import generate_pead_trades
from backtest.strategies.insider import generate_insider_trades
from backtest.strategies.short_interest_xs import (generate_si_bearish_trades,
                                                   generate_squeeze_candidate_trades)
from backtest.liquid_universe import liquid_top, sector_map
from backtest.marketdata_source import DEFAULT_CACHE_ROOT
from backtest import equity_cache
from research.signals.research_registry import RESEARCH_SIGNALS
from research.regime import regime_state as rs_mod
from research.regime import themes as themes_mod

REPORTS = Path(__file__).resolve().parents[2] / "data" / "backtest_reports"
TRAIN = (date(2021, 7, 1), date(2024, 12, 31))
WF = (date(2025, 1, 1), date(2026, 6, 30))
TRAIN_SELECT = (date(2021, 7, 1), date(2023, 12, 31))
TRAIN_VALIDATE = (date(2024, 1, 1), date(2024, 12, 31))
COST = 2.0 * 5.0 / 1e4

_GIT_SHA = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def _chain_universe():
    # only chain names that are ALSO in the equity cache (so the panel is cache-only,
    # never falling back to throttled yfinance during the sweep).
    cached = {p.stem for p in equity_cache.EQUITY_DIR.glob("*.parquet")}
    return sorted(d.name for d in DEFAULT_CACHE_ROOT.iterdir()
                  if d.is_dir() and not d.name.startswith("_") and d.name in cached)


def _cache_panel(universe):
    """Cache-only close panel (no yfinance fallback) for sweep speed."""
    panel, _missing = equity_cache.cached_panel(universe)
    if panel.empty:
        return panel
    return panel.sort_index()


def _net_ret(t: EquityTrade) -> float:
    return t.direction * (t.exit_price / t.entry_price - 1.0) - COST


def _regime_series() -> pd.Series:
    rs = rs_mod.load()
    if rs.empty:
        return pd.Series(dtype=int)
    return rs["regime_state"]


def _regime_at(rseries: pd.Series, d: date):
    if rseries.empty:
        return None
    sub = rseries[rseries.index <= pd.Timestamp(d)]
    return int(sub.iloc[-1]) if len(sub) else None


def _bench_cagr(sym: str, start: date, end: date):
    s = equity_cache.load_close(sym)
    if s is None or s.empty:
        return None
    s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    if len(s) < 30:
        return None
    yrs = max((s.index[-1] - s.index[0]).days / 365.0, 1e-6)
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1.0)


def _trade_stats(trades):
    if not trades:
        return {}
    r = np.array([_net_ret(t) for t in trades])
    wins, losses = r[r > 0], r[r < 0]
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else None
    holds = [( (t.exit_date - t.entry_date).days ) for t in trades]
    return {"win_rate": float((r > 0).mean()), "expectancy": float(r.mean()),
            "profit_factor": float(pf) if pf else None, "avg_hold_days": float(np.mean(holds))}


def _d2_regime_stratified(trades, rseries):
    """Per regime_state: mean trade return + n (at entry)."""
    by = {}
    for t in trades:
        g = _regime_at(rseries, t.entry_date)
        if g is None:
            continue
        by.setdefault(g, []).append(_net_ret(t))
    return {int(g): {"n": len(v), "mean_ret": float(np.mean(v))} for g, v in by.items()}


def _occurrences(rseries, allowed, lo, hi, min_days=30):
    """Distinct contiguous episodes of an allowed regime within [lo,hi]; count + max share."""
    win = rseries[(rseries.index >= pd.Timestamp(lo)) & (rseries.index <= pd.Timestamp(hi))]
    inq = win.isin(allowed).astype(int)
    episodes, run = [], 0
    for v in inq:
        if v:
            run += 1
        elif run:
            episodes.append(run); run = 0
    if run:
        episodes.append(run)
    episodes = [e for e in episodes if e >= min_days]
    return episodes


def _d3_live_gate(train_trades, wf_trades, rseries):
    """Allowed regimes chosen on train_select, verified on train_validate, then WF gated."""
    sel = [t for t in train_trades if TRAIN_SELECT[0] <= t.entry_date <= TRAIN_SELECT[1]]
    val = [t for t in train_trades if TRAIN_VALIDATE[0] <= t.entry_date <= TRAIN_VALIDATE[1]]
    d2_sel = _d2_regime_stratified(sel, rseries)
    d2_val = _d2_regime_stratified(val, rseries)
    # allowed = regimes positive on BOTH select and validate (no peeking at WF)
    allowed = [g for g, s in d2_sel.items()
               if s["mean_ret"] > 0 and d2_val.get(g, {}).get("mean_ret", -1) > 0]
    if not allowed:
        return {"allowed": [], "gated_n": 0, "verdict": "no_allowed_regime"}
    gated = [t for t in wf_trades if _regime_at(rseries, t.entry_date) in allowed]
    eps = _occurrences(rseries, allowed, WF[0], WF[1])
    r = np.array([_net_ret(t) for t in gated]) if gated else np.array([])
    return {"allowed": allowed, "gated_n": len(gated),
            "gated_mean_ret": float(r.mean()) if len(r) else None,
            "gated_win_rate": float((r > 0).mean()) if len(r) else None,
            "wf_occurrences": len(eps),
            "max_episode_share": (max(eps) / sum(eps)) if eps else None}


def _theme_bet(wf_trades, clusters):
    """Concentration of WF positive PnL in one PRECOMPUTED emergent cluster."""
    if not wf_trades or not clusters:
        return {"theme_bet": False, "top_cluster_share": 0.0}
    pnl = {}
    for t in wf_trades:
        pnl[t.symbol] = pnl.get(t.symbol, 0.0) + _net_ret(t)
    return themes_mod.theme_concentration(pnl, clusters)


# signal set: (name, generator, kwargs, data_class, universe_kind)
def _signal_set():
    sigs = []
    sigs.append(("momentum_12_1", generate_momentum_trades, {"lookback_days": 126}, "EQUITY", "equity"))
    for prim in equity_xs._SCORERS:
        sigs.append((prim, equity_xs.make_generator(prim), {}, "EQUITY", "equity"))
    sigs.append(("trend", equity_xs.generate_trend_trades, {}, "EQUITY", "equity"))
    sigs.append(("risk", equity_xs.generate_risk_trades, {}, "EQUITY", "equity"))
    sigs.append(("skew_25d", generate_skew_trades, {"hold_days": 21}, "OPTIONS", "chain"))
    sigs.append(("vrp_z", generate_vrp_z_trades, {}, "OPTIONS", "chain"))
    sigs.append(("iv_call_put_spread", generate_iv_cp_spread_trades, {}, "OPTIONS", "chain"))
    sigs.append(("beat_and_raise_pead", generate_pead_trades, {"hold_days": 10}, "FMP", "equity"))
    sigs.append(("insider_cluster", generate_insider_trades, {"hold_days": 60}, "FMP", "equity"))
    sigs.append(("short_squeeze_bearish", generate_si_bearish_trades, {"hold_days": 21}, "SI", "equity"))
    sigs.append(("squeeze_candidate", generate_squeeze_candidate_trades, {"hold_days": 21}, "SI", "equity"))
    for name, (gen, dclass, _caution) in RESEARCH_SIGNALS.items():
        kind = "chain" if dclass == "OPTIONS" else "equity"
        sigs.append((name, gen, {}, "RESEARCH:" + dclass, kind))
    return sigs


def _label(row, num_trials):
    n_tr, n_wf = row.get("n_train", 0), row.get("n_wf", 0)
    if "PENDING" in row.get("data_flags", "") or (n_tr == 0 and n_wf == 0):
        return "DATA_GATED"
    if (n_tr and n_tr < 100) or (n_wf and n_wf < 50):
        return "SMALL_N"
    tr, wf = row.get("train_dsr") or 0, row.get("wf_dsr") or 0
    dd = row.get("true_account_dd")
    uncond = (tr >= 0.50 and wf >= 0.30 and (dd is not None and dd < 0.25))
    if uncond:
        return "SURVIVORSHIP_CAPPED(UNCONDITIONAL_CANDIDATE)"
    # regime-conditional: D3 gated positive + integrity + not theme bet
    d3 = row.get("_d3", {})
    if (d3.get("gated_mean_ret") or 0) > 0 and (d3.get("gated_n") or 0) >= 100:
        if (d3.get("wf_occurrences") or 0) < 3 or (d3.get("max_episode_share") or 1) > 0.5:
            return "INSUFFICIENT_REGIME_INSTANCES"
        if row.get("theme_bet"):
            return "THEME_BET"
        return "SURVIVORSHIP_CAPPED(REGIME_CONDITIONAL_CANDIDATE)"
    if wf >= 0.30 and tr < 0.50:
        return "REGIME_CANDIDATE_PENDING_TEST"
    if dd is None:
        return "DD_PROVISIONAL"
    return "NO_EDGE"


async def run():
    sigs = _signal_set()
    num_trials = max(len(sigs) * 3, 60)         # program-wide multiple-testing deflation
    rseries = _regime_series()
    sm = sector_map()
    eq_uni = liquid_top(250); eq_panel = _cache_panel(eq_uni)
    ch_uni = _chain_universe(); ch_panel = _cache_panel(ch_uni)
    spy_tr, qqq_tr = _bench_cagr("SPY", *WF), _bench_cagr("QQQ", *WF)
    # precompute emergent clusters ONCE at the WF midpoint (same for every signal)
    wf_mid = pd.Timestamp(WF[0]) + (pd.Timestamp(WF[1]) - pd.Timestamp(WF[0])) / 2
    clusters_wf = themes_mod.emergent_clusters(eq_panel, wf_mid) if not eq_panel.empty else {}

    rows = []
    for name, gen, kw, dclass, kind in sigs:
        uni, panel = (eq_uni, eq_panel) if kind == "equity" else (ch_uni, ch_panel)
        try:
            tr_tr = await gen(uni, TRAIN[0], TRAIN[1], panel=panel, **kw)
            wf_tr = await gen(uni, WF[0], WF[1], panel=panel, **kw)
        except Exception as e:
            rows.append({"signal": name, "data_class": dclass, "data_flags": f"ERROR:{e}",
                         "label": "DATA_GATED", "n_train": 0, "n_wf": 0})
            continue
        trb = await run_equity_backtest(tr_tr, num_trials=num_trials)
        wfb = await run_equity_backtest(wf_tr, num_trials=num_trials)
        mtm = run_daily_portfolio(wf_tr, panel, sector_map=sm)
        d2 = _d2_regime_stratified(wf_tr, rseries)
        d3 = _d3_live_gate(tr_tr, wf_tr, rseries)
        theme = _theme_bet(wf_tr, clusters_wf)
        sig_cagr = mtm.metrics.get("cagr")
        flags = []
        if dclass.startswith("RESEARCH:FMP_STATEMENT") or (dclass == "FMP" and len(wf_tr) == 0):
            flags.append("FUNDAMENTALS_PENDING")
        if kind == "chain":
            flags.append("CACHE_LIMITED")
        flags.append("SURVIVORSHIP")
        row = {
            "signal": name, "data_class": dclass,
            "train_dsr": trb.metrics.get("deflated_sharpe"),
            "wf_dsr": wfb.metrics.get("deflated_sharpe"),
            "cohort_wf_dd": wfb.metrics.get("max_drawdown"),
            "true_account_dd": mtm.metrics.get("true_account_dd"),
            "n_train": trb.metrics.get("num_trades", 0), "n_wf": wfb.metrics.get("num_trades", 0),
            "wf_cagr": sig_cagr, "excess_spy": (sig_cagr - spy_tr) if (sig_cagr is not None and spy_tr is not None) else None,
            "excess_qqq": (sig_cagr - qqq_tr) if (sig_cagr is not None and qqq_tr is not None) else None,
            "theme_bet": theme.get("theme_bet"), "theme_share": theme.get("top_cluster_share"),
            "d2_regime": d2, "_d3": d3,
            "d3_allowed": d3.get("allowed"), "d3_gated_n": d3.get("gated_n"),
            "d3_gated_mean_ret": d3.get("gated_mean_ret"), "d3_wf_occurrences": d3.get("wf_occurrences"),
            "data_flags": "|".join(flags), "source_report": "REGIME_SWEEP_2026-06-20",
            "git_sha": _GIT_SHA, "num_trials": num_trials,
        }
        row.update(_trade_stats(wf_tr))
        row["label"] = _label(row, num_trials)
        rows.append(row)
        _write(rows, spy_tr, qqq_tr, num_trials)
        print(f"  {name:30} tr={_f(row.get('train_dsr'))} wf={_f(row.get('wf_dsr'))} "
              f"acctDD={_f(row.get('true_account_dd'))} -> {row['label']}")
    print(f"\nREGIME_SWEEP complete: {len(rows)} signals")


def _f(x): return f"{x:.3f}" if isinstance(x, (int, float)) else "-"
def _p(x): return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "-"


def _write(rows, spy, qqq, num_trials):
    REPORTS.mkdir(parents=True, exist_ok=True)
    # JSON (authoritative, tracker reads this)
    (REPORTS / "REGIME_SWEEP_2026-06-20.json").write_text(json.dumps(
        {"windows": {"train": [str(d) for d in TRAIN], "wf": [str(d) for d in WF]},
         "spy_wf_cagr": spy, "qqq_wf_cagr": qqq, "num_trials": num_trials,
         "git_sha": _GIT_SHA, "rows": rows}, indent=2, default=str))
    # CSV (flat schema)
    cols = ["signal", "data_class", "label", "train_dsr", "wf_dsr", "cohort_wf_dd",
            "true_account_dd", "n_train", "n_wf", "win_rate", "expectancy", "profit_factor",
            "avg_hold_days", "wf_cagr", "excess_spy", "excess_qqq", "theme_bet", "theme_share",
            "d3_allowed", "d3_gated_n", "d3_gated_mean_ret", "d3_wf_occurrences",
            "data_flags", "source_report", "git_sha"]
    with open(REPORTS / "REGIME_SWEEP_2026-06-20.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    # MD (human)
    L = ["# REGIME SWEEP — 2026-06-20 (0620.2 Phase 3)", "",
         f"git_sha {_GIT_SHA}. num_trials={num_trials} (program-wide multiple-testing deflation). "
         f"True account DD via Phase 2.0 daily-MTM simulator. SPY wf CAGR {_p(spy)}, QQQ {_p(qqq)}.",
         "Both bars; D2 regime-stratified + D3 live-gate (allowed regimes chosen on "
         "train_select, verified on train_validate, never on WF). SANDBOX/SURVIVORSHIP-capped until PIT.",
         "",
         "| signal | class | train DSR | wf DSR | acct DD | n_wf | win% | excess_SPY | theme | D3 gated_n/occ | label |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['signal']} | {r.get('data_class','')} | {_f(r.get('train_dsr'))} | "
                 f"{_f(r.get('wf_dsr'))} | {_p(r.get('true_account_dd'))} | {r.get('n_wf',0)} | "
                 f"{_p(r.get('win_rate'))} | {_p(r.get('excess_spy'))} | "
                 f"{'YES' if r.get('theme_bet') else '-'} | "
                 f"{r.get('d3_gated_n','-')}/{r.get('d3_wf_occurrences','-')} | {r.get('label','')} |")
    (REPORTS / "REGIME_SWEEP_2026-06-20.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    asyncio.run(run())
