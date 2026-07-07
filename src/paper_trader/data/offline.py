"""In-package offline data seams (Live-Operation T5 fix).

The sanctioned offline default for the provider factory when live mode is OFF.
Application-owned (NOT the test tree) so a production run with
``PAPER_TRADER_LIVE_MODE=0`` assembles without importing ``tests`` — the earlier
factory reached into ``tests.fixtures.fakes``, which is absent outside pytest.

These are deterministic, network-free implementations of the data-client
protocols. They mirror the test fakes' shapes but live beside the live clients so
both the runner and CI can use them. Test fixtures may still keep their own richer
fakes; this is only what the offline runner needs to start cleanly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from paper_trader.domain import Asset, NewsItem, OHLCVBar


class OfflineClock:
    """Wall-clock-free deterministic Clock; market always open (offline default)."""

    def __init__(self, now: datetime | None = None, *, market_open: bool = True):
        self._now = now or datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
        self._market_open = market_open

    def now(self) -> datetime:
        return self._now

    def is_market_open(self, asset_type: str) -> bool:
        return True if asset_type == "crypto" else self._market_open


class OfflineMarketData:
    """MarketDataProvider stub: flat quote, empty history (no trades form)."""

    async def get_current_quote(self, symbol: str) -> float:
        return 100.0

    async def get_ohlcv(self, symbol: str, period_days: int) -> list[OHLCVBar]:
        return []

    async def get_asset_metadata(self, symbol: str) -> Asset:
        return Asset(symbol=symbol, kind="stock")


class OfflineCompanyNews:
    async def get_company_news(self, symbol: str, since: datetime) -> list[NewsItem]:
        return []


class OfflineCryptoData:
    async def get_market_data(self, symbol: str) -> dict[str, object]:
        return {}

    async def get_crypto_news(self, symbol: str, since: datetime) -> list[NewsItem]:
        return []


class OfflineTradingClient:
    """Fill at the quoted price; ample liquidity so R2 never binds offline."""

    async def submit_paper_trade(self, symbol: str, quantity: float, price: float) -> float:
        return price

    async def get_liquidity_metric(self, symbol: str, asset_type: str) -> float:
        return 1_000_000_000.0
