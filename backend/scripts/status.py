"""
Status check — tells you what's actually done vs pending.

Reads filesystem + env to detect:
  - Which API keys are set
  - Which migrations exist on disk
  - Which Python deps are installed
  - Which feature-store snapshots exist
  - Which ML model artifacts exist
  - Whether the signal registry passes audit
  - Whether Discord is wired

Usage:
    cd backend && python3 -m scripts.status
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
DIM = "\033[2m"


def mark(ok: bool, partial: bool = False) -> str:
    if partial:
        return f"{YELLOW}~{RESET}"
    return f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"


def section(title: str):
    print(f"\n{title}")
    print("─" * len(title))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_env_keys() -> list[tuple[str, bool, str]]:
    must_have = [
        ("ANTHROPIC_API_KEY", "Claude — required for strategist + analysts"),
        ("FRED_API_KEY",       "Macro data — yield curve, HY, TGA"),
        ("MARKETDATA_API_KEY", "Options chains live + historical — CRITICAL"),
        ("FMP_API_KEY",        "Fundamentals + insiders + earnings — CRITICAL"),
        ("ALPHA_VANTAGE_API_KEY", "Backup for sentiment + short interest"),
    ]
    optional = [
        ("DISCORD_WEBHOOK_URL", "Signal contamination + briefing alerts"),
        ("NEWS_API_KEY",        "Optional — falls back to RSS feeds"),
        ("SECRET_KEY",          "Change from default before deploy"),
    ]
    print(f"{DIM}required keys{RESET}")
    out = []
    for key, desc in must_have:
        is_set = bool(os.environ.get(key))
        print(f"  {mark(is_set)} {key:<25} {DIM}{desc}{RESET}")
        out.append((key, is_set, desc))
    print(f"{DIM}optional keys{RESET}")
    for key, desc in optional:
        is_set = bool(os.environ.get(key))
        # Treat SECRET_KEY default as not-set
        if key == "SECRET_KEY":
            val = os.environ.get(key, "")
            is_set = is_set and "change-this" not in val
        print(f"  {mark(is_set, partial=not is_set)} {key:<25} {DIM}{desc}{RESET}")
        out.append((key, is_set, desc))
    return out


def check_python_deps() -> list[tuple[str, bool]]:
    deps = [
        ("duckdb",           "Feature store"),
        ("lightgbm",         "Cross-sectional ranker"),
        ("feedparser",       "FOMC RSS + news"),
        ("redis",            "Cache layer"),
        ("pytest",           "Test suite"),
        ("pytest_asyncio",   "Async tests"),
        ("httpx",            "HTTP client"),
        ("pandas",           "Data wrangling"),
        ("numpy",            "Numerics"),
        ("scipy",            "Stats"),
        ("pydantic_settings","Config"),
        ("sqlalchemy",       "DB"),
        ("loguru",           "Logging"),
        ("anthropic",        "Claude SDK"),
        ("orjson",           "Fast JSON"),
        ("yfinance",         "Backup price history"),
    ]
    optional = [
        ("cupy",             "GPU acceleration for sweeper (optional)"),
        ("pandas_ta",        "Indicator library"),
    ]
    out = []
    for name, desc in deps:
        try:
            importlib.import_module(name)
            ok = True
        except ImportError:
            ok = False
        print(f"  {mark(ok)} {name:<22} {DIM}{desc}{RESET}")
        out.append((name, ok))
    print(f"{DIM}optional{RESET}")
    for name, desc in optional:
        try:
            importlib.import_module(name)
            ok = True
        except ImportError:
            ok = False
        print(f"  {mark(ok, partial=not ok)} {name:<22} {DIM}{desc}{RESET}")
    return out


def check_migrations() -> tuple[int, int]:
    mig_dir = Path("db/migrations")
    if not mig_dir.exists():
        mig_dir = Path("backend/db/migrations")
    files = sorted(mig_dir.glob("*.sql")) if mig_dir.exists() else []
    print(f"  {mark(len(files) >= 10)} {len(files)} migration files on disk")
    for f in files:
        print(f"    {DIM}{f.name}{RESET}")
    print(f"  {YELLOW}~{RESET} actual applied state requires DB connection — verify with:")
    print(f"    {DIM}psql $DATABASE_URL -c \"\\dt\"{RESET}")
    return len(files), 16


def check_feature_store():
    fs_root = Path(os.environ.get("FEATURE_STORE_ROOT", "data/feature_store"))
    if not fs_root.exists():
        print(f"  {mark(False)} no feature store directory yet — run backfill")
        return 0
    snapshots = list(fs_root.glob("*/snapshot_*.parquet"))
    has_enough = len(snapshots) >= 60
    print(f"  {mark(has_enough, partial=0 < len(snapshots) < 60)} "
          f"{len(snapshots)} daily snapshots "
          f"{DIM}(need 60+ to train LightGBM){RESET}")
    if not has_enough:
        print(f"    {DIM}Run: python3 -m scripts.backfill_feature_store --days 700{RESET}")


def check_model_artifacts():
    models_dir = Path(os.environ.get("MODELS_DIR", "data/models"))
    if not models_dir.exists():
        print(f"  {mark(False)} no LightGBM models trained yet")
        return
    artifacts = list(models_dir.glob("*.pkl"))
    print(f"  {mark(len(artifacts) >= 3)} "
          f"{len(artifacts)} ranker artifacts on disk")
    for h in (5, 21, 63):
        present = any(f"_h{h}_" in p.name for p in artifacts)
        print(f"    {mark(present)} horizon h={h}")


def check_signal_registry():
    try:
        sys.path.insert(0, ".")
        from scoring.signal_registry import REGISTRY
        leaks = [s.name for s in REGISTRY
                 if s.promotion_status in ("sandbox", "feature_only")
                 and s.influences_conviction]
        print(f"  {mark(len(REGISTRY) > 0)} {len(REGISTRY)} signals registered")
        print(f"  {mark(not leaks)} no sandbox/feature_only leakage into conviction")
        if leaks:
            print(f"    {RED}LEAKAGE: {leaks}{RESET}")
    except Exception as e:
        print(f"  {mark(False)} registry import failed: {e}")


def check_tests():
    tests_dir = Path("tests")
    if not tests_dir.exists():
        tests_dir = Path("backend/tests")
    test_files = list(tests_dir.glob("test_*.py")) if tests_dir.exists() else []
    print(f"  {mark(len(test_files) >= 10)} {len(test_files)} test modules on disk")
    print(f"    {DIM}Run: python3 -m pytest tests/ -q{RESET}")


def check_pending_md():
    pending = Path("../misc/PENDING.md")
    if not pending.exists():
        pending = Path("misc/PENDING.md")
    if pending.exists():
        text = pending.read_text()
        unchecked = text.count("- [ ]")
        checked = text.count("- [x]")
        total = unchecked + checked
        print(f"  PENDING.md: {checked}/{total} items checked off")
        print(f"  {DIM}Open: misc/PENDING.md{RESET}")
    else:
        print(f"  {mark(False)} misc/PENDING.md not found")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"\n{'═' * 60}")
    print(f"  System status check")
    print(f"{'═' * 60}")

    section("🔑 API keys")
    key_results = check_env_keys()
    critical_missing = sum(
        1 for k, ok, _ in key_results[:5]  # first 5 are critical
        if not ok
    )

    section("📦 Python dependencies")
    check_python_deps()

    section("🗃️  Database migrations")
    n_files, n_expected = check_migrations()

    section("📊 Feature store")
    check_feature_store()

    section("🤖 ML model artifacts")
    check_model_artifacts()

    section("🎯 Signal registry")
    check_signal_registry()

    section("🧪 Tests")
    check_tests()

    section("📋 Manual checklist")
    check_pending_md()

    print()
    if critical_missing > 0:
        print(f"{RED}⚠ {critical_missing} critical API keys missing — system will mostly degrade silently.{RESET}")
        return 1
    print(f"{GREEN}✓ Critical keys present. Run `pytest tests/` then `scripts/audit_signals` to verify health.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
