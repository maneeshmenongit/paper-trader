"""Live CoinGecko crypto-data client (Live-Operation T1).

The live counterpart of ``tests.fixtures.fakes.FakeCryptoData``, implementing the
``CryptoDataProvider`` protocol from ``paper_trader.data.interfaces`` verbatim.
CoinGecko covers crypto market data (market cap, 24h volume, supply); the free
tier needs no key — the authority (§3 T1) groups it with the no-hard-dependency
providers.

Design:
- The pycoingecko SDK is synchronous → wrapped in ``asyncio.to_thread``.
- The raw SDK call is isolated behind a ``_coin_by_id`` seam so tests inject
  recorded fixtures and never touch the network.
- Retries ride the shared ``retry_with_backoff`` seam; the finnhub/coingecko
  politeness bound (≤ 4 concurrent) stays owned by the Research agent's semaphore.
- ``get_market_data`` returns the dict shape the fake returns (market_cap,
  volume_24h, ...). ``get_crypto_news`` returns [] — CoinGecko is not a news
  source (the fake returns [] too); crypto news is a later, separate seam if a
  demonstrated need appears.

Symbol mapping: the app watchlist uses tickers (``BTC``), CoinGecko keys by coin
id (``bitcoin``). A small built-in map covers the common majors; unknown symbols
fall back to the lowercased ticker, which the caller can override by injecting a
custom ``symbol_to_id``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from paper_trader.data.live.retry import retry_with_backoff
from paper_trader.domain import NewsItem

# Common ticker -> CoinGecko coin-id. Extend via the injectable override.
DEFAULT_SYMBOL_TO_ID: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "DOT": "polkadot",
}


class CoinGeckoCryptoData:
    """CryptoDataProvider over the pycoingecko SDK. Crypto; free tier, no key.

    ``coin_by_id`` is injectable so tests supply recorded fixtures. In production
    it defaults to the real SDK call, with the client constructed lazily so
    importing this module never requires a network.
    """

    def __init__(
        self,
        *,
        coin_by_id: Callable[[str], dict[str, Any]] | None = None,
        symbol_to_id: dict[str, str] | None = None,
        max_attempts: int = 3,
    ):
        self._coin_by_id = coin_by_id
        self._symbol_to_id = {**DEFAULT_SYMBOL_TO_ID, **(symbol_to_id or {})}
        self._max_attempts = max_attempts
        self._client: Any | None = None

    def _coin_id(self, symbol: str) -> str:
        return self._symbol_to_id.get(symbol.upper(), symbol.lower())

    def _coin_by_id_raw(self, symbol: str) -> dict[str, Any]:
        coin_id = self._coin_id(symbol)
        if self._coin_by_id is not None:
            return self._coin_by_id(coin_id)
        if self._client is None:
            from pycoingecko import CoinGeckoAPI

            self._client = CoinGeckoAPI()
        return dict(
            self._client.get_coin_by_id(
                coin_id,
                localization=False,
                tickers=False,
                market_data=True,
                community_data=False,
                developer_data=False,
            )
        )

    async def get_market_data(self, symbol: str) -> dict[str, object]:
        raw = await retry_with_backoff(
            lambda: asyncio.to_thread(self._coin_by_id_raw, symbol),
            max_attempts=self._max_attempts,
        )
        return _extract_market_data(raw)

    async def get_crypto_news(self, symbol: str, since: datetime) -> list[NewsItem]:
        # CoinGecko is not a news source; mirror the fake's empty return. A live
        # crypto-news seam is deferred until a demonstrated need appears.
        return []


def _extract_market_data(raw: dict[str, Any]) -> dict[str, object]:
    """Pull market_cap / 24h volume / supply out of a get_coin_by_id payload.

    Values live under ``market_data`` keyed by currency (``usd``). A missing field
    becomes ``None`` rather than raising — the caller decides how to handle a gap.
    """
    md = raw.get("market_data") or {}

    def _usd(key: str) -> float | None:
        block = md.get(key)
        if isinstance(block, dict):
            value = block.get("usd")
            return float(value) if value is not None else None
        return None

    return {
        "market_cap": _usd("market_cap"),
        "volume_24h": _usd("total_volume"),
        "current_price": _usd("current_price"),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
    }
