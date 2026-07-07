"""Recorded market-data fixtures for the live data-client tests (Live-Op T1).

These are static, network-free stand-ins for the raw library payloads the live
clients parse: a yfinance OHLCV DataFrame, a finnhub company-news list, and a
CoinGecko get_coin_by_id dict. Tests inject them via the clients' raw-call seams
so CI never touches the network.

Shapes mirror what the real libraries return (yfinance's (field, ticker) column
MultiIndex; finnhub's unix ``datetime``; CoinGecko's ``market_data.<field>.usd``).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def recorded_ohlcv_frame(symbol: str = "AAPL", *, rows: int = 5) -> pd.DataFrame:
    """A yfinance-style OHLCV frame with the (field, ticker) column MultiIndex."""
    dates = pd.date_range("2026-06-01", periods=rows, freq="D")
    closes = [100.0 + i for i in range(rows)]
    fields = {
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Adj Close": closes,
        "Volume": [1_000_000 + i * 1000 for i in range(rows)],
    }
    columns = pd.MultiIndex.from_tuples([(f, symbol) for f in fields])
    data = {(f, symbol): v for f, v in fields.items()}
    return pd.DataFrame(data, index=dates, columns=columns)


def recorded_ticker_info(symbol: str = "AAPL", *, crypto: bool = False) -> dict[str, Any]:
    if crypto:
        return {
            "regularMarketPrice": 65000.0,
            "quoteType": "CRYPTOCURRENCY",
        }
    return {
        "regularMarketPrice": 195.25,
        "previousClose": 194.10,
        "quoteType": "EQUITY",
        "sector": "Technology",
    }


def recorded_finnhub_news(symbol: str = "AAPL") -> list[dict[str, Any]]:
    return [
        {
            "headline": f"{symbol} beats earnings estimates",
            "url": f"https://example.com/{symbol}/1",
            "datetime": 1_751_000_000,  # unix seconds
            "source": "Reuters",
            "summary": "…",
        },
        {
            "headline": f"{symbol} announces buyback",
            "url": f"https://example.com/{symbol}/2",
            "datetime": 1_751_100_000,
            "source": "Bloomberg",
        },
        # A malformed item (no headline) — the client must skip it, not raise.
        {"url": "https://example.com/x", "datetime": 1_751_200_000},
    ]


def recorded_coingecko_coin(symbol: str = "bitcoin") -> dict[str, Any]:
    return {
        "id": symbol,
        "symbol": "btc",
        "market_data": {
            "market_cap": {"usd": 1_280_000_000_000.0},
            "total_volume": {"usd": 35_000_000_000.0},
            "current_price": {"usd": 65_000.0},
            "circulating_supply": 19_700_000.0,
            "total_supply": 21_000_000.0,
        },
    }
