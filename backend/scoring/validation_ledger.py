"""
Validation ledger (0620.3 Phase 4.1) — the EARNED list of signals allowed to drive
live/paper conviction. Distinct from signal_registry.promotion_status, which carries
LEGACY labels (many engine signals are `live_full` by inheritance, none validated).

A signal influences conviction only if: registry allows AND mode allows AND it is in
THIS ledger. The ledger is populated only when V promotes a signal after it clears the
validation bar. It is currently EMPTY — nothing has cleared — so in paper/live modes no
signal drives conviction yet. That is the intended safety posture before paper kickoff.

Source: data/validation_ledger.json -> {"validated": ["signal_name", ...]}. Absent/empty
-> no validated signals. Backtest mode bypasses the ledger (research evaluates raw).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LEDGER_FILE = Path(__file__).resolve().parents[2] / "data" / "validation_ledger.json"


@lru_cache(maxsize=1)
def validated_signals() -> frozenset[str]:
    if not LEDGER_FILE.exists():
        return frozenset()
    try:
        data = json.loads(LEDGER_FILE.read_text())
        return frozenset(data.get("validated", []))
    except Exception:
        return frozenset()


def is_validated(signal_name: str) -> bool:
    return signal_name in validated_signals()


def reload_ledger():
    validated_signals.cache_clear()
