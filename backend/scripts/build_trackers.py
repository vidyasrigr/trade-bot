"""
Build the three single-source-of-truth trackers (Track 5 of CONSTRAINT_RUNBOOK).

  SIGNAL_STATUS.md     - per-signal: tested? stream? pass/fail/why? blocked-by?
  DATA_INVENTORY.md    - what's cached from where, coverage bars, credit ledger
  VALIDATION_LEDGER.md - BT/WF/paper status rolled up per stream + per category

Design (per TRACKERS_SPEC_2026-06-19):
  - Auto-generated, never hand-edited. Reads REGISTRY + cache dirs + report JSONs.
  - Pure python, no LLM, read-only, fast (<5s). Missing source -> PENDING/0%, never errors.
  - Writes to data/trackers/ and mac/trackers/ so V sees them outside the backend.
  - Run: python -m scripts.build_trackers   (also wired hourly + post-run in main.py)

NOTE on data granularity (caution from V 2026-06-19): FMP Starter serves
ratios/key_metrics/analyst_estimates as ANNUAL (quarterly is a premium param).
Those rows are labelled annual-fundamentals in DATA_INVENTORY so a fundamental
signal underperforming on coarse data is not mistaken for a dead edge.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from scoring.signal_registry import REGISTRY, by_name

# --------------------------------------------------------------------------- #
# Paths (backend/ is the cwd anchor; reports live at repo-root data/)
# --------------------------------------------------------------------------- #

BACKEND = Path(__file__).resolve().parents[1]            # .../Trade Bot/backend
REPO = BACKEND.parent                                    # .../Trade Bot
REPORTS = REPO / "data" / "backtest_reports"
MD_CACHE = BACKEND / "data" / "marketdata_cache"
FMP_CACHE = BACKEND / "data" / "cache" / "fmp"
# feature store exists under both roots historically; count both.
FEATURE_STORES = [REPO / "data" / "feature_store", BACKEND / "data" / "feature_store"]
OUT_DIRS = [REPO / "data" / "trackers", REPO / "misc" / "mac" / "trackers"]

# FMP endpoints that come back annual on Starter (quarterly is premium-gated).
_ANNUAL_FMP = {"ratios", "key_metrics", "analyst_est"}

# --------------------------------------------------------------------------- #
# Source readers (all tolerant of missing inputs)
# --------------------------------------------------------------------------- #


def _md_symbols() -> set[str]:
    """Distinct symbols with at least one banked options-chain parquet."""
    if not MD_CACHE.exists():
        return set()
    syms = set()
    for p in MD_CACHE.iterdir():
        if p.is_dir():
            syms.add(p.name)
        else:
            syms.add(p.name.split("_")[0].split(".")[0])
    syms.discard("")
    return syms


def _fmp_counts() -> dict[str, int]:
    """endpoint -> number of symbols banked."""
    out: dict[str, int] = {}
    if not FMP_CACHE.exists():
        return out
    for d in sorted(FMP_CACHE.iterdir()):
        if d.is_dir():
            out[d.name] = sum(1 for _ in d.glob("*.json"))
    return out


def _feature_store_count() -> int:
    """Equity OHLCV parquets (exclude the macro/ subdir, counted separately)."""
    total = 0
    for fs in FEATURE_STORES:
        if fs.exists():
            total += sum(1 for p in fs.rglob("*.parquet") if "macro" not in p.parts)
    return total


def _fred_series_count() -> int:
    seen: set[str] = set()
    for fs in FEATURE_STORES:
        macro = fs / "macro"
        if macro.exists():
            seen.update(p.stem for p in macro.glob("*.parquet"))
    return len(seen)


def _norm_signal(variant_signal: str) -> str:
    """Map a backtest variant's `signal` to a registry name."""
    s = variant_signal.strip()
    # vrp_naked_* / vrp_iron_condor / vrp_regime_gate -> vrp_harvest (the strategy)
    if s.startswith("vrp_naked") or s.startswith("vrp_iron") or s.startswith("vrp_regime"):
        return "vrp_harvest"
    if s.startswith("pead") or s.startswith("beat_and_raise"):
        return "beat_and_raise_pead"
    if s.startswith("skew"):
        return "skew_25d"
    if s.startswith("momentum_12_1") or s.startswith("momentum_xs"):
        return "momentum_12_1"
    if s in by_name():
        return s
    # strip trailing _hold=.. / (..) / =.. decorations and retry
    base = re.split(r"[ (_]?(hold|lookback|=|\()", s)[0]
    return base if base in by_name() else s


