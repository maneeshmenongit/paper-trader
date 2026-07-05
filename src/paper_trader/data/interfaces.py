"""Data-client seam protocols (Wave 2.5 Task 2).

Verbatim in shape from PAPER_TRADER_ARCH_002 §7.1. Every external dependency is a
Protocol; live implementations injected at boot, fakes used in tests (no network
calls in tests). The Clock is likewise injectable — agents NEVER call
datetime.now() directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from paper_trader.domain import Asset, NewsItem, OHLCVBar


@runtime_checkable
class MarketDataProvider(Protocol):
    """Current quote and recent OHLCV for stocks AND crypto. yfinance covers both."""

    async def get_current_quote(self, symbol: str) -> float: ...

    async def get_ohlcv(self, symbol: str, period_days: int) -> list[OHLCVBar]: ...

    async def get_asset_metadata(self, symbol: str) -> Asset: ...


@runtime_checkable
class CompanyNewsProvider(Protocol):
    """Per-ticker news. Finnhub for stocks."""

    async def get_company_news(self, symbol: str, since: datetime) -> list[NewsItem]: ...


@runtime_checkable
class CryptoDataProvider(Protocol):
    """Crypto-specific market data: market cap, volume, supply. CoinGecko."""

    async def get_market_data(self, symbol: str) -> dict[str, object]: ...

    async def get_crypto_news(self, symbol: str, since: datetime) -> list[NewsItem]: ...


@runtime_checkable
class Clock(Protocol):
    """Injectable clock. Live = wall clock. Frozen = test fixture."""

    def now(self) -> datetime: ...

    def is_market_open(self, asset_type: str) -> bool:
        """For 'stock', checks NYSE/NASDAQ hours. For 'crypto', always True."""
        ...


@runtime_checkable
class TradingClient(Protocol):
    """Simulated execution seam. No broker — records a fill at a given price.

    ARCH_002's 'exchange is a SQLite table': this seam is what Execute calls to
    'place' a simulated trade. Live = writes a paper_trades row at the quoted
    price; fake = deterministic fill for tests.
    """

    async def submit_paper_trade(
        self, symbol: str, quantity: float, price: float
    ) -> float:
        """Return the simulated fill price."""
        ...

    async def get_liquidity_metric(self, symbol: str, asset_type: str) -> float:
        """Return the liquidity figure Filter R2 checks: 20-day avg daily dollar
        volume (stocks) or 24h volume (crypto), in dollars."""
        ...
