"""
Tiered news pipeline:
RSS feeds + SEC EDGAR 8-K → Ollama filter (kill 90% noise) → Claude (top 5-10%)

Sources (all free, no API key required):
- Yahoo Finance RSS per-symbol (best per-ticker coverage)
- Reuters business news RSS
- MarketWatch top stories RSS
- Benzinga markets RSS
- SEC EDGAR 8-K filings (free API)
"""

import asyncio
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from loguru import logger

from core.config import settings
from core.redis_client import cache_get, cache_set


# ---------------------------------------------------------------------------
# RSS feed URLs
# ---------------------------------------------------------------------------

# Per-symbol: Yahoo Finance — best single-source for stock-specific news
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

# Market-wide general feeds
MARKET_RSS_FEEDS = [
    ("reuters",       "https://feeds.reuters.com/reuters/businessNews"),
    ("marketwatch",   "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("benzinga",      "https://www.benzinga.com/markets/news.xml"),
    ("cnbc",          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"),
]

# Macro / central bank feeds — Fed statements, FOMC minutes, Treasury, BLS
MACRO_RSS_FEEDS = [
    # Federal Reserve: all press releases (rate decisions, speeches, minutes)
    ("fed_press",  "https://www.federalreserve.gov/feeds/press_all.xml"),
    # FOMC statements only
    ("fomc",       "https://www.federalreserve.gov/feeds/fomc.xml"),
    # US Treasury press releases (debt ceiling, auction results, sanctions)
    ("treasury",   "https://home.treasury.gov/system/files/RSS.xml"),
    # White House briefing room (executive orders, tariff announcements)
    ("whitehouse", "https://www.whitehouse.gov/feed/"),
]


def _parse_rss_date(date_str: str) -> str:
    """Parse RSS date string to ISO format. Returns empty string on failure."""
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return date_str


class NewsAggregator:

    async def get_news_for_symbols(self, symbols: list[str], hours_back: int = 24) -> list[dict]:
        """
        Fetch news from all sources for a list of symbols.
        Returns raw items (not yet filtered).

        Sources:
          - Yahoo Finance RSS per symbol (stock-specific)
          - Reuters, MarketWatch, Benzinga, CNBC (general market)
          - Federal Reserve, FOMC, Treasury, White House (macro/policy)
          - SEC EDGAR 8-K filings
        """
        tasks = [self._fetch_sec_8k(hours_back)]

        # Per-symbol Yahoo Finance RSS (up to 8 symbols to avoid rate limits)
        for sym in symbols[:8]:
            tasks.append(self._fetch_yahoo_rss(sym))

        # General market + macro feeds in parallel
        tasks.append(self._fetch_market_rss(hours_back))
        tasks.append(self._fetch_macro_rss(hours_back))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_items: list[dict] = []
        for batch in results:
            if isinstance(batch, Exception):
                logger.debug(f"News source failed: {batch}")
                continue
            all_items.extend(batch or [])

        return all_items

    async def _fetch_yahoo_rss(self, symbol: str) -> list[dict]:
        """Yahoo Finance RSS for a specific ticker — free, no key, excellent coverage."""
        cache_key = f"yahoo_rss:{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            return orjson.loads(cached)

        url = YAHOO_RSS.format(symbol=symbol)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "OptionsTradingBot/0.1 vidyasrigr@gmail.com"},
                    follow_redirects=True,
                )
                raw_xml = resp.text

            feed = feedparser.parse(raw_xml)
            items = []
            for entry in feed.entries[:15]:
                items.append({
                    "source": "yahoo_finance",
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "published_at": _parse_rss_date(entry.get("published", "")),
                    "summary": entry.get("summary", ""),
                    "symbol": symbol,
                })
        except Exception as e:
            logger.debug(f"Yahoo RSS failed for {symbol}: {e}")
            items = []

        import orjson
        await cache_set(cache_key, orjson.dumps(items).decode(), ttl=1800)
        return items

    async def _fetch_market_rss(self, hours_back: int) -> list[dict]:
        """General financial news from multiple RSS feeds."""
        cache_key = f"market_rss:{hours_back}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            return orjson.loads(cached)

        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        all_items: list[dict] = []

        async def _fetch_one(source_name: str, feed_url: str) -> list[dict]:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        feed_url,
                        headers={"User-Agent": "OptionsTradingBot/0.1 vidyasrigr@gmail.com"},
                        follow_redirects=True,
                    )
                    raw_xml = resp.text
                feed = feedparser.parse(raw_xml)
                items = []
                for entry in feed.entries[:20]:
                    pub_str = _parse_rss_date(entry.get("published", ""))
                    items.append({
                        "source": source_name,
                        "headline": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "published_at": pub_str,
                        "summary": entry.get("summary", ""),
                        "symbol": None,
                    })
                return items
            except Exception as e:
                logger.debug(f"RSS feed {source_name} failed: {e}")
                return []

        results = await asyncio.gather(*[_fetch_one(name, url) for name, url in MARKET_RSS_FEEDS])
        for batch in results:
            all_items.extend(batch)

        import orjson
        await cache_set(cache_key, orjson.dumps(all_items).decode(), ttl=1800)
        return all_items

    async def _fetch_macro_rss(self, hours_back: int) -> list[dict]:
        """
        Macro / central bank news: Fed press releases, FOMC statements,
        Treasury announcements, White House briefing room.
        These are tagged source=macro_* so Ollama can flag high-urgency
        policy events (rate decisions, tariffs, executive orders).
        """
        cache_key = f"macro_rss:{hours_back}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            return orjson.loads(cached)

        all_items: list[dict] = []

        async def _fetch_one(source_name: str, feed_url: str) -> list[dict]:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        feed_url,
                        headers={"User-Agent": "OptionsTradingBot/0.1 vidyasrigr@gmail.com"},
                        follow_redirects=True,
                    )
                    raw_xml = resp.text
                feed = feedparser.parse(raw_xml)
                items = []
                for entry in feed.entries[:10]:
                    items.append({
                        "source": source_name,
                        "headline": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "published_at": _parse_rss_date(entry.get("published", "")),
                        "summary": entry.get("summary", ""),
                        "symbol": None,
                        "is_macro": True,
                    })
                return items
            except Exception as e:
                logger.debug(f"Macro RSS feed {source_name} failed: {e}")
                return []

        results = await asyncio.gather(*[_fetch_one(name, url) for name, url in MACRO_RSS_FEEDS])
        for batch in results:
            all_items.extend(batch)

        import orjson
        await cache_set(cache_key, orjson.dumps(all_items).decode(), ttl=1800)
        return all_items

    async def _fetch_sec_8k(self, hours_back: int) -> list[dict]:
        """Poll SEC EDGAR for recent 8-K filings (material events)."""
        cache_key = f"sec_8k:{hours_back}"
        cached = await cache_get(cache_key)
        if cached:
            import orjson
            return orjson.loads(cached)

        from_dt = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%d")
        to_dt = datetime.utcnow().strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={"forms": "8-K", "dateRange": "custom", "startdt": from_dt, "enddt": to_dt},
                    headers={"User-Agent": "OptionsTradingBot/0.1 vidyasrigr@gmail.com"},
                )
                resp.raise_for_status()
                data = resp.json()

            hits = data.get("hits", {}).get("hits", [])
            items = []
            for h in hits[:30]:
                src = h.get("_source", {})
                items.append({
                    "source": "sec_8k",
                    "headline": src.get("file_date", "") + " 8-K: " + src.get("entity_name", ""),
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id', '')}&type=8-K",
                    "published_at": src.get("file_date", ""),
                    "summary": src.get("period_of_report", ""),
                    "symbol": None,
                    "cik": src.get("entity_id"),
                    "company_name": src.get("entity_name", ""),
                })
        except Exception as e:
            logger.debug(f"SEC EDGAR fetch failed: {e}")
            items = []

        import orjson
        await cache_set(cache_key, orjson.dumps(items).decode(), ttl=1800)
        return items


