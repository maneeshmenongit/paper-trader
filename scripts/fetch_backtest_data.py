"""CLI: python scripts/fetch_backtest_data.py [--force] [--universe-file PATH]

Fetches the default universe (or a custom one) and reports cache stats.

Exit code: 0 if all requested symbols succeeded, 1 if any failed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from paper_trader.backtest import historical_fetch
from paper_trader.backtest.universe import DEFAULT_UNIVERSE


def load_universe(universe_file: str | None) -> list[str]:
    if not universe_file:
        return list(DEFAULT_UNIVERSE)
    text = Path(universe_file).read_text()
    symbols = [line.strip().upper() for line in text.splitlines()]
    return [s for s in symbols if s and not s.startswith("#")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch historical OHLCV for the backtest universe."
    )
    parser.add_argument("--force", action="store_true", help="re-fetch even if cached")
    parser.add_argument(
        "--universe-file",
        help="path to a text file with one symbol per line (default: built-in 50-stock universe)",
    )
    parser.add_argument("--lookback-years", type=int, default=2)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    symbols = load_universe(args.universe_file)
    end = date.today()
    start = end - timedelta(days=args.lookback_years * 365)

    pre = historical_fetch.cache_stats(symbols, start, end)["pre_existing"]

    results = historical_fetch.fetch_universe(
        symbols,
        lookback_years=args.lookback_years,
        force=args.force,
    )

    succeeded = set(results)
    failed = [s for s in symbols if s not in succeeded]
    # "Newly fetched" = succeeded that were not already cached-and-covering, or all if --force.
    newly_fetched = len(succeeded) if args.force else max(0, len(succeeded) - pre)

    cache_dir = historical_fetch.CACHE_DIR
    total_bytes = (
        sum(p.stat().st_size for p in cache_dir.glob("*.parquet")) if cache_dir.exists() else 0
    )

    print("─" * 60)
    print("Backtest data fetch summary")
    print(f"  Symbols requested:       {len(symbols)}")
    print(f"  Cached pre-existing:     {pre}")
    print(f"  Newly fetched:           {newly_fetched}")
    print(f"  Failed:                  {len(failed)}" + (f"  {failed}" if failed else ""))
    print(f"  Total cache size:        {total_bytes / 1_000_000:.2f} MB")
    print(f"  Cache dir:               {cache_dir}")
    print("─" * 60)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
