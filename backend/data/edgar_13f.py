"""
SEC EDGAR 13F holdings — quarterly hedge fund / institutional positioning.

13F filings disclose long-equity positions of institutions with ≥$100M AUM,
filed within 45 days of quarter end. Data is lagged but real: shows what
sophisticated money owned a quarter ago. Useful for:
  - Crowded-trade detection (when N>50 funds hold same name)
  - Sector tilt by smart-money cohort
  - Fund-vs-fund concentration ranking

EDGAR exposes 13F via two paths:
  1. Forms feed: cik-by-cik latest filing
  2. Full-text search at efts.sec.gov

We use the per-filer holdings JSON published by efts (no auth required) and
cache aggressively — these only change once a quarter.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


EDGAR_HEADERS = {
    "User-Agent": settings.edgar_user_agent if hasattr(settings, "edgar_user_agent")
                   else "TradeResearch (vidyasrigr@gmail.com)",
    "Accept": "application/json",
}

# Watched filers — top 20 most-followed funds by long alpha generation
WATCHED_CIKS = {
    "berkshire_hathaway": "0001067983",
    "scion_asset_mgmt": "0001649339",
    "pershing_square": "0001336528",
    "tiger_global": "0001167483",
    "renaissance_tech": "0001037389",
    "two_sigma": "0001179392",
    "citadel": "0001423053",
    "millennium": "0001273087",
    "appaloosa": "0001656456",
    "third_point": "0001040273",
    "viking_global": "0001103804",
    "lone_pine": "0001061165",
    "coatue_mgmt": "0001135730",
    "balyasny_asset": "0001162008",
    "soros_fund": "0001029160",
    "elliott_mgmt": "0001048445",
    "icahn_capital": "0000921669",
    "duquesne_family": "0001536411",
    "greenlight_capital": "0001079114",
    "baupost_group": "0001061768",
}

CACHE_TTL_S = 86400 * 30  # 30 days — 13Fs land quarterly


@dataclass
class HoldingRow:
    cik: str
    fund_name: str
    quarter_end: date
    symbol: str
    name: str
    value_usd: int
    shares: int


async def _fetch_latest_13f(cik: str, fund_name: str) -> list[HoldingRow]:
    cache_key = f"13f:{cik}"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        rows = orjson.loads(cached)
        return [HoldingRow(**{**r, "quarter_end": date.fromisoformat(r["quarter_end"])})
                for r in rows]

    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(submissions_url, headers=EDGAR_HEADERS)
        if resp.status_code != 200:
            return []
        sub_json = resp.json()
    except Exception as e:
        logger.debug(f"13F submissions fetch failed for {fund_name}: {e}")
        return []

    recent = sub_json.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    accession_numbers = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []
    filing_dates = recent.get("filingDate") or []

    accession, primary_doc, filing_date = None, None, None
    for f, acc, doc, fd in zip(forms, accession_numbers, primary_docs, filing_dates):
        if f.startswith("13F-HR") and not f.endswith("/A"):
            accession, primary_doc, filing_date = acc, doc, fd
            break
    if accession is None:
        return []

    accession_clean = accession.replace("-", "")
    cik_int = str(int(cik))
    info_table_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/"
        f"{primary_doc}".replace(".htm", "").replace(".html", "") + ".xml"
    )
    # The actual info table is a separate XML, often named "infotable.xml" or similar.
    # Resolve by hitting the filing index JSON.
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/index.json"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            idx = (await client.get(index_url, headers=EDGAR_HEADERS)).json()
        items = idx.get("directory", {}).get("item", [])
        info_table = next(
            (it for it in items
             if it.get("name", "").lower().endswith(".xml") and "info" in it.get("name", "").lower()),
            None,
        )
        if info_table is None:
            return []
        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/"
            f"{info_table['name']}"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            xml_resp = await client.get(xml_url, headers=EDGAR_HEADERS)
        if xml_resp.status_code != 200:
            return []
        xml_text = xml_resp.text
    except Exception as e:
        logger.debug(f"13F info-table fetch failed for {fund_name}: {e}")
        return []

    # Lightweight XML parse — 13F-HR is well-defined and small enough we can
    # use stdlib without pulling lxml just for this.
    import xml.etree.ElementTree as ET
    try:
        tree = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.debug(f"13F xml parse failed for {fund_name}: {e}")
        return []

    ns = {"i": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}

    try:
        quarter_end = date.fromisoformat(filing_date) if filing_date else date.today()
    except ValueError:
        quarter_end = date.today()

    out: list[HoldingRow] = []
    for entry in tree.findall("i:infoTable", ns) or tree.findall(".//{*}infoTable"):
        def _t(tag):
            el = entry.find(f"i:{tag}", ns) or entry.find(f".//{{*}}{tag}")
            return el.text if el is not None else None
        try:
            ticker = (_t("nameOfIssuer") or "").strip().upper()
            cusip = (_t("cusip") or "").strip()
            value = int(float(_t("value") or 0))
            shares_el = entry.find("i:shrsOrPrnAmt", ns) or entry.find(".//{*}shrsOrPrnAmt")
            if shares_el is not None:
                shares_text = (shares_el.find("i:sshPrnamt", ns) or
                                shares_el.find(".//{*}sshPrnamt"))
                shares = int(float(shares_text.text)) if shares_text is not None else 0
            else:
                shares = 0
        except (ValueError, TypeError, AttributeError):
            continue
        # value column in 13Fs is in thousands of USD — normalize
        value_usd = value * 1000
        out.append(HoldingRow(
            cik=cik, fund_name=fund_name, quarter_end=quarter_end,
            symbol=ticker[:5],  # 13F uses issuer name not tickers; downstream needs CUSIP->ticker
            name=ticker, value_usd=value_usd, shares=shares,
        ))

    if out:
        import orjson
        await cache_set(cache_key, orjson.dumps([{
            "cik": h.cik, "fund_name": h.fund_name,
            "quarter_end": h.quarter_end.isoformat(), "symbol": h.symbol,
            "name": h.name, "value_usd": h.value_usd, "shares": h.shares,
        } for h in out]).decode(), ttl=CACHE_TTL_S)
    return out


async def crowded_names() -> Counter:
    """Across all watched funds: how many funds own each issuer name."""
    all_holdings = await asyncio.gather(
        *[_fetch_latest_13f(cik, name) for name, cik in WATCHED_CIKS.items()],
        return_exceptions=True,
    )
    counter: Counter = Counter()
    for fund_holdings in all_holdings:
        if isinstance(fund_holdings, Exception):
            continue
        for h in fund_holdings or []:
            counter[h.name] += 1
    return counter


async def top_smart_money_picks(limit: int = 25) -> list[tuple[str, int]]:
    """Names held by the most smart-money funds — crowded-trade alert."""
    counter = await crowded_names()
    return counter.most_common(limit)
