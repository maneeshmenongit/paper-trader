"""Cycle-id generation (DT-4.1, Wave 3 Task 2).

cycle_id becomes a ULID: monotonic, ordered, 26-char TEXT (spec §5.1 requires a
stable orderable id for replay). The timestamp component is taken from the
INJECTED Clock — never wall-clock — so cycles remain deterministic under a frozen
clock in tests and replay ordering reflects real cycle time.

TEXT-compatible: a ULID is a 26-char string, so every consumer that stored a
uuid4 str (cycle_runs, predictions, trade_decisions, paper_trades, checkpointer
keys, Store A cycle_id) accepts it unchanged — no schema or type change.
"""

from __future__ import annotations

from typing import Any

from ulid import ULID


def new_cycle_id(clock: Any) -> str:
    """Return a fresh ULID cycle_id timestamped from the injected clock."""
    return str(ULID.from_datetime(clock.now()))
