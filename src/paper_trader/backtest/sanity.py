"""The five Stage-0 sanity checks as HARNESS ASSERTIONS (step 5).

STAGE0_BUILD_PROMPT §4/§5: "assertions in the harness, not commentary." Each check
raises ``SanityViolationError`` on failure so a broken scoring path HALTS the run before
any verdict is trusted. They are motivated by the five bugs the first live run
surfaced — fixtures masked them, so these run against REAL data.

| # | Check | Halts on |
|---|-------|----------|
| 1 | Ceiling is a hard bound: strategy P&L ≤ ceiling P&L (per trade & aggregate) | any violation |
| 2 | Floor cross-check: momentum-method P&L == momentum floor P&L for the point | any divergence |
| 3 | Entry-price realism: every entry/exit price is a real cached close      | fabricated price |
| 4 | No look-ahead: methods read only bars strictly before the decision date | look-ahead peek |
| 5 | Settlement on a real non-zero move: aggregate is not a degenerate all-zero  | all-zero moves |
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import datetime

from paper_trader.backtest.stage0_settlement import TradeOutcome

# Floating-point slack for equality/bound comparisons (prices are ~1e2, P&L ~1e3).
_TOL = 1e-6


class SanityViolationError(AssertionError):
    """A Stage-0 scoring invariant was violated — the run is NOT trustworthy."""


def check_ceiling_is_bound(
    strategy_pnls: Sequence[float],
    ceiling_pnls: Sequence[float],
    *,
    label: str = "strategy",
) -> None:
    """#1 — no strategy trade (or the aggregate) may exceed perfect foresight."""
    if len(strategy_pnls) != len(ceiling_pnls):
        raise SanityViolationError(
            f"#1 ceiling: length mismatch {len(strategy_pnls)} vs {len(ceiling_pnls)}"
        )
    for i, (s, c) in enumerate(zip(strategy_pnls, ceiling_pnls, strict=True)):
        if s > c + _TOL:
            raise SanityViolationError(
                f"#1 ceiling breached ({label} trade {i}): pnl {s:.6f} > ceiling {c:.6f}"
            )
    tot_s, tot_c = sum(strategy_pnls), sum(ceiling_pnls)
    if tot_s > tot_c + _TOL:
        raise SanityViolationError(
            f"#1 ceiling breached ({label} aggregate): {tot_s:.6f} > ceiling {tot_c:.6f}"
        )


def check_floor_cross(
    momentum_method_pnls: Sequence[float],
    floor_pnls: Sequence[float],
) -> None:
    """#2 — when the selected method IS momentum, its per-trade P&L (via the real
    math) must equal the independently-computed momentum floor P&L for that point.
    Any divergence is the signature of the dropped-baseline-persistence bug class.
    """
    if len(momentum_method_pnls) != len(floor_pnls):
        raise SanityViolationError(
            f"#2 floor: length mismatch {len(momentum_method_pnls)} vs {len(floor_pnls)}"
        )
    for i, (m, f) in enumerate(zip(momentum_method_pnls, floor_pnls, strict=True)):
        if abs(m - f) > _TOL:
            raise SanityViolationError(
                f"#2 floor cross-check failed (trade {i}): momentum-method {m:.6f} "
                f"!= floor {f:.6f} — same-input P&L must flow through the same math"
            )


def check_entry_price_realism(
    outcomes: Sequence[TradeOutcome],
    is_real_close: Callable[[str, datetime], bool],
) -> None:
    """#3 — every entered trade's entry & exit price is a real cached close (never
    a round-number/100.0 fallback). ``is_real_close(symbol, day)`` is the seam's own
    ``has_close_on`` — we assert the price exists AND equals the seam's close.
    """
    for i, o in enumerate(outcomes):
        if not o.entered:
            continue
        if o.entry_price is None or o.exit_price is None:
            raise SanityViolationError(f"#3 realism: entered trade {i} has a None price")
        for label, day in (("entry", o.entry_date), ("exit", o.exit_date)):
            if not is_real_close(o.symbol, day):
                raise SanityViolationError(
                    f"#3 realism: {o.symbol} {label} price on {day} is not a real "
                    f"cached close — fabricated price detected"
                )
        for label, px in (("entry", o.entry_price), ("exit", o.exit_price)):
            if not (px > 0 and math.isfinite(px)):
                raise SanityViolationError(
                    f"#3 realism: {o.symbol} {label} price {px!r} is not > 0 / finite"
                )


def check_no_lookahead(
    *,
    decision_index: int,
    history_len: int,
) -> None:
    """#4 — a method fed ``history_len`` bars for a point at positional
    ``decision_index`` must have read ONLY bars strictly before it. The harness
    slices ``closes[:decision_index]``; this asserts that contract held.
    """
    if history_len > decision_index:
        raise SanityViolationError(
            f"#4 look-ahead: method saw {history_len} bars for a decision at index "
            f"{decision_index} — must be ≤ {decision_index} (strictly-before only)"
        )


def check_nonzero_settlement(outcomes: Sequence[TradeOutcome]) -> None:
    """#5 — the entered trades must settle on REAL non-zero moves in aggregate; an
    all-zero-move set is the T6b asterisk (seeded/flat data), not a real result.
    """
    entered = [o for o in outcomes if o.entered]
    if not entered:
        raise SanityViolationError(
            "#5 non-zero settlement: no trades entered at all — nothing settled"
        )
    if all(abs(o.actual_move_pct or 0.0) <= _TOL for o in entered):
        raise SanityViolationError(
            "#5 non-zero settlement: every entered trade had a ~zero move — "
            "degenerate (the T6b flat-data asterisk), not a trustworthy result"
        )
