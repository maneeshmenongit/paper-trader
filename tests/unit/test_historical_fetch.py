"""Unit tests for the historical OHLCV fetcher. yfinance is mocked — no network."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from paper_trader.backtest import historical_fetch


def _fake_ohlcv(start: str, periods: int, multiindex: bool = True) -> pd.DataFrame:
    """Build a yfinance-shaped frame. Recent yfinance uses a (field, ticker) MultiIndex."""
    idx = pd.bdate_range(start=start, periods=periods, name="Date")
    fields = ["Open", "High", "Low", "Close", "Volume", "Adj Close"]
    data = {f: [float(i + 1) for i in range(periods)] for f in fields}
    df = pd.DataFrame(data, index=idx)
    if multiindex:
        df.columns = pd.MultiIndex.from_product([fields, ["AAPL"]])
    return df


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "historical"


def test_fetch_one_downloads_and_caches(cache_dir):
    fake = _fake_ohlcv("2024-01-01", 60)
    with patch.object(historical_fetch.yf, "download", return_value=fake) as mock_dl:
        df = historical_fetch.fetch_one(
            "AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir
        )
    mock_dl.assert_called_once()
    # MultiIndex columns are flattened to plain field names.
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume", "Adj Close"]
    assert (cache_dir / "AAPL.parquet").exists()


def test_fetch_one_cache_hit_no_network(cache_dir):
    fake = _fake_ohlcv("2024-01-01", 60)
    with patch.object(historical_fetch.yf, "download", return_value=fake) as mock_dl:
        historical_fetch.fetch_one("AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)
        assert mock_dl.call_count == 1
        # Second call covering the same range must NOT hit the network.
        historical_fetch.fetch_one("AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)
        assert mock_dl.call_count == 1


def test_fetch_one_force_refetches(cache_dir):
    fake = _fake_ohlcv("2024-01-01", 60)
    with patch.object(historical_fetch.yf, "download", return_value=fake) as mock_dl:
        historical_fetch.fetch_one("AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)
        historical_fetch.fetch_one(
            "AAPL", date(2024, 1, 1), date(2024, 3, 1), force=True, cache_dir=cache_dir
        )
        assert mock_dl.call_count == 2


def test_fetch_one_stale_cache_refetches(cache_dir):
    """A cache that doesn't cover the requested start should trigger a refetch."""
    short = _fake_ohlcv("2024-02-01", 20)  # starts after requested start
    full = _fake_ohlcv("2024-01-01", 60)
    with patch.object(historical_fetch.yf, "download", side_effect=[short, full]) as mock_dl:
        historical_fetch.fetch_one("AAPL", date(2024, 2, 1), date(2024, 3, 1), cache_dir=cache_dir)
        # Now ask for an earlier start the cache doesn't cover → refetch.
        historical_fetch.fetch_one("AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)
        assert mock_dl.call_count == 2


def test_fetch_one_raises_on_empty(cache_dir):
    with patch.object(historical_fetch.yf, "download", return_value=pd.DataFrame()):
        with pytest.raises(ValueError, match="no data"):
            historical_fetch.fetch_one("ZZZZ", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)


def test_fetch_one_raises_on_missing_columns(cache_dir):
    bad = pd.DataFrame(
        {"Open": [1.0], "Close": [2.0]},
        index=pd.bdate_range("2024-01-01", periods=1, name="Date"),
    )
    with patch.object(historical_fetch.yf, "download", return_value=bad):
        with pytest.raises(ValueError, match="missing expected columns"):
            historical_fetch.fetch_one("AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)


def test_fetch_universe_continues_past_failures(cache_dir):
    good = _fake_ohlcv("2024-01-01", 60)

    def fake_download(symbol, **kwargs):
        if symbol == "BAD":
            return pd.DataFrame()  # triggers ValueError inside fetch_one
        return good

    with patch.object(historical_fetch.yf, "download", side_effect=fake_download):
        results = historical_fetch.fetch_universe(
            ["AAPL", "BAD", "MSFT"],
            lookback_years=1,
            cache_dir=cache_dir,
            today=date(2024, 3, 1),
        )
    assert set(results) == {"AAPL", "MSFT"}
    assert "BAD" not in results


def test_load_cached_skips_missing(cache_dir):
    fake = _fake_ohlcv("2024-01-01", 60)
    with patch.object(historical_fetch.yf, "download", return_value=fake):
        historical_fetch.fetch_one("AAPL", date(2024, 1, 1), date(2024, 3, 1), cache_dir=cache_dir)
    loaded = historical_fetch.load_cached(["AAPL", "NOPE"], cache_dir=cache_dir)
    assert set(loaded) == {"AAPL"}
