"""Clock implementations (Wave 2.5 Task 2).

The Clock seam (data/interfaces.py) is injected everywhere a time is needed —
agents never call datetime.now(). LiveClock is the wall-clock implementation;
FrozenClock (tests/fixtures) is the deterministic test fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime


class LiveClock:
    """Wall-clock Clock. `is_market_open('crypto')` is always True; 'stock' uses a
    simple NYSE weekday/hours check (9:30–16:00 US Eastern is approximated here as
    a placeholder — a calendar library slots in later without touching agents)."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def is_market_open(self, asset_type: str) -> bool:
        if asset_type == "crypto":
            return True
        # Stocks: weekday check only in v1 (hour-level NYSE calendar is a later
        # refinement; the seam shape is what matters for the domain build).
        now = self.now()
        return now.weekday() < 5
