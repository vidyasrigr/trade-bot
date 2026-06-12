"""
FMP (Financial Modeling Prep) MCP Server — exposes fundamentals as MCP tools.

Add to your project's .mcp.json:

  {
    "mcpServers": {
      "fmp": {
        "command": "python",
        "args": ["backend/mcp_servers/fmp_server.py"],
        "env": {
          "FMP_API_KEY": "<your-key>"
        }
      }
    }
  }

Lets you query revenue growth, Piotroski scores, earnings history, and analyst
estimates directly from Claude Code — e.g. "What's NVDA's Piotroski score?"
"""

from __future__ import annotations

import os
import sys

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

API_KEY = os.environ.get("FMP_API_KEY", "")
BASE_URL = "https://financialmodelingprep.com/api/v3"

mcp = FastMCP("fmp-fundamentals")


def _params(**kwargs) -> dict:
    return {"apikey": API_KEY, **kwargs}


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_company_profile(symbol: str) -> dict:
    """
    Get company profile: sector, industry, market cap, description, CEO.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/profile/{symbol.upper()}", params=_params())
        resp.raise_for_status()
        data = resp.json()

    profile = data[0] if (isinstance(data, list) and data) else {}
    return {
        "symbol": profile.get("symbol"),
        "company_name": profile.get("companyName"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "market_cap": profile.get("mktCap"),
        "description": (profile.get("description") or "")[:300],
        "ceo": profile.get("ceo"),
        "employees": profile.get("fullTimeEmployees"),
        "website": profile.get("website"),
    }


@mcp.tool()
async def get_income_statement(symbol: str, quarters: int = 4) -> list[dict]:
    """
    Get quarterly income statements. Returns revenue, gross profit, net income, EPS.
    Use to compute revenue acceleration QoQ and gross margin trends.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/income-statement/{symbol.upper()}",
            params=_params(period="quarter", limit=quarters),
        )
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []

    return [
        {
            "date": q.get("date"),
            "revenue": q.get("revenue"),
            "gross_profit": q.get("grossProfit"),
            "gross_margin_pct": round(q["grossProfit"] / q["revenue"] * 100, 1)
                if q.get("revenue") and q.get("grossProfit") else None,
            "net_income": q.get("netIncome"),
            "eps": q.get("eps"),
            "eps_diluted": q.get("epsdiluted"),
            "operating_income": q.get("operatingIncome"),
        }
        for q in data[:quarters]
    ]


@mcp.tool()
async def get_cash_flow(symbol: str, quarters: int = 4) -> list[dict]:
    """
    Get quarterly cash flow statements. Returns operating CF, capex, free cash flow.
    Use to compute FCF yield and accruals quality.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/cash-flow-statement/{symbol.upper()}",
            params=_params(period="quarter", limit=quarters),
        )
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []

    return [
        {
            "date": q.get("date"),
            "operating_cash_flow": q.get("operatingCashFlow"),
            "capex": q.get("capitalExpenditure"),
            "free_cash_flow": q.get("freeCashFlow"),
            "dividends_paid": q.get("dividendsPaid"),
        }
        for q in data[:quarters]
    ]


@mcp.tool()
async def get_earnings_history(symbol: str, quarters: int = 8) -> list[dict]:
    """
    Get earnings surprise history: actual vs estimate, beat/miss, guidance.
    Use to compute earnings_direction_bias_on_beat for behavioral DNA.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/earnings-surprises/{symbol.upper()}",
            params=_params(),
        )
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []

    results = []
    for e in data[:quarters]:
        actual = e.get("actualEarningResult")
        estimate = e.get("estimatedEarning")
        beat = None
        if actual is not None and estimate is not None and estimate != 0:
            beat = actual > estimate
            surprise_pct = round((actual - estimate) / abs(estimate) * 100, 1)
        else:
            surprise_pct = None

        results.append({
            "date": e.get("date"),
            "actual_eps": actual,
            "estimated_eps": estimate,
            "beat": beat,
            "surprise_pct": surprise_pct,
        })

    return results


@mcp.tool()
async def get_analyst_estimates(symbol: str) -> dict:
    """
    Get forward EPS and revenue consensus estimates + revision trend.
    Use to detect analyst estimate revision cascades.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BASE_URL}/analyst-estimates/{symbol.upper()}",
            params=_params(),
        )
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list) or not data:
        return {"error": "No analyst estimates available"}

    latest = data[0]
    return {
        "symbol": symbol.upper(),
        "fiscal_year": latest.get("date"),
        "estimated_eps_avg": latest.get("estimatedEpsAvg"),
        "estimated_eps_high": latest.get("estimatedEpsHigh"),
        "estimated_eps_low": latest.get("estimatedEpsLow"),
        "estimated_revenue_avg": latest.get("estimatedRevenueAvg"),
        "number_of_analysts": latest.get("numberAnalystEstimatedEps"),
    }


@mcp.tool()
async def get_key_metrics(symbol: str) -> dict:
    """
    Get key financial metrics: PE, PEG, ROE, ROIC, FCF yield, debt/equity.
    Use for LT scoring layer.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BASE_URL}/key-metrics/{symbol.upper()}",
            params=_params(period="annual", limit=1),
        )
        resp.raise_for_status()
        data = resp.json()

    m = data[0] if (isinstance(data, list) and data) else {}
    return {
        "symbol": symbol.upper(),
        "pe_ratio": m.get("peRatio"),
        "peg_ratio": m.get("pegRatio"),
        "price_to_sales": m.get("priceToSalesRatio"),
        "ev_to_ebitda": m.get("enterpriseValueOverEBITDA"),
        "roe": m.get("roe"),
        "roic": m.get("roic"),
        "fcf_yield": m.get("freeCashFlowYield"),
        "debt_to_equity": m.get("debtToEquity"),
        "dividend_yield": m.get("dividendYield"),
        "current_ratio": m.get("currentRatio"),
    }


@mcp.tool()
async def get_insider_trading(symbol: str, limit: int = 20) -> list[dict]:
    """
    Get recent insider trading activity: buys, sells, cluster detection.
    Use to detect the 3+ C-suite insider sell cluster signal.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BASE_URL}/insider-trading",
            params=_params(symbol=symbol.upper(), limit=limit),
        )
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []

    return [
        {
            "date": t.get("transactionDate"),
            "insider_name": t.get("reportingName"),
            "title": t.get("typeOfOwner"),
            "transaction_type": t.get("transactionType"),
            "shares": t.get("securitiesTransacted"),
            "price": t.get("price"),
            "value": t.get("securitiesTransacted", 0) * (t.get("price") or 0),
        }
        for t in data
    ]


if __name__ == "__main__":
    if not API_KEY:
        print("Warning: FMP_API_KEY not set. Set it in env or .mcp.json.", file=sys.stderr)
    mcp.run()
