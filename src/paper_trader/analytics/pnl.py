"""Realized P&L math — the ONE real path (Stage 0 extraction).

Extracted VERBATIM (behavior-identical) from ``agents/postmortem.py`` so the live
loop and the Stage-0 feasibility backtest score through the *same* functions. This
is what makes Stage 0's sanity check #2 (floor cross-check) load-bearing: the
momentum method's P&L and the momentum floor's P&L flow through one code path, so
agreement is a real invariant, not two copies of new code agreeing with each other.

Pure functions, no I/O, no domain-model imports. LONG-only (v1 fence): a position
is entered at ``entry_price`` and closed at ``exit_price`` for ``quantity`` units.

Provenance: the arithmetic here previously lived inline in ``PostMortemAgent._score``
(``simulated_pnl = trade.quantity * (exit_price - trade.entry_price)``) and
``_baseline_pnl`` (``notional * actual_move * direction_sign``). Extraction only —
no formula changed. See ``docs/gate_reports/STAGE0_*`` for the recorded amendment.
"""

from __future__ import annotations


def actual_move_fraction(entry_price: float, exit_price: float) -> float:
    """The realized price move as a fraction of entry (e.g. 0.10 == +10%).

    Mirrors ``(exit_price - trade.entry_price) / trade.entry_price`` from the
    original ``_score``. Caller guarantees ``entry_price != 0`` (a real cached
    close is always > 0; the settlement seam guards this).
    """
    return (exit_price - entry_price) / entry_price


def realized_pnl(entry_price: float, exit_price: float, quantity: float) -> float:
    """Realized P&L for a closed LONG position: ``qty * (exit - entry)``.

    Verbatim from the original ``simulated_pnl`` computation.
    """
    return quantity * (exit_price - entry_price)


def baseline_shadow_pnl(
    notional_value: float,
    actual_move: float,
    baseline_direction_sign: float,
) -> float:
    """Momentum-baseline shadow P&L: what the BASELINE call earned on this
    notional, measured by the REALIZED move (not the predicted magnitude).

    ``baseline_direction_sign`` is +1.0 for a LONG/UP baseline call, -1.0 for a
    DOWN call. Verbatim from ``_baseline_pnl``'s
    ``trade.notional_value * actual_move * direction_sign``. The earlier T4 bug
    multiplied notional by the PREDICTED magnitude (inflating the shadow ~15x on
    the first live settlement); this realized-move form is the fix, preserved here.
    """
    return notional_value * actual_move * baseline_direction_sign
