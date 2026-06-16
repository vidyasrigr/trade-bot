"""
ThetaData client — historical options data via the local ThetaTerminal.

ThetaTerminal is a Java app that must be running locally (default port 25510)
with an active ThetaData subscription (Standard tier recommended, ~$80/mo).
Docs: https://http-docs.thetadata.us/

Until the terminal is running, every call raises ThetaTerminalNotRunning with
setup instructions — no silent fallbacks, no fabricated data.

ASYNC: every HTTP call uses httpx.AsyncClient. The previous sync httpx.get()
blocked the asyncio event loop for every quote fetched during a backtest.
"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
from loguru import logger

from core.config import settings

_BASE = getattr(settings, "THETADATA_BASE_URL", None) or "http://127.0.0.1:25510"


class ThetaTerminalNotRunning(RuntimeError):
    def __init__(self, base: str):
        super().__init__(
            f"ThetaTerminal is not reachable at {base}. "
            "Historical options data requires: (1) a ThetaData subscription "
            "(thetadata.net, Standard tier), (2) ThetaTerminal.jar running locally. "
            "Start it with: java -jar ThetaTerminal.jar <email> <password>"
        )


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


class ThetaDataClient:
    def __init__(self, base: str = _BASE, timeout: float = 60.0):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, base_url=self.base)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict) -> dict:
        client = await self._http()
        try:
            resp = await client.get(path, params=params)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise ThetaTerminalNotRunning(self.base) from e
        resp.raise_for_status()
        data = resp.json()
        header = data.get("header", {})
        if header.get("error_type") not in (None, "null"):
            raise RuntimeError(f"ThetaData error: {header.get('error_type')} — {header.get('error_msg')}")
        return data

    def _to_df(self, data: dict) -> pd.DataFrame:
        cols = data.get("header", {}).get("format") or []
        rows = data.get("response") or []
        return pd.DataFrame(rows, columns=cols)

    async def expirations(self, root: str) -> list[date]:
        data = await self._get("/v2/list/expirations", {"root": root})
        out = []
        for row in data.get("response") or []:
            s = str(row)
            out.append(date(int(s[:4]), int(s[4:6]), int(s[6:8])))
        return sorted(out)

    async def strikes(self, root: str, exp: date) -> list[float]:
        data = await self._get("/v2/list/strikes", {"root": root, "exp": _fmt(exp)})
        # ThetaData strikes are in 1/10 cent units
        return sorted(float(row) / 1000.0 for row in (data.get("response") or []))

    async def option_eod(self, root: str, exp: date, strike: float, right: str,
                          start: date, end: date) -> pd.DataFrame:
        """
        Daily EOD quotes/OHLC for one contract.
        right: 'C' or 'P'. Returns df with ThetaData's column format, with
        normalized lowercase columns and a 'quote_date' date column added.
        """
        data = await self._get("/v2/hist/option/eod", {
            "root": root,
            "exp": _fmt(exp),
            "strike": str(int(round(strike * 1000))),
            "right": right.upper(),
            "start_date": _fmt(start),
            "end_date": _fmt(end),
        })
        df = self._to_df(data)
        if df.empty:
            return df
        df.columns = [str(c).lower() for c in df.columns]
        if "date" in df.columns:
            df["quote_date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d").dt.date
        return df


_client: ThetaDataClient | None = None


def get_thetadata() -> ThetaDataClient:
    global _client
    if _client is None:
        _client = ThetaDataClient()
    return _client
