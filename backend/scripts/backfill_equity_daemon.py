"""
Equity OHLCV backfill daemon (CONSTRAINT_RUNBOOK Track 3 substrate).

Pulls daily OHLCV ONE SYMBOL AT A TIME (paced) into backtest.equity_cache so the
free-signal sweep reads close panels from disk instead of bulk yfinance (which
rate-limits / IP-bans on large universes). Idempotent, resumable.

Universe: a curated LIQUID set (the chain-bank CORE_200 list + the curated
get_full_universe), NOT the alphabetical directory head (that is illiquid junk).
True ADV-ranked 500/1000/2000 breadth is a later expansion (needs volume ranking).

Run:
  python -m scripts.backfill_equity_daemon --once         # one pass over the liquid set
  python -m scripts.backfill_equity_daemon                 # forever, refresh daily
  python -m scripts.backfill_equity_daemon --pace 1.0      # seconds between pulls
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

from backtest import equity_cache

PROGRESS_LOG = equity_cache.EQUITY_DIR / "_backfill_progress.log"


def liquid_universe() -> list[str]:
    """Real ADV-ranked liquid set: top-500 by ADV + get_full_universe + chain cache.

    ADV ranking from the banked FMP profiles (free). Falls back to the curated lists
    if profiles are unavailable. This is the substrate for the momentum multi-slice
    depth (top-100/250/500) and the breadth sweep.
    """
    from data.scanner import get_full_universe
    names: list[str] = []
    try:
        from backtest.liquid_universe import liquid_top
        names += liquid_top(500)
    except Exception:
        from scripts.chain_bank_daemon import CORE_200
        names += list(CORE_200)
    names += list(get_full_universe())
    # include any name we have chains for (so options XS panels resolve from cache)
    try:
        from backtest.marketdata_source import DEFAULT_CACHE_ROOT
        names += [d.name for d in DEFAULT_CACHE_ROOT.iterdir()
                  if d.is_dir() and not d.name.startswith("_")]
    except Exception:
        pass
    return list(dict.fromkeys(names))


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_LOG, "a") as f:
        f.write(line + "\n")
    logger.info(msg)


def run(once: bool, pace: float, prefer_marketdata: bool = False) -> None:
    universe = liquid_universe()
    while True:
        todo = [s for s in universe if not equity_cache.fresh(s)]
        _log(f"backfill pass: {len(universe)} liquid names, {len(todo)} stale/missing "
             f"(source={'marketdata' if prefer_marketdata else 'yfinance->marketdata'})")
        ok = fail = 0
        for i, sym in enumerate(todo, 1):
            if equity_cache.backfill_symbol(sym, prefer_marketdata=prefer_marketdata):
                ok += 1
            else:
                fail += 1
            if i % 25 == 0:
                _log(f"  progress {i}/{len(todo)}  ok={ok} fail={fail}")
            time.sleep(pace)
        _log(f"pass complete: ok={ok} fail={fail} cached_total="
             f"{len(list(equity_cache.EQUITY_DIR.glob('*.parquet')))}")
        if once:
            return
        time.sleep(6 * 3600)   # refresh twice a day


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--pace", type=float, default=1.2, help="seconds between pulls")
    ap.add_argument("--marketdata", action="store_true",
                    help="skip yfinance, use MarketData get_history (when yfinance throttled)")
    args = ap.parse_args()
    run(args.once, args.pace, prefer_marketdata=args.marketdata)


if __name__ == "__main__":
    main()
