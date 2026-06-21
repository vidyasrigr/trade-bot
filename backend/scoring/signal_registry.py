"""
Signal Registry + Audit — Phase K.

Single source of truth for every signal the system computes. Each signal
declares:

  - name              : unique identifier
  - category          : 'engine', 'cross_section', 'compound', 'overlay',
                        'dna', 'strategy', 'feature_only'
  - module            : where it lives (importable path)
  - output_destination: where its results land
                        ('category_score', 'signal_ranks', 'compound_signal_events',
                         'factor_ic_scores', 'feature_store', 'briefing_only')
  - data_sources      : declared data dependencies, validated by the audit
  - promotion_status  : 'proposed' / 'paper' / 'live_small' / 'live_full' /
                        'demoted' / 'sandbox' / 'feature_only'
  - influences_conviction: whether the signal currently feeds compute_final_score
                          (sandbox signals MUST have this False)
  - research_anchor   : peer-reviewed paper or null

Audit checks (run nightly or on demand):
  1. Every signal in the registry has fresh data (last_computed within stale window)
  2. Every signal firing in DB tables IS in the registry (no shadow signals)
  3. No sandbox signal influences conviction (no leakage)
  4. No signal double-counts (e.g. same data path scored twice)
  5. Promotion-ladder status in factor_ic_scores matches registry

The registry powers:
  - GET /api/signals — UI surface listing every signal + contribution
  - Nightly contamination check (logged + Discord alert on failure)
  - /signals/audit slash-command for on-demand inspection
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Iterable

from loguru import logger


# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalSpec:
    name: str
    category: str
    module: str
    output_destination: str
    data_sources: tuple[str, ...]
    promotion_status: str = "proposed"
    influences_conviction: bool = True
    research_anchor: str | None = None
    stale_after_days: int = 2   # default freshness window
    streams: tuple[str, ...] = ()   # trading streams this signal informs: O/S/M/L

    def to_dict(self) -> dict:
        return asdict(self)


# Canonical list. ADD signals here when you add them, REMOVE when you delete.
# Audit fails when DB shows signals not in this list (shadow) or when registry
# signals haven't produced recent rows (stale / silently broken).

REGISTRY: tuple[SignalSpec, ...] = (
    # ── ENGINE CATEGORIES (15, weighted to sum 100) ─────────────────────────
    SignalSpec("macro",             "engine", "analysis.macro",
               "category_score", ("FRED", "yfinance"), "live_full", True, None),
    SignalSpec("calendar",          "engine", "analysis.calendar",
               "category_score", ("FOMC_RSS", "BLS_CPI_calendar"), "live_full", True, None),
    SignalSpec("fundamental",       "engine", "analysis.fundamental",
               "category_score", ("FMP", "AlphaVantage"), "live_full", True, None),
    SignalSpec("trend",             "engine", "analysis.trend",
               "category_score", ("yfinance",), "live_full", True, None),
    SignalSpec("support_resistance","engine", "analysis.support_resistance",
               "category_score", ("yfinance",), "live_full", True, None),
    SignalSpec("candles",           "engine", "analysis.candles",
               "category_score", ("yfinance",), "live_full", True, None),
    SignalSpec("chart_patterns",    "engine", "analysis.chart_patterns",
               "category_score", ("yfinance",), "live_full", True, None),
    SignalSpec("momentum",          "engine", "analysis.momentum",
               "category_score", ("yfinance",), "live_full", True,
               "Jegadeesh-Titman 1993; Daniel-Moskowitz 2016 crash filter"),
    SignalSpec("iv_analysis",       "engine", "analysis.iv_analysis",
               "category_score", ("MarketData/Tradier", "yfinance"), "live_full", True,
               "Carr-Wu 2009 VRP; Xing-Zhang-Zhao 2010 skew"),
    SignalSpec("options_chain",     "engine", "analysis.options_chain",
               "category_score", ("MarketData/Tradier",), "live_full", True, None),
    SignalSpec("greeks",            "engine", "analysis.greeks",
               "category_score", ("MarketData/Tradier",), "live_full", True, None),
    SignalSpec("trade_structure",   "engine", "analysis.trade_structure_analysis",
               "category_score", ("MarketData/Tradier",), "live_full", True, None),
    SignalSpec("sentiment",         "engine", "analysis.sentiment",
               "category_score", ("AlphaVantage", "options_flow", "gex_dex"), "live_full", True,
               "Drechsler-Drechsler 2014 SI bearish drag (corrected H6)"),
    SignalSpec("liquidity",         "engine", "analysis.liquidity",
               "category_score", ("MarketData/Tradier",), "live_full", True, None),
    SignalSpec("risk",              "engine", "analysis.risk",
               "category_score", ("yfinance",), "live_full", True, None),

    # ── OVERLAY ANALYZERS (weight=0 in engine, modify other categories) ─────
    SignalSpec("gex_dex",           "overlay", "analysis.gex_dex",
               "category_score", ("MarketData/Tradier",), "live_full", True,
               "SqueezeMetrics white paper"),
    SignalSpec("options_flow",      "overlay", "analysis.options_flow",
               "category_score", ("MarketData/Tradier",), "live_full", True,
               "Pan-Poteshman 2006"),
    SignalSpec("volatility_regime", "overlay", "analysis.volatility_regime",
               "category_score", ("yfinance", "VIX"), "live_full", True, None),
    SignalSpec("earnings_adj_iv",   "overlay", "analysis.earnings_adj_iv",
               "category_score", ("MarketData/Tradier", "FMP"), "live_full", True, None),

    # ── CROSS-SECTIONAL RANKS (signal_ranks table) ──────────────────────────
    SignalSpec("vrp_z",             "cross_section", "analysis.cross_section_job",
               "signal_ranks", ("MarketData/Tradier", "yfinance"), "proposed", True,
               "Carr-Wu 2009; AQR 2018 VRP harvest"),
    SignalSpec("vrp_level",         "cross_section", "analysis.cross_section_job",
               "signal_ranks", ("MarketData/Tradier", "yfinance"), "proposed", True, "Carr-Wu 2009"),
    SignalSpec("skew_25d",          "cross_section", "analysis.cross_section_job",
               "signal_ranks", ("MarketData/Tradier",), "proposed", True,
               "Xing-Zhang-Zhao 2010 (-10.9%/yr)"),
    SignalSpec("iv_call_put_spread","cross_section", "analysis.cross_section_job",
               "signal_ranks", ("MarketData/Tradier",), "proposed", True,
               "Cremers-Weinbaum 2010 (~50bp/wk)"),
    SignalSpec("iv_term_slope",     "cross_section", "analysis.cross_section_job",
               "signal_ranks", ("MarketData/Tradier",), "proposed", True,
               "Vasquez 2015 (5.5%/mo)"),
    SignalSpec("momentum_12_1",     "cross_section", "analysis.cross_section_job",
               "signal_ranks", ("yfinance",), "proposed", True,
               "Jegadeesh-Titman 1993 + Daniel-Moskowitz 2016 gate"),
    SignalSpec("whale_flow",        "cross_section", "analysis.whale_flow",
               "signal_ranks", ("MarketData/Tradier",), "proposed", True,
               "Pan-Poteshman 2006 (DIY version)"),
    SignalSpec("short_squeeze",     "cross_section", "analysis.short_squeeze",
               "signal_ranks", ("FMP", "AlphaVantage", "yfinance"), "proposed", True,
               "Drechsler-Drechsler 2014 (squeeze exception)"),
    SignalSpec("reddit_mentions",   "cross_section", "analysis.reddit_sentiment",
               "signal_ranks", ("reddit_json",), "sandbox", False,
               "Boehmer-Jones-Zhang-Zhang 2021 retail flow proxy"),
    SignalSpec("reddit_polarity",   "cross_section", "analysis.reddit_sentiment",
               "signal_ranks", ("reddit_json",), "sandbox", False,
               "Boehmer-Jones-Zhang-Zhang 2021"),
    SignalSpec("insider_cluster",   "cross_section", "analysis.insider_flow",
               "signal_ranks", ("FMP",), "proposed", True,
               "Cohen-Malloy-Pomorski 2012 (6%/yr)"),
    SignalSpec("insider_analyst_combo","cross_section", "analysis.insider_analyst_combo",
               "signal_ranks", ("FMP",), "proposed", True,
               "Cohen-Malloy-Pomorski + Womack 1996"),

    # ── COMPOUND SIGNALS (event-driven, compound_signal_events) ─────────────
    SignalSpec("beat_and_raise_pead", "compound", "agents.compound_signals",
               "compound_signal_events", ("FMP",), "proposed", True,
               "Bernard-Thomas 1989 PEAD"),
    SignalSpec("analyst_revision_cascade","compound", "agents.compound_signals",
               "compound_signal_events", ("FMP",), "proposed", True,
               "ExtractAlpha / Womack 1996"),
    SignalSpec("sector_dispersion",  "compound", "agents.compound_signals",
               "compound_signal_events", ("CBOE COR1M",), "proposed", False,
               "Kakushadze 6.3 — not wired (no COR1M data feed)"),

    # ── MACRO / REGIME OVERLAYS ─────────────────────────────────────────────
    SignalSpec("pre_fomc_drift",    "overlay", "analysis.fomc_drift",
               "briefing_only", ("FOMC_RSS", "yfinance"), "proposed", True,
               "Lucca-Moench 2015 (gated by RV percentile)"),
    SignalSpec("regime_markov_market","overlay", "analysis.regime_markov",
               "briefing_only", ("yfinance", "VIX"), "proposed", True,
               "Hamilton 1989 extended; Roan/RohOnChain 2026 4-state"),
    SignalSpec("regime_markov_per_symbol","overlay", "analysis.regime_markov",
               "briefing_only", ("yfinance",), "proposed", True,
               "per-stock RV-conditioned Markov"),
    SignalSpec("supply_chain_lead_lag","cross_section", "analysis.lead_lag",
               "lead_lag_edges", ("yfinance",), "proposed", True,
               "Cohen-Frazzini 2008 economic links"),

    # ── DNA (per-stock statistical profile) ─────────────────────────────────
    SignalSpec("stock_dna",         "dna", "analysis.stock_dna",
               "feature_store", ("yfinance", "FMP"), "live_full", True,
               "Per-stock behavioral DNA — FDR-corrected per H6"),

    # ── HAND-CODED STRATEGIES (entry/exit rules) ────────────────────────────
    SignalSpec("vrp_harvest",       "strategy", "backtest.strategies.vrp_harvest",
               "backtest_runs", ("MarketData/Tradier", "yfinance"), "proposed", True,
               "Carr-Wu 2009 canonical"),
    SignalSpec("pre_fomc_straddle", "strategy", "backtest.strategies.pre_fomc_straddle",
               "backtest_runs", ("FOMC_RSS", "MarketData/Tradier"), "proposed", True,
               "Lucca-Moench 2015 long-vol implementation"),

    # ── FEATURE-ONLY (surfaced to LLM but NOT in scoring) ───────────────────
    SignalSpec("political_boost",   "feature_only", "data.political",
               "briefing_only", ("OGE",), "feature_only", False,
               "NBER review — weak; demoted per H assessment"),
    SignalSpec("halo_boost",        "feature_only", "analysis.ipo_halo",
               "briefing_only", ("FMP",), "feature_only", False,
               "IPO halo edge 0-5% in literature; demoted H2"),
    SignalSpec("cot_extreme",       "feature_only", "data.cftc_cot",
               "briefing_only", ("CFTC",), "feature_only", False,
               "Specs-max-long/short reversal hint"),
    SignalSpec("smart_money_crowded","feature_only", "data.edgar_13f",
               "briefing_only", ("EDGAR_13F",), "feature_only", False,
               "13F overlap among watched funds"),
    SignalSpec("vix_term_contango", "feature_only", "data.macro_feeds",
               "briefing_only", ("CBOE_delayed_CSV",), "feature_only", False,
               "VIX3M-VIX positive = normal, negative = stress"),
    SignalSpec("yield_curve_slope", "feature_only", "data.macro_feeds",
               "briefing_only", ("FRED",), "feature_only", False, None),
    SignalSpec("hy_credit_spread",  "feature_only", "data.macro_feeds",
               "briefing_only", ("FRED",), "feature_only", False, None),
    SignalSpec("finra_short_volume","feature_only", "data.macro_feeds",
               "briefing_only", ("FINRA",), "feature_only", False, None),
)


# ---------------------------------------------------------------------------
# Trading-stream mapping (O=Options, S=Swing 1-10d, M=Mid 2-8wk, L=Long months)
# Kept as one map and applied via replace() so streams live ON each SignalSpec
# (data-driven for the trackers) without editing all 49 constructor calls.
# ---------------------------------------------------------------------------

_SIGNAL_STREAMS: dict[str, tuple[str, ...]] = {
    # engine
    "macro": ("L",), "calendar": ("S", "L"), "fundamental": ("M", "L"),
    "trend": ("S", "M"), "support_resistance": ("S",), "candles": ("S",),
    "chart_patterns": ("S",), "momentum": ("S", "M"), "iv_analysis": ("O",),
    "options_chain": ("O",), "greeks": ("O",), "trade_structure": ("O",),
    "sentiment": ("S",), "liquidity": ("O", "S"), "risk": ("S", "M"),
    # overlay
    "gex_dex": ("O",), "options_flow": ("O",), "volatility_regime": ("O", "S"),
    "earnings_adj_iv": ("O",),
    # cross_section
    "vrp_z": ("O",), "vrp_level": ("O",), "skew_25d": ("O",),
    "iv_call_put_spread": ("O",), "iv_term_slope": ("O",),
    "momentum_12_1": ("S", "M", "L"), "whale_flow": ("O",),
    "short_squeeze": ("S", "M"), "reddit_mentions": ("S",), "reddit_polarity": ("S",),
    "insider_cluster": ("M", "L"), "insider_analyst_combo": ("M", "L"),
    # compound
    "beat_and_raise_pead": ("S", "M"), "analyst_revision_cascade": ("S", "M"),
    "sector_dispersion": ("M",),
    # macro/regime overlays
    "pre_fomc_drift": ("O", "S"), "regime_markov_market": ("M", "L"),
    "regime_markov_per_symbol": ("S", "M"), "supply_chain_lead_lag": ("S", "M"),
    # dna
    "stock_dna": ("S", "M", "L"),
    # strategy
    "vrp_harvest": ("O",), "pre_fomc_straddle": ("O",),
    # feature_only
    "political_boost": ("M", "L"), "halo_boost": ("S", "M"), "cot_extreme": ("S", "M"),
    "smart_money_crowded": ("L",), "vix_term_contango": ("O",),
    "yield_curve_slope": ("L",), "hy_credit_spread": ("L",), "finra_short_volume": ("S",),
}

# Re-stamp every spec with its streams (frozen dataclass -> replace).
from dataclasses import replace as _replace
REGISTRY = tuple(
    _replace(s, streams=_SIGNAL_STREAMS.get(s.name, ())) for s in REGISTRY
)


def by_name() -> dict[str, SignalSpec]:
    return {s.name: s for s in REGISTRY}


def streams_for(signal_name: str) -> tuple[str, ...]:
    return by_name().get(signal_name, SignalSpec("", "", "", "", ())).streams


# P0 Stage 1.5 — promotion statuses allowed to feed conviction, per operating mode.
MODE_ALLOWED = {
    "backtest":   {"sandbox", "feature_only", "proposed", "paper", "live_small", "live_full"},
    "paper":      {"paper", "live_small", "live_full"},
    "live_small": {"live_small", "live_full"},
    "live_full":  {"live_full"},
}


def contributes_in_mode(signal_name: str, mode: str = "paper") -> bool:
    """
    May this signal feed compute_final_score in the given operating mode?

    - backtest mode evaluates everything raw (returns True).
    - An ungoverned name (not in the registry) defaults to True — it's a core
      component, not an experimental signal under promotion governance.
    - A registry signal contributes iff influences_conviction is True AND its
      promotion_status is permitted for the mode. So in 'paper' mode the 20
      live_full core-engine signals pass while the 18 'proposed' experimental
      signals contribute 0 — the runtime kill-switch GPT/ogo asked for.
    """
    if mode == "backtest":
        return True
    spec = by_name().get(signal_name)
    if spec is None:
        return True
    if not spec.influences_conviction:
        return False
    if spec.promotion_status not in MODE_ALLOWED.get(mode, MODE_ALLOWED["paper"]):
        return False
    # 0620.3 Phase 4.1: also require the EARNED validation ledger, not just the legacy
    # registry label. Many engine signals are live_full by inheritance but none have
    # cleared validation -> the (currently empty) ledger blocks them from live/paper
    # conviction until V promotes them. Backtest already returned True above.
    from scoring.validation_ledger import is_validated
    return is_validated(signal_name)


def by_category(cat: str) -> list[SignalSpec]:
    return [s for s in REGISTRY if s.category == cat]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@dataclass
class AuditFinding:
    severity: str           # 'info' | 'warning' | 'critical'
    signal: str
    issue: str
    detail: str | None = None


@dataclass
class AuditReport:
    as_of: str
    findings: list[AuditFinding] = field(default_factory=list)
    signal_freshness: dict[str, str | None] = field(default_factory=dict)  # name -> ISO date
    promotion_in_db: dict[str, str] = field(default_factory=dict)
    contribution_today: dict[str, float] = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "summary": {
                "total_signals": len(REGISTRY),
                "critical": self.critical_count,
                "warnings": self.warning_count,
                "all_clear": self.critical_count == 0 and self.warning_count == 0,
            },
            "findings": [asdict(f) for f in self.findings],
            "signal_freshness": self.signal_freshness,
            "promotion_in_db": self.promotion_in_db,
            "contribution_today": self.contribution_today,
        }


async def _signal_freshness(session) -> dict[str, str | None]:
    """For each registry signal, find its most recent presence in DB."""
    from sqlalchemy import text
    out: dict[str, str | None] = {}

    # signal_ranks
    result = await session.execute(text("""
        SELECT signal_type, MAX(as_of_date) AS d FROM signal_ranks GROUP BY signal_type
    """))
    for sig_type, d in result.fetchall():
        out[sig_type] = d.isoformat() if d else None

    # factor_ic_scores acts as freshness for engine categories
    result = await session.execute(text("""
        SELECT category, MAX(updated_at) AS d FROM factor_ic_scores GROUP BY category
    """))
    for cat, d in result.fetchall():
        if cat in out:
            continue
        out[cat] = d.date().isoformat() if d else None

    # compound signals
    result = await session.execute(text("""
        SELECT signal_type, MAX(created_at) AS d
        FROM compound_signal_events GROUP BY signal_type
    """))
    for sig_type, d in result.fetchall():
        out[sig_type] = d.date().isoformat() if d else None

    return out


async def _shadow_signals(session) -> set[str]:
    """Signal types present in DB but NOT in the registry."""
    from sqlalchemy import text
    known = {s.name for s in REGISTRY}
    seen: set[str] = set()
    for q in [
        "SELECT DISTINCT signal_type FROM signal_ranks",
        "SELECT DISTINCT signal_type FROM compound_signal_events",
        "SELECT DISTINCT category FROM factor_ic_scores",
    ]:
        try:
            result = await session.execute(text(q))
            for (name,) in result.fetchall():
                if name:
                    seen.add(str(name))
        except Exception:
            continue
    return seen - known


async def _promotion_states(session) -> dict[str, str]:
    """Read live promotion state per category from factor_ic_scores."""
    from sqlalchemy import text
    out: dict[str, str] = {}
    try:
        result = await session.execute(text("""
            SELECT category, signal_status FROM factor_ic_scores
            WHERE regime = 'all'
        """))
        for cat, status in result.fetchall():
            out[cat] = status
    except Exception:
        pass
    return out


async def _conviction_contribution_today(session) -> dict[str, float]:
    """Pull today's contribution per signal type from the latest scan."""
    from sqlalchemy import text
    import orjson
    out: dict[str, float] = {}
    try:
        result = await session.execute(text("""
            SELECT raw_signals FROM analysis_results
            ORDER BY analyzed_at DESC LIMIT 50
        """))
        for (raw,) in result.fetchall():
            if not raw:
                continue
            data = orjson.loads(raw) if isinstance(raw, (str, bytes)) else raw
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, (int, float)):
                        out[key] = out.get(key, 0.0) + float(val)
    except Exception:
        pass
    return out


