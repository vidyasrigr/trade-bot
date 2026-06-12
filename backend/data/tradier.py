"""
Tradier API client — options chains, quotes, paper trade execution.
All calls go to the sandbox URL (https://sandbox.tradier.com/v1).
"""

from datetime import date, timedelta
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import settings


class TradierClient:
    def __init__(self):
        self.base_url = settings.TRADIER_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.TRADIER_API_KEY}",
            "Accept": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers=self.headers,
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _post(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers=self.headers,
                data=data,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # QUOTES
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        data = await self._get("/markets/quotes", {"symbols": symbol, "greeks": "false"})
        quotes = data.get("quotes", {}).get("quote", {})
        if isinstance(quotes, list):
            return quotes[0] if quotes else {}
        return quotes

    async def get_quotes_bulk(self, symbols: list[str]) -> list[dict]:
        symbols_str = ",".join(symbols)
        data = await self._get("/markets/quotes", {"symbols": symbols_str, "greeks": "false"})
        quotes = data.get("quotes", {}).get("quote", [])
        if isinstance(quotes, dict):
            quotes = [quotes]
        return quotes or []

    # ------------------------------------------------------------------
    # OPTIONS CHAINS
    # ------------------------------------------------------------------

    async def get_expirations(self, symbol: str) -> list[str]:
        """Return available expiry dates as YYYY-MM-DD strings."""
        data = await self._get(
            "/markets/options/expirations",
            {"symbol": symbol, "includeAllRoots": "true", "strikes": "false"},
        )
        dates = data.get("expirations", {}).get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        return sorted(dates or [])

    async def get_options_chain(
        self, symbol: str, expiry: str, greeks: bool = True
    ) -> list[dict]:
        """
        Returns list of option contracts for one expiry.
        Each dict has: symbol, strike, option_type, bid, ask, last, volume,
        open_interest, greeks (delta, gamma, theta, vega, rho, mid_iv).
        """
        data = await self._get(
            "/markets/options/chains",
            {"symbol": symbol, "expiration": expiry, "greeks": str(greeks).lower()},
        )
        options = data.get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]
        return options or []

    async def get_best_chain(
        self,
        symbol: str,
        min_dte: int = 14,
        max_dte: int = 60,
    ) -> list[dict]:
        """Return the nearest expiry within the DTE window with adequate liquidity."""
        expirations = await self.get_expirations(symbol)
        today = date.today()
        target_expiries = []
        for exp_str in expirations:
            exp_date = date.fromisoformat(exp_str)
            dte = (exp_date - today).days
            if min_dte <= dte <= max_dte:
                target_expiries.append(exp_str)

        if not target_expiries:
            logger.warning(f"No expirations in {min_dte}-{max_dte} DTE range for {symbol}")
            return []

        # Return nearest qualifying expiry
        return await self.get_options_chain(symbol, target_expiries[0])

    async def get_iv_surface(self, symbol: str) -> dict:
        """
        Fetches chains for 3 expirations to build an IV surface:
        near (14-21 DTE), mid (30-45 DTE), far (60-90 DTE).
        Returns {expiry: [chain contracts]}.
        """
        expirations = await self.get_expirations(symbol)
        today = date.today()
        buckets = {"near": (14, 21), "mid": (30, 45), "far": (60, 90)}
        surface: dict[str, list] = {}

        for bucket, (lo, hi) in buckets.items():
            for exp_str in expirations:
                dte = (date.fromisoformat(exp_str) - today).days
                if lo <= dte <= hi:
                    try:
                        chain = await self.get_options_chain(symbol, exp_str)
                        surface[exp_str] = chain
                    except Exception as e:
                        logger.warning(f"IV surface fetch failed for {symbol} {exp_str}: {e}")
                    break

        return surface

    # ------------------------------------------------------------------
    # PAPER TRADING
    # ------------------------------------------------------------------

    async def get_account(self) -> dict:
        data = await self._get("/user/profile")
        return data.get("profile", {})

    async def get_balances(self) -> dict:
        accounts = await self.get_account()
        account_id = self._extract_account_id(accounts)
        if not account_id:
            return {}
        data = await self._get(f"/accounts/{account_id}/balances")
        return data.get("balances", {})

    async def get_positions(self) -> list[dict]:
        accounts = await self.get_account()
        account_id = self._extract_account_id(accounts)
        if not account_id:
            return []
        data = await self._get(f"/accounts/{account_id}/positions")
        positions = data.get("positions", {}).get("position", [])
        if isinstance(positions, dict):
            positions = [positions]
        return positions or []

    async def get_orders(self) -> list[dict]:
        accounts = await self.get_account()
        account_id = self._extract_account_id(accounts)
        if not account_id:
            return []
        data = await self._get(f"/accounts/{account_id}/orders")
        orders = data.get("orders", {}).get("order", [])
        if isinstance(orders, dict):
            orders = [orders]
        return orders or []

    async def place_option_order(
        self,
        symbol: str,
        option_symbol: str,
        side: str,           # 'buy_to_open', 'sell_to_open', 'buy_to_close', 'sell_to_close'
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
        duration: str = "day",
    ) -> dict:
        """Place an options order in Tradier sandbox."""
        accounts = await self.get_account()
        account_id = self._extract_account_id(accounts)
        if not account_id:
            raise ValueError("No Tradier account found")

        payload = {
            "class": "option",
            "symbol": symbol,
            "option_symbol": option_symbol,
            "side": side,
            "quantity": str(quantity),
            "type": order_type,
            "duration": duration,
        }
        if limit_price is not None:
            payload["price"] = str(round(limit_price, 2))

        data = await self._post(f"/accounts/{account_id}/orders", payload)
        return data.get("order", {})

    async def cancel_order(self, order_id: str) -> dict:
        accounts = await self.get_account()
        account_id = self._extract_account_id(accounts)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{self.base_url}/accounts/{account_id}/orders/{order_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # HISTORICAL DATA (Tradier provides up to 10 years)
    # ------------------------------------------------------------------

    async def get_history(
        self,
        symbol: str,
        interval: str = "daily",
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        params: dict = {"symbol": symbol, "interval": interval}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        data = await self._get("/markets/history", params)
        history = data.get("history", {})
        if not history or history == "null":
            return []
        days = history.get("day", [])
        if isinstance(days, dict):
            days = [days]
        return days or []

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _extract_account_id(self, profile: dict) -> str | None:
        account = profile.get("account", {})
        if isinstance(account, list):
            account = account[0] if account else {}
        return account.get("account_number")


_client: TradierClient | None = None


def get_tradier() -> TradierClient:
    global _client
    if _client is None:
        _client = TradierClient()
    return _client
