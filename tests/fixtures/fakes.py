"""Deterministic seam fakes for tests (Wave 2.5 Task 2).

No network calls. Each fake implements one seam protocol from
paper_trader.data.interfaces (or the LLM router) with in-memory, injectable data,
so agent tests construct CycleState with fakes and assert on state mutations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from paper_trader.domain import Asset, NewsItem, OHLCVBar

FIXED_NOW = datetime(2026, 7, 5, 15, 0, tzinfo=UTC)  # a weekday (Sunday->adjust in tests)


class FrozenClock:
    """Deterministic Clock. `now` fixed; market-open answers are injected."""

    def __init__(self, now: datetime = FIXED_NOW, *, market_open: bool = True):
        self._now = now
        self._market_open = market_open

    def now(self) -> datetime:
        return self._now

    def is_market_open(self, asset_type: str) -> bool:
        if asset_type == "crypto":
            return True
        return self._market_open


class FakeMarketData:
    """MarketDataProvider fake. Quotes/OHLCV/metadata injected per symbol."""

    def __init__(
        self,
        quotes: dict[str, float] | None = None,
        ohlcv: dict[str, list[OHLCVBar]] | None = None,
        metadata: dict[str, Asset] | None = None,
    ):
        self.quotes = quotes or {}
        self.ohlcv = ohlcv or {}
        self.metadata = metadata or {}

    async def get_current_quote(self, symbol: str) -> float:
        return self.quotes.get(symbol, 100.0)

    async def get_ohlcv(self, symbol: str, period_days: int) -> list[OHLCVBar]:
        return self.ohlcv.get(symbol, [])

    async def get_asset_metadata(self, symbol: str) -> Asset:
        return self.metadata.get(symbol, Asset(symbol=symbol, kind="stock"))


class FakeCompanyNews:
    def __init__(self, news: dict[str, list[NewsItem]] | None = None, *, fail: bool = False):
        self.news = news or {}
        self.fail = fail

    async def get_company_news(self, symbol: str, since: datetime) -> list[NewsItem]:
        if self.fail:
            raise RuntimeError("simulated news source failure")
        return self.news.get(symbol, [])


class FakeCryptoData:
    def __init__(self, market: dict[str, dict[str, object]] | None = None):
        self.market = market or {}

    async def get_market_data(self, symbol: str) -> dict[str, object]:
        return self.market.get(symbol, {})

    async def get_crypto_news(self, symbol: str, since: datetime) -> list[NewsItem]:
        return []


class FakeTradingClient:
    """Deterministic fill at the quoted price; injectable liquidity per symbol."""

    def __init__(self, liquidity: dict[str, float] | None = None):
        self.liquidity = liquidity or {}
        self.submitted: list[tuple[str, float, float]] = []

    async def submit_paper_trade(self, symbol: str, quantity: float, price: float) -> float:
        self.submitted.append((symbol, quantity, price))
        return price  # fills exactly at the quoted price

    async def get_liquidity_metric(self, symbol: str, asset_type: str) -> float:
        # default well above any floor so Filter R2 passes unless overridden
        default = 1_000_000_000.0
        return self.liquidity.get(symbol, default)


class FakeLLMRouter:
    """LLM router fake. Returns scripted (text, tokens) per purpose; counts calls.

    Matches LLMRouter.call(purpose, system, user, ...) -> (text, tokens_used).
    A purpose set to raise simulates budget exhaustion or provider failure.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        tokens_per_call: int = 10,
        fail_purposes: set[str] | None = None,
        budget_exhausted_after: int | None = None,
    ):
        self.responses = responses or {}
        self.tokens_per_call = tokens_per_call
        self.fail_purposes = fail_purposes or set()
        # Raise BudgetExhaustedError once this many successful calls have occurred.
        self.budget_exhausted_after = budget_exhausted_after
        self.calls: list[str] = []

    def call(
        self,
        purpose: str,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        if (
            self.budget_exhausted_after is not None
            and len(self.calls) >= self.budget_exhausted_after
        ):
            from paper_trader.llm.errors import BudgetExhaustedError

            raise BudgetExhaustedError("simulated budget exhaustion")
        if purpose in self.fail_purposes:
            raise RuntimeError(f"simulated LLM failure for {purpose}")
        self.calls.append(purpose)
        return self.responses.get(purpose, ""), self.tokens_per_call


def make_ohlcv(closes: list[float], *, start: datetime | None = None) -> list[OHLCVBar]:
    """Build a simple OHLCV series from a list of closes (one bar/day)."""
    start = start or (FIXED_NOW - timedelta(days=len(closes)))
    bars = []
    for i, c in enumerate(closes):
        ts = start + timedelta(days=i)
        bars.append(OHLCVBar(timestamp=ts, open=c, high=c, low=c, close=c, volume=1_000_000))
    return bars