class OllamaNewsFilter:
    """
    Uses local Ollama llama3.1:8b to filter raw news.
    Kills 90% of noise, keeps only actionable signals.
    Claude never touches this stage.
    """

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_CHAT_MODEL

    async def filter_and_tag(self, items: list[dict], watchlist: list[str]) -> list[dict]:
        """
        For each news item, asks Ollama:
        - Is this relevant to any stock in watchlist? (Y/N + which ticker)
        - Sentiment: positive/negative/neutral
        - Category (sector tag)
        - Urgency: 1-5 (5 = market-moving catalyst)

        Returns only items with urgency >= 3 and relevance = Y.
        """
        if not items:
            return []

        filtered = []
        batch_size = 10

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            tasks = [self._classify_item(item, watchlist) for item in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item, result in zip(batch, results):
                if isinstance(result, Exception):
                    continue
                if result and result.get("relevant") and result.get("urgency", 0) >= 3:
                    item.update(result)
                    filtered.append(item)

        logger.info(f"Ollama news filter: {len(items)} → {len(filtered)} relevant items")
        return filtered

    async def _classify_item(self, item: dict, watchlist: list[str]) -> dict | None:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        watchlist_str = ", ".join(watchlist[:50])

        is_macro = item.get("is_macro", False)
        macro_note = (
            "\nNOTE: This is a macro/policy source (Fed, Treasury, White House). "
            "Rate decisions, FOMC statements, tariff announcements, and executive orders "
            "are ALWAYS relevant (urgency >= 4). Mark relevant=true."
            if is_macro else ""
        )

        prompt = f"""Analyze this financial news item. Watchlist: {watchlist_str}{macro_note}

Headline: {headline}
Summary: {summary[:300]}

Respond in JSON only:
{{
  "relevant": true/false,
  "ticker": "SYMBOL or null",
  "sentiment": "positive/negative/neutral",
  "category": "ai_infra/space/nuclear/defense/quantum/pharma/auto/fintech/fed_policy/fiscal_policy/macro/other",
  "urgency": 1-5,
  "reason": "brief explanation"
}}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                import orjson
                return orjson.loads(data.get("response", "{}"))
        except Exception as e:
            logger.debug(f"Ollama classify failed: {e}")
            return None


_aggregator: NewsAggregator | None = None
_filter: OllamaNewsFilter | None = None


def get_news_aggregator() -> NewsAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = NewsAggregator()
    return _aggregator


def get_ollama_filter() -> OllamaNewsFilter:
    global _filter
    if _filter is None:
        _filter = OllamaNewsFilter()
    return _filter
