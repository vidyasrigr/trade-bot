All Phase K wired. Compiles clean. Self-checks confirm:

  - 49 signals registered across 7 categories
  - All 2 sandbox signals (Reddit) correctly isolated (influences_conviction=False)
  - All 8 feature-only signals (political, halo, COT, 13F, VIX TS, FRED macros, FINRA SV) correctly isolated

  Phase K shipped

  ┌────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┐
  │            File            │                                       Purpose                                       │
  ├────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
  │                            │ The truth table — every signal declared with category, module, data sources,        │
  │ scoring/signal_registry.py │ promotion status, research anchor, and influences_conviction flag. 5 audit checks:  │
  │                            │ stale data, shadow signals in DB, sandbox leakage, promotion drift, feature-only    │
  │                            │ leakage.                                                                            │
  ├────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
  │                            │ Three endpoints: GET /api/signals (full registry JSON), GET /api/signals/audit      │
  │ api/signals.py             │ (live audit JSON), GET /api/signals/audit/text (CLI/Discord-friendly), GET          │
  │                            │ /api/signals/registry/text (compact text table)                                     │
  ├────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
  │ scripts/audit_signals.py   │ CLI: python3 -m scripts.audit_signals (exits 1 on critical findings, so usable in   │
  │                            │ CI/cron)                                                                            │
  ├────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────┤
  │ Nightly job                │ 11 PM ET — runs audit, fires Discord 🔴 alert on critical findings                  │
  └────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┘

  Answers to your specific concerns

  #1: Are the H7 advanced free signals (FRED, VIX TS, FINRA SV, CFTC, 13F) categorized correctly?
  Yes — all 8 are explicitly category="feature_only" with influences_conviction=False (verified by
  format_registry_table() above). They appear in the strategist prompt as context but never score into
  compute_final_score. The audit will fail loudly if anyone changes that.

  Reddit sentiment (mentions + polarity) is promotion_status="sandbox", also isolated — observe-only until DSR backtest
  clears it.

  Promotion path is now machine-enforced:
  - proposed → built but never validated → can influence conviction (with caveats logged)
  - paper → backtest-validated, paper-trading 4 weeks
  - live_small / live_full → trades with sizing weight
  - sandbox → observation only, must have influences_conviction=False
  - feature_only → never scored, just context
  
  If you flip a sandbox signal to live without backtest evidence, the nightly audit fires 🔴 and Discord alerts you.

  #2: Sweeper output — example block above is accurate. Real output goes to backtest_runs table; promotable variants
  persist, sandboxed stay in-memory until you decide.

  #3: Backtest window — corrected. Use 2018-01-01 → 2024-12-31 train fold, 2025-01-01 → 2026-06-15 out-of-sample fold.
  Any signal that wins the train fold but loses out-of-sample is overfit and goes to sandbox automatically.

  How you'll use this day-to-day

  # See the full signal taxonomy
  python3 -m scripts.audit_signals --registry

  # Run audit (exits non-zero on critical findings — usable in CI)
  python3 -m scripts.audit_signals

  # JSON output for dashboards / piping
  python3 -m scripts.audit_signals --json | jq .summary

  # From the UI / API
  curl http://localhost:8000/api/signals/audit/text

  The Discord webhook fires on every critical finding nightly — so contamination can't quietly creep in.

  Next single action recommendation: subscribe to MarketData → run python3 -m scripts.backfill_feature_store --days 700
  → write a sweep grid for VRP harvest → run await run_sweep(...) → audit the results. The system now tells you what's
  noise, what's signal, what's leaking, and what's earned its keep.