def _load_progress(path: Path) -> dict[str, dict]:
    """Read a validation master_progress.json -> best-variant verdict per signal."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for v in data.get("variants", []):
        name = _norm_signal(v.get("signal", ""))
        res = v.get("result") or {}
        tr = res.get("train") or {}
        wf = res.get("walk_forward") or {}
        row = {
            "train_dsr": tr.get("deflated_sharpe"),
            "wf_dsr": wf.get("deflated_sharpe"),
            "train_dd": tr.get("max_drawdown"),
            "wf_dd": wf.get("max_drawdown"),
            "n_tr": tr.get("num_trades"),
            "n_wf": wf.get("num_trades"),
            "status": (v.get("status") or "").lower(),
            "needs_md": v.get("needs_marketdata", False),
            "variant": v.get("name", v.get("signal", "")),
        }
        # keep the variant with the highest wf_dsr per signal (best honest OOS)
        prev = out.get(name)
        if prev is None or (row["wf_dsr"] or -9) > (prev["wf_dsr"] or -9):
            out[name] = row
    return out


def _verdict(spec, row: dict | None, data_ready: bool) -> tuple[str, str]:
    """Return (VERDICT, blocked_by)."""
    if row is None:
        if not data_ready:
            return "BLOCKED", _blocked_reason(spec)
        return "PENDING", "-"
    tr, wf, dd = row.get("train_dsr"), row.get("wf_dsr"), row.get("wf_dd")
    if tr is None and wf is None:
        return "PENDING", "-"
    # Hard gates: train DSR >= 0.50 AND wf DSR >= 0.30 AND wf MTM-DD < 0.25.
    # Free/equity sweeps are survivorship-biased -> capped at SANDBOX (never PASS).
    survivorship = not row.get("needs_md", False)
    passes = (tr or 0) >= 0.50 and (wf or 0) >= 0.30 and (dd or 1) < 0.25
    if passes and survivorship:
        return "SANDBOX", "survivorship-capped (liquid universe)"
    if passes:
        return "PASS", "-"
    if (dd or 0) >= 0.25 and (wf or 0) >= 0.30:
        return "SANDBOX", "DD>25% hard gate"
    if (wf or 0) >= 0.30 or (tr or 0) >= 0.50:
        return "SANDBOX", "partial gate"
    return "NO_EDGE", "-"


def _blocked_reason(spec) -> str:
    srcs = set(spec.data_sources)
    if any("MarketData" in s or "Tradier" in s for s in srcs):
        return "MarketData chain bank"
    if "FMP" in srcs:
        return "FMP bank"
    return "data pending"


def _data_ready(spec, md_syms: set[str], fmp: dict[str, int]) -> bool:
    srcs = set(spec.data_sources)
    if any("MarketData" in s or "Tradier" in s for s in srcs):
        return len(md_syms) > 0
    if "FMP" in srcs:
        return sum(fmp.values()) > 0
    # yfinance / FRED / CFTC etc. are live/keyless -> always testable
    return True


# --------------------------------------------------------------------------- #
# Tracker renderers
# --------------------------------------------------------------------------- #

def _bar(frac: float, width: int = 10) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled) + f" {frac*100:4.0f}%"


def _fmt(x, nd=2):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "-"


def build_signal_status(verdicts: dict, ready: dict, ts: str) -> str:
    counts = {"PASS": 0, "SANDBOX": 0, "NO_EDGE": 0, "BLOCKED": 0, "PENDING": 0, "PARTIAL": 0}
    for v, _ in verdicts.values():
        counts[v] = counts.get(v, 0) + 1
    tested = sum(1 for v, _ in verdicts.values() if v in ("PASS", "SANDBOX", "NO_EDGE"))
    # per-stream tested
    stream_tot = {"O": 0, "S": 0, "M": 0, "L": 0}
    stream_done = {"O": 0, "S": 0, "M": 0, "L": 0}
    for spec in REGISTRY:
        v = verdicts[spec.name][0]
        for st in spec.streams:
            stream_tot[st] += 1
            if v in ("PASS", "SANDBOX", "NO_EDGE"):
                stream_done[st] += 1

    L = []
    L.append(f"SIGNAL STATUS  -  generated {ts}")
    L.append("=" * 95)
    L.append(f"Tested: {tested}/{len(REGISTRY)}   PASS: {counts['PASS']}   "
             f"SANDBOX: {counts['SANDBOX']}   NO_EDGE: {counts['NO_EDGE']}   "
             f"BLOCKED: {counts['BLOCKED']}   PENDING: {counts['PENDING']}")
    L.append("By stream:  " + "   ".join(
        f"{k} {stream_done[k]}/{stream_tot[k]}" for k in ("O", "S", "M", "L")))
    L.append("=" * 95)
    L.append("")
    hdr = (f"{'SIGNAL':<26}{'O S M L':<9}{'DATA':<7}{'TRAIN':>7}{'WF_DSR':>8}"
           f"{'MTM_DD':>8}  {'VERDICT':<9} {'BLOCKED_BY'}")
    for cat in ("engine", "overlay", "cross_section", "compound", "dna", "strategy", "feature_only"):
        specs = [s for s in REGISTRY if s.category == cat]
        if not specs:
            continue
        L.append(f"-- {cat.upper()} " + "-" * (90 - len(cat)))
        L.append(hdr)
        for spec in sorted(specs, key=lambda s: s.name):
            v, why = verdicts[spec.name]
            row = _PROGRESS.get(spec.name)
            sm = " ".join("x" if st in spec.streams else "." for st in ("O", "S", "M", "L"))
            data = "ready" if ready[spec.name] else "wait"
            tr = _fmt(row["train_dsr"]) if row else "-"
            wf = _fmt(row["wf_dsr"]) if row else "-"
            dd = (f"{row['wf_dd']*100:.0f}%" if row and isinstance(row.get("wf_dd"), (int, float)) else "-")
            L.append(f"{spec.name:<26}{sm:<9}{data:<7}{tr:>7}{wf:>8}{dd:>8}  {v:<9} {why}")
        L.append("")
    return "\n".join(L)


def build_data_inventory(md_syms, fmp, ts: str, core_n: int = 200) -> str:
    fred_n = _fred_series_count()
    fs_n = _feature_store_count()
    md_calls = _read_credit_ledger()
    fmp_total = sum(fmp.values())

    L = []
    L.append(f"DATA INVENTORY  -  generated {ts}")
    L.append("=" * 95)
    L.append(f"MarketData chains: {len(md_syms)} symbols banked   |   "
             f"FMP calls cached: {fmp_total}   |   FRED series: {fred_n}")
    L.append(f"MarketData credits today: {md_calls}")
    L.append("=" * 95)
    L.append("")
    L.append(f"{'SOURCE':<12}{'DATASET':<22}{'SYMBOLS':<10}{'COVERAGE(core-'+str(core_n)+')':<22}{'NOTE'}")
    L.append("-" * 95)
    L.append(f"{'MarketData':<12}{'option chains':<22}{len(md_syms):<10}"
             f"{_bar(len(md_syms)/core_n):<22}5y rolling, no hist greeks")
    L.append(f"{'yfinance':<12}{'daily OHLCV (feat)':<22}{fs_n:<10}"
             f"{'(live, keyless)':<22}backfill daemon")
    L.append(f"{'FRED':<12}{'macro series':<22}{fred_n:<10}{_bar(min(fred_n/30,1)):<22}target 30+")
    for ep in sorted(fmp):
        note = "annual-fundamentals" if ep in _ANNUAL_FMP else ""
        L.append(f"{'FMP':<12}{ep:<22}{fmp[ep]:<10}{'(no daily cap, 300/min)':<22}{note}")
    if not fmp:
        L.append(f"{'FMP':<12}{'(daemon starting)':<22}{'0':<10}")
    L.append("")
    L.append("NOTES")
    L.append("- FMP ratios/key_metrics/analyst_est are ANNUAL on Starter (quarterly is premium).")
    L.append("  Fine for slow-moving fundamental scoring; granularity flagged if a signal underperforms.")
    L.append("- FMP short-interest = 404 on Starter; squeeze sourced from free exchange CSV (Track 4a).")
    L.append("- ETFs excluded from the listed-universe parse; options core-200 lists ETFs explicitly.")
    return "\n".join(L)


def build_validation_ledger(verdicts: dict, ts: str) -> str:
    streams = ("O", "S", "M", "L")
    cats = ("engine", "overlay", "cross_section", "compound", "dna", "strategy", "feature_only")
    bt = {s: [0, 0] for s in streams}      # [done, total]
    wf = {s: [0, 0] for s in streams}
    cat_bt = {c: [0, 0] for c in cats}
    cat_wf = {c: [0, 0] for c in cats}
    bt_done = wf_done = 0
    for spec in REGISTRY:
        row = _PROGRESS.get(spec.name)
        has_bt = bool(row and row.get("train_dsr") is not None)
        has_wf = bool(row and row.get("wf_dsr") is not None)
        bt_done += has_bt
        wf_done += has_wf
        for st in spec.streams:
            bt[st][1] += 1
            wf[st][1] += 1
            bt[st][0] += has_bt
            wf[st][0] += has_wf
        cat_bt[spec.category][1] += 1
        cat_wf[spec.category][1] += 1
        cat_bt[spec.category][0] += has_bt
        cat_wf[spec.category][0] += has_wf

    L = []
    L.append(f"VALIDATION LEDGER  -  generated {ts}")
    L.append("=" * 70)
    L.append(f"Signals with BACKTEST: {bt_done}/{len(REGISTRY)}    "
             f"WALK-FWD: {wf_done}/{len(REGISTRY)}    PAPER: 0/{len(REGISTRY)}")
    L.append("=" * 70)
    L.append("")
    L.append(f"{'BY STREAM':<12}{'BT':<10}{'WF':<10}{'PAPER'}")
    L.append("-" * 50)
    names = {"O": "Options", "S": "Swing", "M": "Mid", "L": "Long"}
    for st in streams:
        L.append(f"{names[st]:<12}{f'{bt[st][0]}/{bt[st][1]}':<10}"
                 f"{f'{wf[st][0]}/{wf[st][1]}':<10}{f'0/{wf[st][1]}'}")
    L.append("")
    L.append(f"{'BY CATEGORY':<16}{'BT':<10}{'WF':<10}{'PAPER'}")
    L.append("-" * 50)
    for c in cats:
        if cat_bt[c][1] == 0:
            continue
        L.append(f"{c:<16}{f'{cat_bt[c][0]}/{cat_bt[c][1]}':<10}"
                 f"{f'{cat_wf[c][0]}/{cat_wf[c][1]}':<10}{f'0/{cat_wf[c][1]}'}")
    L.append("")
    L.append("PAPER PIPELINE (populates once a signal clears the hard gates)")
    L.append("-" * 50)
    passes = [n for n, (v, _) in verdicts.items() if v == "PASS"]
    if passes:
        for n in passes:
            L.append(f"  {n}  -> awaiting paper duration gate")
    else:
        L.append("  (empty - nothing has cleared the hard gates yet)")
    return "\n".join(L)


def _read_credit_ledger() -> str:
    """Best-effort MarketData credit counter from the phase4/bank progress json."""
    for fn in ("phase4_bank.json", "master_progress.json"):
        p = REPORTS / fn
        if p.exists():
            try:
                d = json.loads(p.read_text())
                for k in ("credits_used", "credits_spent", "credits"):
                    if k in d:
                        return str(d[k])
            except Exception:
                pass
    return "see phase4_bank.json"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

_PROGRESS: dict[str, dict] = {}


def generate() -> None:
    global _PROGRESS
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    md_syms = _md_symbols()
    fmp = _fmp_counts()

    # validation results: merge the options master_progress + free sweep progress
    _PROGRESS = _load_progress(REPORTS / "master_progress.json")
    free = _load_progress(REPORTS / "free_sweep_progress.json")
    for k, v in free.items():
        if k not in _PROGRESS or (v.get("wf_dsr") or -9) > (_PROGRESS[k].get("wf_dsr") or -9):
            _PROGRESS[k] = v

    ready = {s.name: _data_ready(s, md_syms, fmp) for s in REGISTRY}
    verdicts = {}
    for spec in REGISTRY:
        verdicts[spec.name] = _verdict(spec, _PROGRESS.get(spec.name), ready[spec.name])

    files = {
        "SIGNAL_STATUS.md": build_signal_status(verdicts, ready, ts),
        "DATA_INVENTORY.md": build_data_inventory(md_syms, fmp, ts),
        "VALIDATION_LEDGER.md": build_validation_ledger(verdicts, ts),
    }
    for out in OUT_DIRS:
        out.mkdir(parents=True, exist_ok=True)
        for fname, body in files.items():
            (out / fname).write_text(body + "\n")
    print(f"trackers regenerated {ts} -> {', '.join(str(o) for o in OUT_DIRS)}")


if __name__ == "__main__":
    generate()
