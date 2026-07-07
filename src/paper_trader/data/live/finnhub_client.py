"""Live Finnhub company-news client (Live-Operation T1).

The live counterpart of ``tests.fixtures.fakes.FakeCompanyNews``, implementing the
``CompanyNewsProvider`` protocol from ``paper_trader.data.interfaces`` verbatim.
Finnhub covers per-ticker stock news and requires an API key (``FINNHUB_API_KEY``,
supplied by config at boot — never hardcoded, never frozen into the trace).

Design:
- The finnhub SDK is synchronous → wrapped in ``asyncio.to_thread``.
- The raw SDK call is isolated behind a ``_company_news`` seam so tests inject
  recorded fixtures and never touch the network.
- Retries ride the shared ``retry_with_backoff`` seam. The finnhub/coingecko
  politeness bound (≤ 4 concurrent) stays owned by the Research agent's news
  semaphore; this client adds no concurrency of its own.
- Failure surfaces as an exception (like the fake's ``fail=True``): Research R1
  degrades a single-source miss to "contributes nothing", never a cycle abort.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from paper_trader.data.live.retry import retry_with_backoff
from paper_trader.domain import NewsItem


class FinnhubCompanyNews:
    """CompanyNewsProvider over the finnhub SDK. Stocks; requires an API key.

    ``company_news`` is injectable so tests supply recorded fixtures. In
    production it defaults to the real SDK call, with the client constructed
    lazily so importing this module never requires the key or a network.
    """

    def __init__(
        self,
        api_key: str,
        *,
        company_news: Callable[[str, str, str], list[dict[str, Any]]] | None = None,
        max_attempts: int = 3,
    ):
        self._api_key = api_key
        self._company_news = company_news
        self._max_attempts = max_attempts
        self._client: Any | None = None

    def _company_news_raw(self, symbol: str, since: datetime) -> list[dict[str, Any]]:
        _from = since.date().isoformat()
        to = datetime.now(tz=UTC).date().isoformat()
        if self._company_news is not None:
            return self._company_news(symbol, _from, to)
        if self._client is None:
            import finnhub

            self._client = finnhub.Client(api_key=self._api_key)
        result = self._client.company_news(symbol, _from=_from, to=to)
        return list(result or [])

    async def get_company_news(self, symbol: str, since: datetime) -> list[NewsItem]:
        raw = await retry_with_backoff(
            lambda: asyncio.to_thread(self._company_news_raw, symbol, since),
            max_attempts=self._max_attempts,
        )
        return [_to_news_item(item) for item in raw if _has_headline(item)]


def _has_headline(item: dict[str, Any]) -> bool:
    return bool(item.get("headline"))


def _to_news_item(item: dict[str, Any]) -> NewsItem:
    ts = item.get("datetime")
    published = (
        datetime.fromtimestamp(float(ts), tz=UTC)
        if ts is not None
        else datetime.now(tz=UTC)
    )
    return NewsItem(
        headline=str(item["headline"]),
        url=str(item.get("url", "")),
        published_at=published,
        source=item.get("source"),
    )
