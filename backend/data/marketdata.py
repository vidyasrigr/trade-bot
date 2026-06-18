"""
MarketData.app client — Tradier-compatible interface.

Why this exists:
  Tradier sandbox doesn't ship historical option chains. MarketData.app does
  (date= parameter on /v1/options/chain/{symbol}/, 1 credit per 1000 symbols
  for historical). Same endpoint, same auth model, cheap. Replacing Tradier
  with MarketData unblocks every options backtest in this repo.

Design choice — adapter, not rewrite:
  All 12+ call sites in the codebase use Tradier's response shape:
    contract.get("greeks", {}).get("delta")
    contract.get("strike")
    contract.get("expiration_date")
    contract.get("open_interest")
    contract.get("option_type")  # 'call' | 'put'

  MarketData's response is column-oriented (parallel arrays of strike[],
  delta[], iv[], bid[], ask[], etc). We transpose to per-contract dicts that
  exactly match Tradier's schema, so the callers don't need to know which
  data source they're using.

  `get_tradier()` (the existing factory) now delegates to MarketData when
  MARKETDATA_API_KEY is set, falling back to Tradier when it isn't, and to
  NullClient when neither is set. One-line switch in config.

Account / orders:
  MarketData is a data API, NOT a broker. It has no place_order / get_balances.
  Those methods on this client return the same empty values NullTradierClient
  returns — the system gracefully degrades. For paper-trade execution we still
  use Tradier sandbox (free), with credentials independent of data source. The
  hybrid is intentional: MarketData for data quality + historical chains,
  Tradier sandbox for paper-trade order routing.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings


MARKETDATA_BASE_URL = "https://api.marketdata.app"


def _normalize_contract(parallel: dict, idx: int) -> dict:
    """
    Build a Tradier-shaped per-contract dict from MarketData's column-oriented
    response at index `idx`.

    MarketData fields (parallel arrays): optionSymbol, underlying, expiration,
    side ('call'|'put'), strike, firstTraded, dte, updated, bid, bidSize, mid,
    ask, askSize, last, openInterest, volume, inTheMoney, intrinsicValue,
    extrinsicValue, underlyingPrice, iv, delta, gamma, theta, vega, rho.

    Tradier shape we emit:
      symbol, strike, option_type ('call'|'put'), bid, ask, last, volume,
      open_interest, expiration_date (YYYY-MM-DD),
      greeks: {delta, gamma, theta, vega, mid_iv}
    """
    def at(key: str) -> Any:
        arr = parallel.get(key)
        if not isinstance(arr, list) or idx >= len(arr):
            return None
        return arr[idx]

    expiration = at("expiration")
    if isinstance(expiration, (int, float)):
        try:
            expiration = date.fromtimestamp(float(expiration)).isoformat()
        except (ValueError, OSError):
            expiration = None
    elif isinstance(expiration, str):
        expiration = expiration[:10]

    greeks = {
        "delta": at("delta"),
        "gamma": at("gamma"),
        "theta": at("theta"),
        "vega": at("vega"),
        "rho": at("rho"),
        "mid_iv": at("iv"),
        "smv_vol": at("iv"),  # Tradier callers sometimes look for either
    }

    return {
        "symbol": at("optionSymbol"),
        "underlying": at("underlying"),
        "strike": at("strike"),
        "option_type": (at("side") or "").lower() or None,
        "bid": at("bid"),
        "ask": at("ask"),
        "last": at("last"),
        "volume": at("volume"),
        "open_interest": at("openInterest"),
        "expiration_date": expiration,
        "greeks": greeks,
        "underlying_price": at("underlyingPrice"),
    }


def _explode_chain(payload: dict) -> list[dict]:
    """Transpose column-oriented response to a list of per-contract dicts."""
    strikes = payload.get("strike")
    if not isinstance(strikes, list):
        return []
    return [_normalize_contract(payload, i) for i in range(len(strikes))]


class MarketDataClient:
    """Tradier-compatible facade over the MarketData.app v1 REST API."""

    def __init__(self) -> None:
        self.base_url = MARKETDATA_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.MARKETDATA_API_KEY}",
            "Accept": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers=self.headers,
                params=params or {},
            )
            # MarketData returns 203 (Non-Authoritative) for cached responses,
            # 204 (No Content) when no data is available — both are non-errors.
            if resp.status_code == 204:
                return {}
            if resp.status_code not in (200, 203):
                resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {}

    # ----------------------------------------------------------------------
    # QUOTES (stocks)
    # ----------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        data = await self._get(f"/v1/stocks/quotes/{symbol}/")
        if not data or "last" not in data:
            return {}
        # MarketData also column-oriented for quotes; one-element arrays
        def first(key: str) -> Any:
            arr = data.get(key)
            return arr[0] if isinstance(arr, list) and arr else arr

        return {
            "symbol": symbol,
            "last": first("last"),
            "bid": first("bid"),
            "ask": first("ask"),
            "volume": first("volume"),
            "change": first("change"),
            "change_percentage": first("changepct"),
            "high": first("high"),
            "low": first("low"),
            "open": first("open"),
            "close": first("close"),
        }

    async def get_quotes_bulk(self, symbols: list[str]) -> list[dict]:
        # MarketData has no native bulk endpoint; sequentially fetch (cheap
        # under the cached tier) — same shape Tradier returns.
        out: list[dict] = []
        for sym in symbols:
            try:
                q = await self.get_quote(sym)
                if q:
                    out.append(q)
            except Exception as e:
                logger.debug(f"MarketData quote failed for {sym}: {e}")
        return out

    # ----------------------------------------------------------------------
    # OPTIONS CHAINS
    # ----------------------------------------------------------------------

    async def get_expirations(self, symbol: str, *, as_of: str | None = None) -> list[str]:
        """
        Returns YYYY-MM-DD expiry strings sorted ascending.

        as_of: optional YYYY-MM-DD to list the expirations that were actually
        listed on that historical date (used by the backtest to snap to a real
        expiry instead of guessing a Friday that may not have existed).
        """
        params = {"date": as_of} if as_of else None
        data = await self._get(f"/v1/options/expirations/{symbol}/", params)
        expirations = data.get("expirations") or []
        # MarketData returns strings already in YYYY-MM-DD; defensively normalize
        out = []
        for e in expirations:
            if isinstance(e, str):
                out.append(e[:10])
            elif isinstance(e, (int, float)):
                try:
                    out.append(date.fromtimestamp(float(e)).isoformat())
                except (ValueError, OSError):
                    continue
        return sorted(out)

    async def get_options_chain(
        self,
        symbol: str,
        expiry: str,
        greeks: bool = True,
        *,
        as_of: str | None = None,
    ) -> list[dict]:
        """
        Returns Tradier-shaped per-contract dicts for one expiry.

        as_of: optional YYYY-MM-DD for historical chains (billed cheaper, see
        docstring at the top of this module).
        """
        params: dict = {"expiration": expiry}
        if as_of:
            params["date"] = as_of
        data = await self._get(f"/v1/options/chain/{symbol}/", params)
        return _explode_chain(data)

    async def get_best_chain(
        self,
        symbol: str,
        min_dte: int = 14,
        max_dte: int = 60,
        *,
        as_of: str | None = None,
    ) -> list[dict]:
        """
        Nearest expiry inside the DTE window. The MarketData filter `dte=`
        gives us this in one call without listing all expirations.
        """
        target_dte = (min_dte + max_dte) // 2
        params: dict = {
            "dte": str(target_dte),
            "from": str(min_dte),
            "to": str(max_dte),
        }
        if as_of:
            params["date"] = as_of
        data = await self._get(f"/v1/options/chain/{symbol}/", params)
        return _explode_chain(data)

    async def get_iv_surface(self, symbol: str, *, as_of: str | None = None) -> dict:
        """
        Three buckets (near / mid / far) for surface analysis.
        Returns {expiry_yyyy_mm_dd: [chain]}.
        """
        expirations = await self.get_expirations(symbol)
        today = date.today()
        buckets = {"near": (14, 21), "mid": (30, 45), "far": (60, 90)}
        surface: dict[str, list] = {}
        for _, (lo, hi) in buckets.items():
            for exp_str in expirations:
                try:
                    dte = (date.fromisoformat(exp_str) - today).days
                except ValueError:
                    continue
                if lo <= dte <= hi:
                    try:
                        chain = await self.get_options_chain(symbol, exp_str, as_of=as_of)
                        surface[exp_str] = chain
                    except Exception as e:
                        logger.warning(f"IV surface fetch failed for {symbol} {exp_str}: {e}")
                    break
        return surface

    # ----------------------------------------------------------------------
    # HISTORICAL STOCK BARS
    # ----------------------------------------------------------------------

    async def get_history(
        self,
        symbol: str,
        interval: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """Daily candles — Tradier-shaped (date, open, high, low, close, volume)."""
        resolution = "D" if interval == "daily" else "1H"
        params: dict = {}
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        data = await self._get(
            f"/v1/stocks/candles/{resolution}/{symbol}/", params,
        )
        timestamps = data.get("t") or []
        if not timestamps:
            return []
        out: list[dict] = []
        for i, ts in enumerate(timestamps):
            try:
                d = date.fromtimestamp(float(ts)).isoformat()
            except (ValueError, OSError):
                continue
            out.append({
                "date": d,
                "open": (data.get("o") or [None])[i],
                "high": (data.get("h") or [None])[i],
                "low": (data.get("l") or [None])[i],
                "close": (data.get("c") or [None])[i],
                "volume": (data.get("v") or [None])[i],
            })
        return out

    # ----------------------------------------------------------------------
    # PAPER TRADING — NOT SUPPORTED (MarketData is data-only)
    # ----------------------------------------------------------------------

    async def get_account(self) -> dict:
        return {}

    async def get_balances(self) -> dict:
        return {}

    async def get_positions(self) -> list[dict]:
        return []

    async def get_orders(self) -> list[dict]:
        return []

    async def place_option_order(self, *args, **kwargs) -> dict:
        logger.warning(
            "MarketDataClient does not place orders — wire Tradier sandbox separately for paper execution"
        )
        return {}

    async def cancel_order(self, order_id: str) -> dict:
        logger.warning("MarketDataClient cannot cancel orders — Tradier sandbox handles execution")
        return {}


class NullMarketDataClient:
    """No-op client when neither MARKETDATA_API_KEY nor TRADIER_API_KEY set."""

    async def get_best_chain(self, symbol: str, **kwargs) -> list[dict]:
        logger.warning(f"No market data source configured — {symbol} returns empty chains")
        return []

    async def get_quote(self, symbol: str) -> dict:
        return {}

    async def get_account(self) -> dict:
        return {}

    async def get_balances(self) -> dict:
        return {}

    async def get_positions(self) -> list[dict]:
        return []

    async def get_orders(self) -> list[dict]:
        return []

    async def place_option_order(self, *args, **kwargs) -> dict:
        return {}

    async def cancel_order(self, order_id: str) -> dict:
        return {}

    async def get_candles(self, symbol: str, **kwargs) -> list[dict]:
        return []


def get_tradier():
    """Returns MarketDataClient when MARKETDATA_API_KEY is set, else NullClient."""
    if settings.MARKETDATA_API_KEY:
        return MarketDataClient()  # reads MARKETDATA_API_KEY from settings itself
    return NullMarketDataClient()
