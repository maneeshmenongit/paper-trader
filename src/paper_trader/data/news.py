"""Live news source implementations — RSS, Google News, Hacker News.

Each implements the NewsSource Protocol. All run VADER sentiment on items before returning.
"""

# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime

import feedparser
import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# TODO(T05): import from paper_trader.domain once the NewsItem model exists.
# from paper_trader.domain import NewsItem
from dataclasses import dataclass, field


@dataclass
class NewsItem:
    """Stub stand-in for the real domain NewsItem (arrives in T05).

    Mirrors the constructor keywords used below so this copied module imports and
    runs during scaffolding. Replace with the import above when domain models land.
    """

    source: str
    title: str
    url: str
    published_at: datetime
    description: str = ""
    sentiment_score: float = 0.0
    metadata: dict = field(default_factory=dict)


_vader = SentimentIntensityAnalyzer()


def _score_sentiment(text: str) -> float:
    """Return VADER compound sentiment score for text."""
    return _vader.polarity_scores(text)["compound"]


def _parse_feed_date(entry: dict) -> datetime:
    """Parse date from a feedparser entry, with fallback to now."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            from time import mktime

            return datetime.fromtimestamp(mktime(parsed), tz=UTC)
        except (ValueError, OverflowError):
            pass
    return datetime.now(UTC)


class RSSNewsSource:
    """Fetches news from one or more RSS feed URLs."""

    def __init__(self, feeds: list[str], name: str = "rss"):
        self.name = name
        self._feeds = feeds

    def fetch_recent(
        self,
        since: datetime,
        keywords: list[str] | None = None,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []
        for url in self._feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub = _parse_feed_date(entry)
                    if pub < since:
                        continue
                    title = entry.get("title", "")
                    desc = entry.get("summary", entry.get("description", ""))
                    if keywords and not _matches_keywords(title + " " + desc, keywords):
                        continue
                    text = f"{title} {desc}"
                    items.append(
                        NewsItem(
                            source=self.name,
                            title=title,
                            url=entry.get("link", ""),
                            published_at=pub,
                            description=desc[:500],
                            sentiment_score=_score_sentiment(text),
                        )
                    )
            except Exception:
                continue  # skip broken feeds, never crash
        return items


class HackerNewsSource:
    """Fetches top stories from Hacker News via Firebase API."""

    def __init__(self, max_items: int = 30):
        self.name = "hackernews"
        self._max_items = max_items
        self._base = "https://hacker-news.firebaseio.com/v0"

    def fetch_recent(
        self,
        since: datetime,
        keywords: list[str] | None = None,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(f"{self._base}/topstories.json")
                resp.raise_for_status()
                story_ids = resp.json()[: self._max_items]

                for sid in story_ids:
                    try:
                        r = client.get(f"{self._base}/item/{sid}.json")
                        r.raise_for_status()
                        story = r.json()
                        if not story or story.get("type") != "story":
                            continue

                        pub = datetime.fromtimestamp(story.get("time", 0), tz=UTC)
                        if pub < since:
                            continue

                        title = story.get("title", "")
                        url = story.get("url", f"https://news.ycombinator.com/item?id={sid}")

                        if keywords and not _matches_keywords(title, keywords):
                            continue

                        items.append(
                            NewsItem(
                                source=self.name,
                                title=title,
                                url=url,
                                published_at=pub,
                                description="",
                                sentiment_score=_score_sentiment(title),
                            )
                        )
                    except Exception:
                        continue
        except Exception:
            pass  # total failure → return empty, never crash
        return items


class GoogleNewsSource:
    """Fetches news from Google News RSS search endpoint."""

    def __init__(self):
        self.name = "google_news"

    def fetch_recent(
        self,
        since: datetime,
        keywords: list[str] | None = None,
    ) -> list[NewsItem]:
        query = "+".join(keywords) if keywords else "crypto"
        encoded = urllib.parse.quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US"

        items: list[NewsItem] = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                pub = _parse_feed_date(entry)
                if pub < since:
                    continue
                title = entry.get("title", "")
                desc = entry.get("summary", entry.get("description", ""))
                text = f"{title} {desc}"
                items.append(
                    NewsItem(
                        source=self.name,
                        title=title,
                        url=entry.get("link", ""),
                        published_at=pub,
                        description=desc[:500],
                        sentiment_score=_score_sentiment(text),
                    )
                )
        except Exception:
            pass
        return items


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    """Case-insensitive check: does text contain any keyword?"""
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)
