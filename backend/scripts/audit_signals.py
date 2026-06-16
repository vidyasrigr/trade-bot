"""
On-demand signal audit + registry inspection.

Usage:
  python3 -m scripts.audit_signals              # run audit, print findings
  python3 -m scripts.audit_signals --registry   # print full registry table
  python3 -m scripts.audit_signals --json       # JSON output for piping

This is the operational complement to /api/signals/audit — useful when you're
in a terminal and want to know "is anything contaminating the trader prompt
right now?" without spinning up the frontend.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _main(args) -> int:
    from scoring.signal_registry import (
        REGISTRY, run_audit, format_audit_report, format_registry_table,
    )

    if args.registry:
        print(format_registry_table())
        print(f"\nTotal: {len(REGISTRY)} registered signals")
        return 0

    report = await run_audit()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(format_audit_report(report))
        print()
        print(f"Promotion states in DB: {report.promotion_in_db}")

    return 1 if report.critical_count > 0 else 0


def main():
    parser = argparse.ArgumentParser(description="Signal registry + audit CLI")
    parser.add_argument("--registry", action="store_true",
                        help="Print full registry table (no audit)")
    parser.add_argument("--json", action="store_true",
                        help="Emit audit findings as JSON")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
