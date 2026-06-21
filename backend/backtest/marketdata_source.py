"""
MarketData historical options source — production backtest data + PERSISTENT cache.

Drop-in replacement for `BlackScholesOptionsSource`. Uses MarketData.app's
historical chain endpoint (date= parameter on /v1/options/chain/) to pull
real bid/ask/IV/greeks for past dates.

PERSISTENT DISK CACHE (added 2026-06-16):
  Every chain pulled from MarketData is written to a partitioned Parquet store
  at `data/marketdata_cache/{symbol}/{expiry}/{day}.parquet`. Subsequent reads
  for the same (symbol, expiry, day) hit disk for free — no credits, no HTTP.

  Why this matters:
    - Re-running the same backtest = $0 (huge: parameter sweeps become free)
    - Adding a new signal that needs the same chain window = $0
    - The data is yours forever, independent of your MarketData subscription
    - V can cancel Starter ($30/mo) after validation and still re-test signals

  Layout:
    data/marketdata_cache/
        SPY/
            2024-06-21/
                2020-05-01.parquet   ← chain @ that expiry, as_of date
                2020-05-02.parquet
                ...
        NVDA/
            ...

  Each parquet stores: strike, option_type, bid, ask, mid_iv, delta, gamma,
  theta, vega, open_interest, volume — i.e. *everything* the chain returned,
  not just what the current backtest needed. So a NEW signal that needs IV or
  greeks gets them for free from cache.

  Empty chains (204 responses) are recorded as zero-row parquets — preventing
  re-fetches that we already know are empty.

CHAIN-LEVEL CACHE (in-memory, in-process):
  Same as before — keeps hot chains in RAM during a single backtest run.
  This sits ABOVE the disk cache: check memory first, then disk, then API.

Cost model:
  1st run on a window:  pays MarketData credits + writes to disk
  2nd run on same window: zero credits, reads from disk in <1ms per chain
  New signal on same window: zero credits
  New signal on new window: pays credits for new dates only
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
from loguru import logger

from backtest.engine import Leg, OptionQuote


DEFAULT_CACHE_ROOT = Path(os.environ.get("MARKETDATA_CACHE_ROOT",
                                           "data/marketdata_cache"))


def _safe(seg: str) -> str:
    """Filesystem-safe path segment."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in seg)


