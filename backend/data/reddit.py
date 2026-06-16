"""
Reddit public-JSON ingestor — free, no auth.

Reddit lets us pull JSON for any subreddit page by appending `.json` to the
URL (rate-limited but doesn't require OAuth for read-only). Boehmer, Jones,
Zhang & Zhang (2021, *JF*) showed retail order imbalance from social signals
predicts short-horizon returns; Reddit's mention bursts are the cheapest
operationalization of that.

Sources scanned:
  - r/wallstreetbets/hot   (raw mention volume + sentiment skew)
  - r/options/hot          (cleaner, more informed flow)
  - r/stocks/hot

Extracts: ticker mentions from post titles + top-level comments via a
$REGEX → uppercase 1-5 letter token filter + ban-list of stop words.
"""

from __future__ import annotations

import re
import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from loguru import logger

from core.redis_client import cache_get, cache_set


SUBREDDITS = ["wallstreetbets", "options", "stocks"]
SUBREDDIT_LIMIT = 50  # posts per subreddit (Reddit caps at 100)
USER_AGENT = "TradeResearch/0.1 (contact: vidyasrigr@gmail.com)"
CACHE_TTL_S = 1800  # 30 min — Reddit moves slowly enough

# Common false-positive uppercase tokens to never count as tickers
STOP_TOKENS = {
    # Pronouns / articles / common short words
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "IF", "IN",
    "IS", "IT", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    "ALL", "AND", "ARE", "BUT", "CAN", "DAY", "FOR", "GET", "GOT", "HAS", "HAD",
    "HER", "HIM", "HIS", "HOW", "ITS", "MAY", "NEW", "NOT", "NOW", "OUR", "OUT",
    "SAW", "SHE", "THE", "TOO", "TWO", "USE", "WAS", "WHO", "WHY", "YOU",
    # Adjectives / common nouns frequently uppercased on Reddit
    "BIG", "OLD", "BAD", "WAY", "TOP", "LOW", "ONE", "OWN",
    "PUT", "SET", "TRY", "RUN", "WIN", "BUY", "ADD", "BIT", "EYE", "FUN",
    # Finance acronyms
    "ATH", "EOD", "DCA", "DD",  "DOW", "EPS", "ETF", "FED", "FOMC", "GDP",
    "IPO", "IRA", "IRS", "KEY", "LOL", "OTC", "PR",  "PSA", "ROI", "SEC",
    "WSB", "YOLO", "FOMO", "MOON", "BULL", "BEAR", "EDIT", "TLDR", "AKA",
    "OMG", "WTF", "IMO", "FYI", "FAQ", "NSFW", "ELI5", "TLDR", "PSA",
}

TICKER_RE = re.compile(r"\$?([A-Z]{1,5})\b")


def _extract_tickers(text: str | None) -> list[str]:
    if not text:
        return []
    tokens = TICKER_RE.findall(text)
    return [t for t in tokens if t not in STOP_TOKENS]


@dataclass
class SubredditScan:
    subreddit: str
    posts_scanned: int
    ticker_mentions: Counter = field(default_factory=Counter)
    bullish_mentions: Counter = field(default_factory=Counter)
    bearish_mentions: Counter = field(default_factory=Counter)


BULLISH_KEYWORDS = ("calls", "long", "buy", "moon", "bullish", "pump", "squeeze",
                     "breakout", "gamma", "rip")
BEARISH_KEYWORDS = ("puts", "short", "sell", "bearish", "crash", "dump",
                     "rugpull", "rugged", "downside")


def _polarity(title_lower: str, selftext_lower: str) -> str:
    text = title_lower + " " + selftext_lower
    bull = sum(text.count(k) for k in BULLISH_KEYWORDS)
    bear = sum(text.count(k) for k in BEARISH_KEYWORDS)
    if bull > bear + 1:
        return "bullish"
    if bear > bull + 1:
        return "bearish"
    return "neutral"


async def _scan_subreddit(subreddit: str, client: httpx.AsyncClient) -> SubredditScan:
    out = SubredditScan(subreddit=subreddit, posts_scanned=0)
    try:
        resp = await client.get(
            f"https://www.reddit.com/r/{subreddit}/hot.json",
            params={"limit": SUBREDDIT_LIMIT},
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            logger.debug(f"reddit {subreddit}: status={resp.status_code}")
            return out
        data = resp.json()
        posts = (data.get("data", {}).get("children") or [])
    except Exception as e:
        logger.debug(f"reddit fetch failed for {subreddit}: {e}")
        return out

    for entry in posts:
        post = entry.get("data") or {}
        title = post.get("title") or ""
        selftext = post.get("selftext") or ""
        tickers = _extract_tickers(title) + _extract_tickers(selftext)
        if not tickers:
            continue
        out.posts_scanned += 1
        polarity = _polarity(title.lower(), selftext.lower())
        for t in set(tickers):  # one mention per post
            out.ticker_mentions[t] += 1
            if polarity == "bullish":
                out.bullish_mentions[t] += 1
            elif polarity == "bearish":
                out.bearish_mentions[t] += 1
    return out


@dataclass
class RedditMention:
    symbol: str
    total_mentions: int
    bullish_mentions: int
    bearish_mentions: int
    sources: list[str]                  # subreddits that mentioned it

    @property
    def net_polarity(self) -> int:
        return self.bullish_mentions - self.bearish_mentions

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "total_mentions": self.total_mentions,
            "bullish": self.bullish_mentions,
            "bearish": self.bearish_mentions,
            "net_polarity": self.net_polarity,
            "sources": self.sources,
        }


async def fetch_mentions() -> list[RedditMention]:
    cache_key = "reddit:mentions:v1"
    cached = await cache_get(cache_key)
    if cached:
        import orjson
        rows = orjson.loads(cached)
        return [RedditMention(**r) for r in rows]

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        scans = await asyncio.gather(
            *[_scan_subreddit(sr, client) for sr in SUBREDDITS],
            return_exceptions=True,
        )

    by_symbol: dict[str, RedditMention] = {}
    for scan in scans:
        if isinstance(scan, Exception) or scan is None:
            continue
        for sym, count in scan.ticker_mentions.items():
            entry = by_symbol.setdefault(
                sym, RedditMention(symbol=sym, total_mentions=0,
                                     bullish_mentions=0, bearish_mentions=0,
                                     sources=[]),
            )
            entry.total_mentions += count
            entry.bullish_mentions += scan.bullish_mentions.get(sym, 0)
            entry.bearish_mentions += scan.bearish_mentions.get(sym, 0)
            if scan.subreddit not in entry.sources:
                entry.sources.append(scan.subreddit)

    result = sorted(by_symbol.values(), key=lambda m: m.total_mentions, reverse=True)
    import orjson
    await cache_set(
        cache_key,
        orjson.dumps([m.to_dict() for m in result]).decode(),
        ttl=CACHE_TTL_S,
    )
    return result


async def mentions_for_symbol(symbol: str) -> RedditMention | None:
    rows = await fetch_mentions()
    for r in rows:
        if r.symbol == symbol:
            return r
    return None
