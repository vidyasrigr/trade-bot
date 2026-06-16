"""
/api/signals — registry + audit endpoints.

Exposes:
  GET  /api/signals             — list every signal in the registry + status
  GET  /api/signals/audit       — run the nightly audit on demand, returns JSON
  GET  /api/signals/audit/text  — text version for CLI / Discord
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse


def get_router() -> APIRouter:
    router = APIRouter()

    @router.get("/signals")
    async def list_signals() -> dict:
        from scoring.signal_registry import REGISTRY, by_category
        return {
            "count": len(REGISTRY),
            "by_category": {
                cat: [asdict(s) for s in by_category(cat)]
                for cat in sorted({s.category for s in REGISTRY})
            },
            "signals": [asdict(s) for s in REGISTRY],
        }

    @router.get("/signals/audit")
    async def audit() -> dict:
        from scoring.signal_registry import run_audit
        report = await run_audit()
        return report.to_dict()

    @router.get("/signals/audit/text", response_class=PlainTextResponse)
    async def audit_text() -> str:
        from scoring.signal_registry import run_audit, format_audit_report
        report = await run_audit()
        return format_audit_report(report)

    @router.get("/signals/registry/text", response_class=PlainTextResponse)
    async def registry_text() -> str:
        from scoring.signal_registry import format_registry_table
        return format_registry_table()

    return router