async def run_audit() -> AuditReport:
    """Main entry point — nightly cron or /signals/audit on demand."""
    from core.database import AsyncSessionLocal

    report = AuditReport(as_of=datetime.utcnow().isoformat())

    async with AsyncSessionLocal() as session:
        freshness = await _signal_freshness(session)
        shadow = await _shadow_signals(session)
        promotion = await _promotion_states(session)
        contribution = await _conviction_contribution_today(session)

    report.signal_freshness = freshness
    report.promotion_in_db = promotion
    report.contribution_today = contribution

    today = date.today()

    # CHECK 1 — registry vs DB freshness
    for spec in REGISTRY:
        if spec.category == "feature_only":
            continue
        last = freshness.get(spec.name)
        if last is None:
            report.findings.append(AuditFinding(
                severity="warning" if spec.promotion_status in ("proposed", "sandbox")
                          else "critical",
                signal=spec.name,
                issue="never_computed",
                detail=f"No DB rows ever; expected freshness within {spec.stale_after_days}d",
            ))
            continue
        try:
            last_d = date.fromisoformat(last[:10])
            stale_days = (today - last_d).days
        except ValueError:
            stale_days = 999
        if stale_days > spec.stale_after_days:
            report.findings.append(AuditFinding(
                severity="critical" if spec.promotion_status.startswith("live") else "warning",
                signal=spec.name,
                issue="stale",
                detail=f"Last seen {last_d}, {stale_days}d ago > {spec.stale_after_days}d stale window",
            ))

    # CHECK 2 — shadow signals in DB
    for name in sorted(shadow):
        report.findings.append(AuditFinding(
            severity="critical", signal=name,
            issue="shadow_signal",
            detail="Signal type present in DB but missing from signal_registry.REGISTRY — "
                   "add it OR delete the rows (contamination risk).",
        ))

    # CHECK 3 — sandbox signals MUST NOT influence conviction
    for spec in REGISTRY:
        if spec.promotion_status == "sandbox" and spec.influences_conviction:
            report.findings.append(AuditFinding(
                severity="critical", signal=spec.name,
                issue="sandbox_leakage",
                detail="Marked sandbox but influences_conviction=True. Set to False until "
                       "the signal earns promotion.",
            ))

    # CHECK 4 — promotion-ladder drift between registry and DB
    for spec in REGISTRY:
        if spec.category != "engine":
            continue
        live = promotion.get(spec.name)
        if live and live != spec.promotion_status:
            report.findings.append(AuditFinding(
                severity="warning", signal=spec.name,
                issue="promotion_drift",
                detail=f"Registry says {spec.promotion_status}, DB says {live}",
            ))

    # CHECK 5 — feature-only signals must NEVER influence conviction
    for spec in REGISTRY:
        if spec.category == "feature_only" and spec.influences_conviction:
            report.findings.append(AuditFinding(
                severity="critical", signal=spec.name,
                issue="feature_only_leakage",
                detail="feature_only signal has influences_conviction=True — fix the registry "
                       "or stop feeding this into compute_final_score.",
            ))

    return report


# ---------------------------------------------------------------------------
# Convenience formatters
# ---------------------------------------------------------------------------

def format_registry_table() -> str:
    """Compact text table for the UI / Discord / CLI."""
    lines = [
        f"{'name':<30} {'cat':<14} {'status':<14} {'influences':<12} {'anchor'}",
        "-" * 110,
    ]
    for s in sorted(REGISTRY, key=lambda x: (x.category, x.name)):
        anchor = (s.research_anchor or "—")[:50]
        lines.append(
            f"{s.name:<30} {s.category:<14} {s.promotion_status:<14} "
            f"{'YES' if s.influences_conviction else 'no':<12} {anchor}"
        )
    return "\n".join(lines)


def format_audit_report(report: AuditReport) -> str:
    lines = [
        f"Signal Audit — {report.as_of}",
        f"  Registry size: {len(REGISTRY)}",
        f"  Critical findings: {report.critical_count}",
        f"  Warnings: {report.warning_count}",
        "",
    ]
    if report.findings:
        lines.append("FINDINGS:")
        for f in report.findings:
            mark = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "•")
            lines.append(f"  {mark} {f.signal:<30} {f.issue:<22} {f.detail or ''}")
    else:
        lines.append("✅ No issues detected.")
    return "\n".join(lines)
