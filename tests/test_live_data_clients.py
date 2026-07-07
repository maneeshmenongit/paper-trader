"""Live data-client tests (Live-Operation T1).

Every client is exercised against RECORDED FIXTURES injected through its raw-call
seam — no network, ever. The clients implement the existing
``paper_trader.data.interfaces`` protocols verbatim, so these tests also assert
protocol conformance (isinstance against the runtime_checkable protocols).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.data.interfaces import (
    CompanyNewsProvider,
    CryptoDataProvider,
    MarketDataProvider,
)
from paper_trader.data.live import (
    CoinGeckoCryptoData,
    FinnhubCompanyNews,
    YFinanceMarketData,
    retry_with_backoff,
)
from paper_trader.domain import Asset, NewsItem, OHLCVBar
from tests.fixtures.recorded_market_data import (
    recorded_coingecko_coin,
    recorded_finnhub_news,
    recorded_ohlcv_frame,
    recorded_ticker_info,
)

SINCE = datetime(2026, 6, 1, tzinfo=UTC)


# ─── retry seam ──────────────────────────────────────────────────────────

async def test_retry_succeeds_first_try():
    calls = []

    async def fn():
        calls.append(1)
        return "ok"

    result = await retry_with_backoff(fn, sleep=_no_sleep())
    assert result == "ok"
    assert len(calls) == 1


async def test_retry_recovers_after_transient_failures():
    attempts = {"n": 0}

    async def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "recovered"

    result = await retry_with_backoff(fn, max_attempts=3, sleep=_no_sleep())
    assert result == "recovered"
    assert attempts["n"] == 3


async def test_retry_reraises_after_giving_up():
    async def fn():
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        await retry_with_backoff(fn, max_attempts=2, sleep=_no_sleep())


async def test_retry_does_not_retry_unlisted_exceptions():
    calls = []

    async def fn():
        calls.append(1)
        raise KeyError("not retryable")

    with pytest.raises(KeyError):
        await retry_with_backoff(fn, retry_on=(ValueError,), sleep=_no_sleep())
    assert len(calls) == 1  # raised immediately, never retried


def _no_sleep():
    async def _sleep(_delay: float) -> None:
        return None

    return _sleep


# ─── yfinance market-data client ─────────────────────────────────────────

def _yf_client(**over):
    return YFinanceMarketData(
        download=over.get("download", lambda s, p: recorded_ohlcv_frame(s)),
        ticker_info=over.get("ticker_info", lambda s: recorded_ticker_info(s)),
        interval=over.get("interval", "1h"),
    )


def test_yfinance_conforms_to_protocol():
    assert isinstance(_yf_client(), MarketDataProvider)


async def test_yfinance_quote():
    price = await _yf_client().get_current_quote("AAPL")
    assert price == pytest.approx(195.25)


async def test_yfinance_quote_falls_back_to_previous_close():
    client = _yf_client(ticker_info=lambda s: {"previousClose": 100.0})
    assert await client.get_current_quote("AAPL") == pytest.approx(100.0)


async def test_yfinance_ohlcv_parses_multiindex_frame():
    bars = await _yf_client().get_ohlcv("AAPL", period_days=5)
    assert len(bars) == 5
    assert all(isinstance(b, OHLCVBar) for b in bars)
    assert bars[0].close == pytest.approx(100.0)
    assert bars[-1].close == pytest.approx(104.0)
    assert bars[0].volume == pytest.approx(1_000_000)


async def test_yfinance_bar_timestamps_are_utc_aware():
    # Regression (T6 live run): yfinance daily bars are tz-NAIVE; a naive bar
    # timestamp raises when Filter R4 subtracts it from the UTC-aware clock.
    # Every bar timestamp must come back UTC-aware.
    bars = await _yf_client().get_ohlcv("AAPL", period_days=5)
    assert all(b.timestamp.tzinfo is not None for b in bars)


async def test_yfinance_daily_interval_slices_to_period_days():
    # With a DAILY interval, keep == period_days (tail(3) of a 10-row frame).
    client = _yf_client(interval="1d", download=lambda s, p: recorded_ohlcv_frame(s, rows=10))
    bars = await client.get_ohlcv("AAPL", period_days=3)
    assert len(bars) == 3


async def test_yfinance_defaults_to_intraday_for_freshness():
    # Default 1h interval keeps a generous bar tail (not just period_days) so the
    # LATEST bar is minutes-fresh for Filter R4 — the T6 fix for daily-bar staleness.
    client = _yf_client(download=lambda s, p: recorded_ohlcv_frame(s, rows=10))
    bars = await client.get_ohlcv("AAPL", period_days=3)
    assert len(bars) == 10  # intraday keep >> 3, so the whole frame is returned


async def test_yfinance_ohlcv_empty_frame_degrades_to_empty():
    import pandas as pd

    client = _yf_client(download=lambda s, p: pd.DataFrame())
    assert await client.get_ohlcv("AAPL", period_days=5) == []


async def test_yfinance_metadata_stock():
    asset = await _yf_client().get_asset_metadata("AAPL")
    assert asset == Asset(symbol="AAPL", kind="stock", sector="Technology")


async def test_yfinance_metadata_crypto():
    client = _yf_client(ticker_info=lambda s: recorded_ticker_info(s, crypto=True))
    asset = await client.get_asset_metadata("BTC-USD")
    assert asset.kind == "crypto"


async def test_yfinance_quote_missing_price_raises():
    client = _yf_client(ticker_info=lambda s: {})
    with pytest.raises(ValueError, match="no price"):
        await client.get_current_quote("AAPL")


# ─── finnhub company-news client ─────────────────────────────────────────

def _finnhub_client(news=None):
    return FinnhubCompanyNews(
        api_key="test-key",
        company_news=news or (lambda s, f, t: recorded_finnhub_news(s)),
    )


def test_finnhub_conforms_to_protocol():
    assert isinstance(_finnhub_client(), CompanyNewsProvider)


async def test_finnhub_news_maps_and_skips_malformed():
    items = await _finnhub_client().get_company_news("AAPL", SINCE)
    # 3 recorded rows, one without a headline -> 2 items.
    assert len(items) == 2
    assert all(isinstance(i, NewsItem) for i in items)
    assert items[0].headline == "AAPL beats earnings estimates"
    assert items[0].source == "Reuters"
    assert items[0].published_at.tzinfo is not None


async def test_finnhub_news_empty():
    items = await _finnhub_client(news=lambda s, f, t: []).get_company_news("AAPL", SINCE)
    assert items == []


async def test_finnhub_news_failure_propagates():
    def boom(s, f, t):
        raise RuntimeError("finnhub 429")

    with pytest.raises(RuntimeError, match="finnhub 429"):
        await _finnhub_client(news=boom).get_company_news("AAPL", SINCE)


async def test_finnhub_passes_since_as_from_date():
    captured = {}

    def capture(symbol, _from, to):
        captured["from"] = _from
        captured["to"] = to
        return []

    await _finnhub_client(news=capture).get_company_news("AAPL", SINCE)
    assert captured["from"] == "2026-06-01"


# ─── coingecko crypto-data client ────────────────────────────────────────

def _coingecko_client(coin=None, **kw):
    return CoinGeckoCryptoData(
        coin_by_id=coin or (lambda cid: recorded_coingecko_coin(cid)),
        **kw,
    )


def test_coingecko_conforms_to_protocol():
    assert isinstance(_coingecko_client(), CryptoDataProvider)


async def test_coingecko_market_data():
    md = await _coingecko_client().get_market_data("BTC")
    assert md["market_cap"] == pytest.approx(1_280_000_000_000.0)
    assert md["volume_24h"] == pytest.approx(35_000_000_000.0)
    assert md["current_price"] == pytest.approx(65_000.0)
    assert md["circulating_supply"] == pytest.approx(19_700_000.0)


async def test_coingecko_maps_ticker_to_coin_id():
    seen = {}

    def capture(coin_id):
        seen["id"] = coin_id
        return recorded_coingecko_coin(coin_id)

    await _coingecko_client(coin=capture).get_market_data("BTC")
    assert seen["id"] == "bitcoin"  # BTC -> bitcoin via the default map


async def test_coingecko_unknown_symbol_falls_back_to_lowercase():
    seen = {}

    def capture(coin_id):
        seen["id"] = coin_id
        return {"market_data": {}}

    await _coingecko_client(coin=capture).get_market_data("WEIRD")
    assert seen["id"] == "weird"


async def test_coingecko_missing_fields_become_none():
    md = await _coingecko_client(coin=lambda cid: {"market_data": {}}).get_market_data("BTC")
    assert md["market_cap"] is None
    assert md["volume_24h"] is None


async def test_coingecko_crypto_news_empty():
    # CoinGecko is not a news source — mirrors the fake's empty return.
    assert await _coingecko_client().get_crypto_news("BTC", SINCE) == []
