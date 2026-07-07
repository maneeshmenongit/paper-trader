"""Config-authored watchlist (Live-Operation T3).

The watchlist is what Filter validates each cycle; it determines which data
clients matter and whether the ratified R2 liquidity floors bind ($10M stocks /
$50M crypto — filter@v1). An all-large/mid-cap list means R2 is effectively
dormant, which the authority (§3 T3) says is fine.

Authored as TOML (stdlib ``tomllib`` — no new dependency), parsed into the domain
``Asset`` type Filter already consumes. Kept out of the frozen trace: the
watchlist is frozen per-cycle via the header's ``watchlist`` snapshot
(graph/freeze.py) as the symbols that were in effect — not as a secret.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from paper_trader.domain import Asset

_VALID_KINDS = {"stock", "crypto"}


def load_watchlist(path: Path) -> list[Asset]:
    """Load and validate the watchlist TOML into a list of domain Assets.

    Schema::

        [[asset]]
        symbol = "AAPL"
        kind = "stock"      # "stock" | "crypto"
        sector = "Technology"   # optional

    Raises ``ValueError`` on a malformed entry (unknown kind, missing symbol) —
    a bad watchlist is an operator error to surface at boot, not a silent skip.
    """
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return parse_watchlist(data)


def parse_watchlist(data: dict[str, object]) -> list[Asset]:
    """Parse a decoded watchlist mapping (split out for network-free tests)."""
    raw = data.get("asset")
    if not isinstance(raw, list):
        raise ValueError("watchlist must contain an [[asset]] array")

    assets: list[Asset] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"watchlist entry is not a table: {entry!r}")
        symbol = entry.get("symbol")
        kind = entry.get("kind")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"watchlist entry missing a symbol: {entry!r}")
        if kind != "stock" and kind != "crypto":
            raise ValueError(f"{symbol}: kind must be one of {_VALID_KINDS}, got {kind!r}")
        if symbol in seen:
            raise ValueError(f"duplicate watchlist symbol: {symbol}")
        seen.add(symbol)
        sector = entry.get("sector")
        assets.append(
            Asset(
                symbol=symbol,
                kind=kind,
                sector=sector if isinstance(sector, str) else None,
            )
        )
    if not assets:
        raise ValueError("watchlist is empty")
    return assets
