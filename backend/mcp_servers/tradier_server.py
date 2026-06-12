"""
Tradier MCP Server — exposes live options data as MCP tools for Claude Code.

Add to your project's .mcp.json:

  {
    "mcpServers": {
      "tradier": {
        "command": "python",
        "args": ["backend/mcp_servers/tradier_server.py"],
        "env": {
          "TRADIER_API_KEY": "<your-key>",
          "TRADIER_BASE_URL": "https://sandbox.tradier.com/v1"
        }
      }
    }
  }

This lets you query live options chains, quotes, and IV data directly from
Claude Code during development — e.g. "What's NVDA's IV percentile right now?"
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# ── Config from environment ──────────────────────────────────────────────────
API_KEY = os.environ.get("TRADIER_API_KEY", "")
BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

mcp = FastMCP("tradier-options")


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_quote(symbol: str) -> dict:
    """
    Get real-time quote for a stock symbol.
    Returns: last price, bid, ask, volume, change%, IV (if available).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BASE_URL}/markets/quotes",
            headers=HEADERS,
            params={"symbols": symbol.upper(), "greeks": "true"},
        )
        resp.raise_for_status()
        data = resp.json()
    quotes = data.get("quotes", {}).get("quote", {})
    if isinstance(quotes, list):
        quotes = quotes[0] if quotes else {}
    return {
        "symbol": quotes.get("symbol"),
        "last": quotes.get("last"),
        "bid": quotes.get("bid"),
        "ask": quotes.get("ask"),
        "volume": quotes.get("volume"),
        "change_pct": quotes.get("change_percentage"),
        "week_52_high": quotes.get("week_52_high"),
        "week_52_low": quotes.get("week_52_low"),
    }


@mcp.tool()
async def get_options_chain(symbol: str, expiration: str = "", option_type: str = "") -> list[dict]:
    """
    Get options chain for a symbol.

    Args:
        symbol: Stock ticker (e.g. NVDA)
        expiration: Expiration date in YYYY-MM-DD format. If empty, uses nearest expiration.
        option_type: 'call', 'put', or '' for both.

    Returns list of contracts with strike, bid, ask, delta, IV, OI, volume.
    """
    params: dict = {"symbol": symbol.upper(), "greeks": "true"}
    if expiration:
        params["expiration"] = expiration
    if option_type:
        params["optionType"] = option_type

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/markets/options/chains",
            headers=HEADERS,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    options = data.get("options", {}).get("option", []) or []
    if not isinstance(options, list):
        options = [options]

    return [
        {
            "symbol": o.get("symbol"),
            "option_type": o.get("option_type"),
            "strike": o.get("strike"),
            "expiration_date": o.get("expiration_date"),
            "bid": o.get("bid"),
            "ask": o.get("ask"),
            "volume": o.get("volume"),
            "open_interest": o.get("open_interest"),
            "delta": (o.get("greeks") or {}).get("delta"),
            "gamma": (o.get("greeks") or {}).get("gamma"),
            "theta": (o.get("greeks") or {}).get("theta"),
            "iv": (o.get("greeks") or {}).get("mid_iv"),
        }
        for o in options
    ]


@mcp.tool()
async def get_expirations(symbol: str) -> list[str]:
    """
    Get all available expiration dates for a symbol's options.
    Returns list of dates in YYYY-MM-DD format, sorted ascending.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BASE_URL}/markets/options/expirations",
            headers=HEADERS,
            params={"symbol": symbol.upper(), "includeAllRoots": "true"},
        )
        resp.raise_for_status()
        data = resp.json()

    dates = data.get("expirations", {}).get("date", []) or []
    if isinstance(dates, str):
        dates = [dates]
    return sorted(dates)


@mcp.tool()
async def get_options_volume_summary(symbol: str) -> dict:
    """
    Get a volume/OI summary for a symbol's options — useful for detecting unusual activity.
    Returns total call/put volume, put/call ratio, and high-OI strikes.
    """
    expirations = await get_expirations(symbol)
    if not expirations:
        return {"error": "No expirations found"}

    nearest = expirations[0]
    chain = await get_options_chain(symbol, expiration=nearest)

    call_vol = sum(c.get("volume") or 0 for c in chain if c.get("option_type") == "call")
    put_vol  = sum(c.get("volume") or 0 for c in chain if c.get("option_type") == "put")
    call_oi  = sum(c.get("open_interest") or 0 for c in chain if c.get("option_type") == "call")
    put_oi   = sum(c.get("open_interest") or 0 for c in chain if c.get("option_type") == "put")

    total_vol = call_vol + put_vol
    pcr = round(put_vol / call_vol, 2) if call_vol > 0 else None

    # Top 3 strikes by volume
    top_by_vol = sorted(chain, key=lambda c: c.get("volume") or 0, reverse=True)[:3]

    return {
        "symbol": symbol.upper(),
        "expiration": nearest,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "total_volume": total_vol,
        "put_call_ratio": pcr,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "top_volume_strikes": [
            {"strike": c["strike"], "type": c["option_type"], "volume": c["volume"]}
            for c in top_by_vol
        ],
    }


@mcp.tool()
async def get_historical_volatility(symbol: str, days: int = 30) -> dict:
    """
    Get historical price data to compute realized volatility.
    Returns close prices for the last N days and annualized HV.
    """
    import math

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/markets/history",
            headers=HEADERS,
            params={"symbol": symbol.upper(), "interval": "daily"},
        )
        resp.raise_for_status()
        data = resp.json()

    history = data.get("history", {}).get("day", []) or []
    if not isinstance(history, list):
        history = [history]

    closes = [float(d["close"]) for d in history[-days:] if d.get("close")]
    if len(closes) < 5:
        return {"error": "Insufficient price history"}

    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    hv_daily = math.sqrt(variance)
    hv_annual = round(hv_daily * math.sqrt(252) * 100, 1)

    return {
        "symbol": symbol.upper(),
        "hv_30d_annualized_pct": hv_annual,
        "days_used": len(closes),
        "last_close": closes[-1],
    }


if __name__ == "__main__":
    if not API_KEY:
        print("Warning: TRADIER_API_KEY not set. Set it in env or .env file.", file=sys.stderr)
    mcp.run()
