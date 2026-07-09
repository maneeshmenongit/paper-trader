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

import math
from datetime import UTC, datetime

import pandas as pd

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


class OfflineQuoteError(ValueError):
    """No real cached close exists for the requested (symbol, timestamp).

    Raised instead of silently fabricating a round-number quote — the Stage-0
    seam must never invent a price (backtest sanity check #3).
    """


class OfflineMarketData:
    """MarketDataProvider backtest seam.

    Two modes, both offline / network-free:

    - **Stub mode** (``history=None``): flat quote, empty history — the sanctioned
      default the offline runner uses to assemble cleanly when live mode is OFF.
      ``get_current_quote(symbol)`` (no timestamp) returns the flat stub value,
      preserving the pre-Stage-0 behavior of the offline runner path.

    - **History mode** (``history`` provided): serves REAL cached daily closes from
      the backtest Parquet cache (``backtest/historical_fetch.load_cached``). This
      is the Stage-0 backtest seam — NOT the live trading path (live uses
      ``YFinanceMarketData``), so fixing it does not touch the frozen live loop.
      ``get_current_quote(symbol, timestamp)`` returns the close on that trading
      day, guarded ``> 0 and isfinite``; a missing/NaN/zero close raises
      ``OfflineQuoteError`` (never a round-number fallback).
    """

    def __init__(
        self,
        history: dict[str, pd.DataFrame] | None = None,
        *,
        stub_quote: float = 100.0,
    ):
        # Normalise each frame to a sorted DatetimeIndex once, up front.
        self._history: dict[str, pd.DataFrame] = {}
        for symbol, df in (history or {}).items():
            frame = df.copy()
            frame.index = pd.to_datetime(frame.index)
            self._history[symbol] = frame.sort_index()
        self._stub_quote = stub_quote

    async def get_current_quote(
        self, symbol: str, timestamp: datetime | None = None
    ) -> float:
        # Stub mode: no timestamp and no history → the legacy flat quote.
        if timestamp is None or symbol not in self._history:
            if self._history:
                # History was provided but this symbol/timestamp combination is not
                # answerable — refuse rather than fabricate (sanity check #3).
                raise OfflineQuoteError(
                    f"no cached history for {symbol!r}"
                    if symbol not in self._history
                    else f"a timestamp is required to price {symbol!r} from history"
                )
            return self._stub_quote
        return self.close_on(symbol, timestamp)

    def close_on(self, symbol: str, timestamp: datetime) -> float:
        """Return the real cached close for ``symbol`` on ``timestamp``'s day.

        Guards ``> 0 and isfinite``; raises ``OfflineQuoteError`` otherwise. This
        is the single price oracle the Stage-0 settlement adapter drives — pure
        lookup, no fabrication.
        """
        frame = self._history.get(symbol)
        if frame is None:
            raise OfflineQuoteError(f"no cached history for {symbol!r}")
        # Match on calendar date only, tz-agnostic: cached frames are tz-naive
        # daily bars, but callers may pass tz-aware timestamps (settlement uses
        # UTC). Comparing plain dates sidesteps the naive/aware equality trap.
        want = pd.Timestamp(timestamp).date()
        matches = frame.loc[frame.index.date == want]
        if matches.empty:
            raise OfflineQuoteError(f"no cached close for {symbol!r} on {want}")
        close = float(matches["Close"].iloc[0])
        if not (close > 0 and math.isfinite(close)):
            raise OfflineQuoteError(
                f"non-finite/zero cached close for {symbol!r} on {want}: {close!r}"
            )
        return close

    def has_close_on(self, symbol: str, timestamp: datetime) -> bool:
        """True iff a real, finite, positive close exists for that (symbol, day)."""
        try:
            self.close_on(symbol, timestamp)
        except OfflineQuoteError:
            return False
        return True

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
