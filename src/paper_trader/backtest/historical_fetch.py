"""Download daily OHLCV from yfinance, cache to local Parquet files.

Cache layout:
    data/backtest/historical/<SYMBOL>.parquet

Idempotency:
    Re-running fetch_universe() does not re-download symbols whose Parquet
    file exists and covers the requested date range. Pass force=True to
    refetch.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/backtest/historical")

# Columns we require every cached frame to carry.
EXPECTED_COLUMNS = ["Open", "High", "Low", "Close", "Volume", "Adj Close"]


def _cache_path(symbol: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / f"{symbol}.parquet"


def _flatten_columns(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """yfinance returns a column MultiIndex (field, ticker) even for one symbol.

    Collapse it to plain field names so the cache schema is stable.
    """
    if isinstance(df.columns, pd.MultiIndex):
        # Drop the ticker level; keep the OHLCV field level.
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def _covers_range(df: pd.DataFrame, start: date, end: date) -> bool:
    """True if the cached frame spans approximately [start, end).

    Only trading days appear in the data, so the requested calendar `start`/`end`
    rarely land on a trading day (weekends, holidays, and yfinance's exclusive
    `end`). We therefore allow a one-week slack at both ends: the cache must begin
    within a week *after* `start` and extend to within a week *before* `end`.
    Without this slack a Saturday `start` would never match the Monday first bar
    and every re-run would re-fetch.
    """
    if df.empty:
        return False
    idx = pd.to_datetime(df.index)
    cached_start = idx.min().date()
    cached_end = idx.max().date()
    return cached_start <= (start + timedelta(days=7)) and cached_end >= (end - timedelta(days=7))


def fetch_one(
    symbol: str,
    start: date,
    end: date,
    force: bool = False,
    cache_dir: Path = CACHE_DIR,
) -> pd.DataFrame:
    """Fetch OHLCV for one symbol. Returns DataFrame indexed by date with
    columns: Open, High, Low, Close, Volume, Adj Close.

    Cache hit returns the cached DataFrame without a network call.
    """
    path = _cache_path(symbol, cache_dir)

    if path.exists() and not force:
        cached = pd.read_parquet(path)
        if _covers_range(cached, start, end):
            logger.info("cache hit: %s", symbol)
            return cached
        logger.info("cache stale (range not covered): %s — refetching", symbol)

    logger.info("fetching: %s [%s..%s]", symbol, start, end)
    df = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
    )
    if df is None or df.empty:
        raise ValueError(f"yfinance returned no data for {symbol}")

    df = _flatten_columns(df, symbol)

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{symbol}: missing expected columns {missing}; got {list(df.columns)}")

    df.index.name = "Date"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def fetch_universe(
    symbols: list[str],
    lookback_years: int = 2,
    force: bool = False,
    cache_dir: Path = CACHE_DIR,
    today: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for many symbols. Returns dict mapping symbol → DataFrame.

    Failures on individual symbols are logged but do not abort the whole run.
    Returns only successfully-fetched symbols in the dict.
    """
    end = today or date.today()
    start = end - timedelta(days=lookback_years * 365)

    results: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            results[symbol] = fetch_one(symbol, start, end, force=force, cache_dir=cache_dir)
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not kill the run
            logger.warning("failed to fetch %s: %s", symbol, exc)
    return results


def load_cached(symbols: list[str], cache_dir: Path = CACHE_DIR) -> dict[str, pd.DataFrame]:
    """Load already-cached frames for `symbols` without any network call.

    Symbols with no cache file are silently skipped. Used by the backtest
    harness, which assumes fetch_backtest_data.py has been run first.
    """
    out: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        path = _cache_path(symbol, cache_dir)
        if path.exists():
            out[symbol] = pd.read_parquet(path)
    return out


def cache_stats(
    symbols: list[str],
    start: date,
    end: date,
    cache_dir: Path = CACHE_DIR,
) -> dict[str, int]:
    """Count how many of `symbols` are already cached and cover [start, end]."""
    pre_existing = 0
    for symbol in symbols:
        path = _cache_path(symbol, cache_dir)
        if path.exists():
            try:
                if _covers_range(pd.read_parquet(path), start, end):
                    pre_existing += 1
            except Exception:  # noqa: BLE001
                pass
    return {"requested": len(symbols), "pre_existing": pre_existing}
