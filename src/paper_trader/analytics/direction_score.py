"""Direction hit/miss scoring — the ONE real path (Stage 0 extraction).

Extracted VERBATIM (behavior-identical) from ``agents/postmortem.py`` so the live
loop and the Stage-0 feasibility backtest judge direction through the *same*
function. LONG-only (v1 fence): the call is "correct" when the price did not fall.

Provenance: ``direction_correct = exit_price >= trade.entry_price`` in the original
``PostMortemAgent._score`` (a flat close counts as correct — preserved exactly).
Any future SHORT/DOWN scoring is a Stage-3+ change, recorded via the register
(review finding L3), not made here.
"""

from __future__ import annotations


def direction_correct(entry_price: float, exit_price: float) -> bool:
    """LONG-only hit/miss: True when the price rose or held flat.

    Verbatim from ``exit_price >= trade.entry_price``. A flat close (== entry) is
    scored a hit, matching the live loop's behavior bit-for-bit.
    """
    return exit_price >= entry_price
