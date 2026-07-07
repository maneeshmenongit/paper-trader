"""Live yfinance market-data client (Live-Operation T1).

The live counterpart of ``tests.fixtures.fakes.FakeMarketData``, implementing the
``MarketDataProvider`` protocol from ``paper_trader.data.interfaces`` verbatim.
yfinance covers both stocks and crypto (e.g. ``BTC-USD``), no API key required —
the authority (§3 T1) says "yfinance (no key — start here)".

Design:
- yfinance is synchronous/blocking. Each call is wrapped in ``asyncio.to_thread``
  so it does not block the event loop and stays a drop-in for the async protocol.
- The raw library call is isolated behind ``_download``/``_ticker_info`` seams so
  tests inject recorded fixtures and never touch the network (CI stays offline).
- Retries ride the shared ``retry_with_backoff`` seam. Politeness (yfinance ≤ 2
  concurrent) stays owned by the Research agent's semaphore — this client adds no
  concurrency of its own.
- Agents are unchanged: same protocol, real implementation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, cast

from paper_trader.data.live.retry import retry_with_backoff
from paper_trader.domain import Asset, OHLCVBar

# yfinance's period_days -> a period string it accepts. Kept coarse: we ask for a
# window at least as long as requested and slice locally, since yfinance only
# takes canned period tokens.
_PERIOD_FOR_DAYS = [
    (5, "5d"),
    (30, "1mo"),
    (90, "3mo"),
    (180, "6mo"),
    (365, "1y"),
]


def _period_token(period_days: int) -> str:
    for days, token in _PERIOD_FOR_DAYS:
        if period_days <= days:
            return token
    return "2y"


class YFinanceMarketData:
    """MarketDataProvider over yfinance. Stocks and crypto; no key.

    ``download`` and ``ticker_info`` are injectable so tests supply recorded
    fixtures. In production they default to the real yfinance calls, imported
    lazily so importing this module never requires the network or the library at
    import time.
    """

    def __init__(
        self,
        *,
        download: Callable[[str, str], Any] | None = None,
        ticker_info: Callable[[str], dict[str, Any]] | None = None,
        max_attempts: int = 3,
    ):
        self._download = download
        self._ticker_info = ticker_info
        self._max_attempts = max_attempts

    # ─── raw library seams (overridden in tests) ─────────────────────────

    def _download_raw(self, symbol: str, period: str) -> Any:
        if self._download is not None:
            return self._download(symbol, period)
        import yfinance as yf

        return yf.download(symbol, period=period, auto_adjust=False, progress=False)

    def _ticker_info_raw(self, symbol: str) -> dict[str, Any]:
        if self._ticker_info is not None:
            return self._ticker_info(symbol)
        import yfinance as yf

        return dict(yf.Ticker(symbol).info)

    # ─── protocol methods ────────────────────────────────────────────────

    async def get_current_quote(self, symbol: str) -> float:
        info = await retry_with_backoff(
            lambda: asyncio.to_thread(self._ticker_info_raw, symbol),
            max_attempts=self._max_attempts,
        )
        price = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
        )
        if price is None:
            raise ValueError(f"yfinance returned no price for {symbol}")
        return float(price)

    async def get_ohlcv(self, symbol: str, period_days: int) -> list[OHLCVBar]:
        period = _period_token(period_days)
        df = await retry_with_backoff(
            lambda: asyncio.to_thread(self._download_raw, symbol, period),
            max_attempts=self._max_attempts,
        )
        return _frame_to_bars(df, period_days)

    async def get_asset_metadata(self, symbol: str) -> Asset:
        info = await retry_with_backoff(
            lambda: asyncio.to_thread(self._ticker_info_raw, symbol),
            max_attempts=self._max_attempts,
        )
        quote_type = str(info.get("quoteType", "")).upper()
        kind: Literal["stock", "crypto"] = (
            "crypto" if quote_type == "CRYPTOCURRENCY" else "stock"
        )
        sector = info.get("sector")
        return Asset(symbol=symbol, kind=kind, sector=sector)


def _frame_to_bars(df: Any, period_days: int) -> list[OHLCVBar]:
    """Convert a yfinance OHLCV DataFrame to the last ``period_days`` bars.

    Handles the (field, ticker) column MultiIndex yfinance returns even for a
    single symbol (same collapse as the backtest fetcher). An empty/None frame
    yields an empty list — the caller (Research R1) degrades gracefully.
    """
    if df is None or getattr(df, "empty", True):
        return []

    import pandas as pd

    frame = df
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.copy()
        frame.columns = frame.columns.get_level_values(0)

    frame = frame.tail(period_days)
    bars: list[OHLCVBar] = []
    index = pd.to_datetime(frame.index)
    for ts, row in zip(index, frame.itertuples(index=False), strict=False):
        cols = frame.columns
        data = dict(zip(cols, row, strict=False))
        bars.append(
            OHLCVBar(
                timestamp=_as_datetime(ts),
                open=float(data["Open"]),
                high=float(data["High"]),
                low=float(data["Low"]),
                close=float(data["Close"]),
                volume=float(data["Volume"]),
            )
        )
    return bars


def _as_datetime(ts: Any) -> datetime:
    """Coerce a pandas Timestamp (or datetime) to a plain datetime."""
    if isinstance(ts, datetime):
        return ts
    return cast(datetime, ts.to_pydatetime())