class MarketDataHistoricalSource:
    """
    Async OptionsSource with THREE-LAYER caching:
      1. In-memory (per-process, fastest)
      2. On-disk Parquet (persistent across runs, free re-reads)
      3. MarketData API (paid, last resort)
    """

    def __init__(self, client=None, *, calendar_symbol: str = "SPY",
                 cache_root: Path | str | None = None):
        if client is None:
            from data.marketdata import MarketDataClient
            client = MarketDataClient()
        self.client = client
        self.calendar_symbol = calendar_symbol
        self.cache_root = Path(cache_root) if cache_root else DEFAULT_CACHE_ROOT
        self.cache_root.mkdir(parents=True, exist_ok=True)

        # In-memory cache: (symbol, expiry, day) -> dict[(strike, right), OptionQuote] | None
        self._chain_cache: dict[tuple, dict[tuple, OptionQuote] | None] = {}
        self._chain_locks: dict[tuple, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._calendar_cache: dict[str, list[date]] = {}

        # Diagnostics — costs and hit-rate
        self._api_fetches = 0
        self._disk_hits = 0
        self._memory_hits = 0
        # Expirations leak fix (2026-06-18): get_expirations was a billed call
        # made per candidate, invisible to api_fetches. Cache + count it.
        self._expirations_mem: dict[tuple, list[str]] = {}
        self._expirations_api = 0
        self._expirations_disk = 0

    @property
    def stats(self) -> dict:
        total = self._api_fetches + self._disk_hits + self._memory_hits
        return {
            "api_fetches": self._api_fetches,
            "disk_hits": self._disk_hits,
            "memory_hits": self._memory_hits,
            "expirations_api": self._expirations_api,
            "expirations_disk": self._expirations_disk,
            "total_lookups": total,
            "disk_hit_rate": (self._disk_hits / total) if total else 0.0,
        }

    # ---- expirations: cache-dir resolution + disk-cached API (leak fix) -----

    def cached_expiries(self, underlying: str, day: date) -> list[date]:
        """
        Expiries whose chain for `day` is ALREADY on disk — read from the cache
        layout {underlying}/{expiry}/{day}.parquet. Resolving expiry from here
        costs ZERO API calls, which is the whole point: re-running a backtest on
        cached data must not re-hit get_expirations (that was the credit leak).
        """
        base = self.cache_root / _safe(underlying)
        if not base.exists():
            return []
        out: list[date] = []
        target = f"{day.isoformat()}.parquet"
        for expdir in base.iterdir():
            if expdir.is_dir() and (expdir / target).exists():
                try:
                    out.append(date.fromisoformat(expdir.name))
                except ValueError:
                    continue
        return sorted(out)

    async def expirations(self, underlying: str, as_of: date) -> list[str]:
        """
        Listed expiries as-of a date, with memory -> disk -> API caching and an
        honest credit counter. Use this instead of client.get_expirations so the
        call is cached (re-runs are free) and visible in stats.
        """
        key = (underlying, as_of)
        if key in self._expirations_mem:
            return self._expirations_mem[key]

        disk = (self.cache_root / "_expirations" / _safe(underlying)
                / f"{as_of.isoformat()}.json")
        if disk.exists():
            try:
                import json
                exps = json.loads(disk.read_text())
                self._expirations_disk += 1
                self._expirations_mem[key] = exps
                return exps
            except Exception as e:
                logger.debug(f"expirations disk read failed {disk}: {e}")

        try:
            exps = await self.client.get_expirations(underlying, as_of=as_of.isoformat())
            self._expirations_api += 1
        except Exception as e:
            logger.debug(f"get_expirations failed {underlying}/{as_of}: {e}")
            return []  # do NOT cache a failure — let it retry next run
        # Only persist NON-empty results. An empty list usually means a rate-limit
        # (429) truncation, not "no expiries"; caching it would block a faithful
        # re-fetch once the daily limit resets.
        if exps:
            try:
                import json
                disk.parent.mkdir(parents=True, exist_ok=True)
                disk.write_text(json.dumps(exps))
            except Exception as e:
                logger.debug(f"expirations disk write failed {disk}: {e}")
            self._expirations_mem[key] = exps
        return exps

    # ---- OptionsSource protocol -----------------------------------------

    async def eod_quote(self, underlying: str, leg: Leg, day: date) -> OptionQuote | None:
        chain_key = (underlying, leg.expiry, day)
        contract_key = (float(leg.strike), leg.right.upper())

        if chain_key in self._chain_cache:
            self._memory_hits += 1
            cached = self._chain_cache[chain_key]
            return cached.get(contract_key) if cached else None

        cached = await self._load_chain(underlying, leg.expiry, day)
        return cached.get(contract_key) if cached else None

    async def trading_days(self, underlying: str, start: date, end: date) -> list[date]:
        """SPY history is the canonical trading calendar — cached on disk."""
        cal_file = self.cache_root / "_calendar" / f"{_safe(self.calendar_symbol)}.parquet"
        if self.calendar_symbol not in self._calendar_cache:
            if cal_file.exists():
                df = pd.read_parquet(cal_file)
                self._calendar_cache[self.calendar_symbol] = sorted(
                    pd.to_datetime(df["date"]).dt.date.tolist()
                )
            else:
                try:
                    bars = await self.client.get_history(
                        self.calendar_symbol, interval="daily",
                        start="2017-01-01", end=date.today().isoformat(),
                    )
                    days = sorted({date.fromisoformat(b["date"]) for b in bars})
                    self._calendar_cache[self.calendar_symbol] = days
                    cal_file.parent.mkdir(parents=True, exist_ok=True)
                    pd.DataFrame({"date": days}).to_parquet(cal_file, index=False)
                except Exception as e:
                    logger.debug(f"trading_days SPY fetch failed: {e}")
                    self._calendar_cache[self.calendar_symbol] = []
        cal = self._calendar_cache.get(self.calendar_symbol, [])
        return [d for d in cal if start <= d <= end]

    # ---- internals ------------------------------------------------------

    def _chain_path(self, underlying: str, expiry: date, day: date) -> Path:
        return (self.cache_root / _safe(underlying) / expiry.isoformat()
                / f"{day.isoformat()}.parquet")

    async def _load_chain(self, underlying: str, expiry: date,
                            day: date) -> dict[tuple, OptionQuote] | None:
        """
        Three-tier load: memory → disk → API. Locks per (underlying, expiry, day)
        so concurrent backtests don't duplicate fetches.
        """
        chain_key = (underlying, expiry, day)
        async with self._chain_locks[chain_key]:
            if chain_key in self._chain_cache:
                self._memory_hits += 1
                return self._chain_cache[chain_key]

            # Tier 2 — disk
            disk_path = self._chain_path(underlying, expiry, day)
            if disk_path.exists():
                try:
                    df = pd.read_parquet(disk_path)
                    parsed = self._parse_dataframe(df)
                    self._chain_cache[chain_key] = parsed or None
                    self._disk_hits += 1
                    return parsed or None
                except Exception as e:
                    logger.debug(f"disk read failed {disk_path}: {e}")

            # Tier 3 — API
            try:
                chain = await self.client.get_options_chain(
                    underlying, expiry=expiry.isoformat(), as_of=day.isoformat(),
                )
                self._api_fetches += 1
            except Exception as e:
                # 0620.2 P0.1: do NOT write an empty sentinel on a TRANSIENT failure
                # (429/5xx/timeout/network/parse after the client's retries). Poisoning
                # the cache with a false no-data here is the same class of silent-corruption
                # bug as the credit leak. Return None and let a later run refetch faithfully.
                logger.debug(f"MarketData historical chain fetch failed "
                             f"{underlying}/{expiry}/{day}: {e}")
                self._chain_cache[chain_key] = None
                return None

            # Success path: an empty `chain` here is TRUE no-data (204/empty content),
            # so persisting an empty parquet is a legitimate "we asked, nothing listed"
            # marker — distinct from the transient-failure path above.
            parsed, df_to_write = self._parse_api_response(chain)
            self._write_chain(disk_path, df_to_write)
            self._chain_cache[chain_key] = parsed if parsed else None
            return parsed or None

    def _parse_api_response(self, chain: list[dict]) -> tuple[dict[tuple, OptionQuote], pd.DataFrame]:
        """
        Return both the engine's OptionQuote dict AND a full DataFrame for
        disk persistence. The DataFrame keeps every field MarketData returned —
        so future signals that need IV, greeks, OI, volume can read them for free.
        """
        rows: list[dict] = []
        quotes: dict[tuple, OptionQuote] = {}
        for c in chain or []:
            try:
                strike = float(c.get("strike") or 0)
                right = (c.get("option_type") or "").upper()[:1] or None
                bid = float(c.get("bid") or 0)
                ask = float(c.get("ask") or 0)
                if not strike or right not in {"C", "P"} or ask <= 0:
                    continue
                greeks = c.get("greeks") or {}
                rows.append({
                    "strike": strike, "option_type": right,
                    "bid": max(0.0, bid), "ask": ask,
                    "mid_iv": float(greeks.get("mid_iv") or 0),
                    "delta": float(greeks.get("delta") or 0),
                    "gamma": float(greeks.get("gamma") or 0),
                    "theta": float(greeks.get("theta") or 0),
                    "vega": float(greeks.get("vega") or 0),
                    "rho": float(greeks.get("rho") or 0),
                    "open_interest": int(c.get("open_interest") or 0),
                    "volume": int(c.get("volume") or 0),
                    "underlying_price": float(c.get("underlying_price") or 0),
                })
                quotes[(strike, right)] = OptionQuote(bid=max(0.0, bid), ask=ask)
            except (TypeError, ValueError):
                continue
        return quotes, pd.DataFrame(rows)

    def _parse_dataframe(self, df: pd.DataFrame) -> dict[tuple, OptionQuote]:
        """Reverse: build OptionQuotes from a cached parquet."""
        out: dict[tuple, OptionQuote] = {}
        if df.empty:
            return out
        for r in df.itertuples(index=False):
            try:
                strike = float(r.strike)
                right = str(r.option_type).upper()[:1]
                bid = float(r.bid)
                ask = float(r.ask)
                if not strike or right not in {"C", "P"} or ask <= 0:
                    continue
                out[(strike, right)] = OptionQuote(bid=max(0.0, bid), ask=ask)
            except (AttributeError, TypeError, ValueError):
                continue
        return out

    def _write_chain(self, path: Path, df: pd.DataFrame) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
        except Exception as e:
            logger.debug(f"chain disk write failed {path}: {e}")

    def _write_empty(self, path: Path) -> None:
        """Persist a 'we tried, it was empty' marker so we don't re-fetch."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=["strike", "option_type", "bid", "ask"]).to_parquet(
                path, index=False,
            )
        except Exception as e:
            logger.debug(f"empty chain marker write failed {path}: {e}")
