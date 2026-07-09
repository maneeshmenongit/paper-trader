"""Stage 0 sanity checks (step 5): each fires on a seeded violation, passes clean."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.backtest import sanity
from paper_trader.backtest.stage0_settlement import TradeOutcome

D1 = datetime(2026, 1, 5, tzinfo=UTC)
D2 = datetime(2026, 1, 6, tzinfo=UTC)


def _entered(symbol="AAPL", pnl=100.0, move=10.0, entry=100.0, exit=110.0):
    return TradeOutcome(
        symbol=symbol, entry_date=D1, exit_date=D2, entered=True, direction="UP",
        entry_price=entry, exit_price=exit, quantity=10.0, pnl=pnl,
        direction_hit=True, actual_move_pct=move,
    )


# ─── #1 ceiling is a hard bound ──────────────────────────────────────────

def test_ceiling_passes_when_below():
    sanity.check_ceiling_is_bound([10.0, -5.0], [20.0, 0.0])


def test_ceiling_fires_per_trade():
    with pytest.raises(sanity.SanityViolationError, match="#1"):
        sanity.check_ceiling_is_bound([25.0], [20.0])


def test_ceiling_aggregate_passes_when_total_under():
    # If every trade is under its ceiling, the aggregate is too (by construction);
    # the aggregate guard is defense-in-depth. Confirm it doesn't false-positive.
    sanity.check_ceiling_is_bound([9.0, 4.0], [10.0, 8.0])


# ─── #2 floor cross-check ────────────────────────────────────────────────

def test_floor_cross_passes_when_equal():
    sanity.check_floor_cross([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])


def test_floor_cross_fires_on_divergence():
    with pytest.raises(sanity.SanityViolationError, match="#2"):
        sanity.check_floor_cross([1.0, 2.0], [1.0, 2.5])


# ─── #3 entry-price realism ──────────────────────────────────────────────

def test_realism_passes_for_real_closes():
    sanity.check_entry_price_realism([_entered()], is_real_close=lambda s, d: True)


def test_realism_fires_on_fabricated_price():
    with pytest.raises(sanity.SanityViolationError, match="#3"):
        sanity.check_entry_price_realism([_entered()], is_real_close=lambda s, d: False)


def test_realism_fires_on_nonpositive_price():
    bad = _entered(entry=0.0)
    with pytest.raises(sanity.SanityViolationError, match="#3"):
        sanity.check_entry_price_realism([bad], is_real_close=lambda s, d: True)


def test_realism_skips_not_entered():
    ne = TradeOutcome(
        symbol="X", entry_date=D1, exit_date=D2, entered=False, direction="DOWN",
        entry_price=None, exit_price=None, quantity=0.0, pnl=0.0,
        direction_hit=None, actual_move_pct=None,
    )
    sanity.check_entry_price_realism([ne], is_real_close=lambda s, d: False)  # no raise


# ─── #4 no look-ahead ────────────────────────────────────────────────────

def test_no_lookahead_passes_strictly_before():
    sanity.check_no_lookahead(decision_index=30, history_len=30)


def test_no_lookahead_fires_on_peek():
    with pytest.raises(sanity.SanityViolationError, match="#4"):
        sanity.check_no_lookahead(decision_index=30, history_len=31)


# ─── #5 non-zero settlement ──────────────────────────────────────────────

def test_nonzero_passes_on_real_moves():
    sanity.check_nonzero_settlement([_entered(move=10.0), _entered(move=-3.0)])


def test_nonzero_fires_on_all_flat():
    with pytest.raises(sanity.SanityViolationError, match="#5"):
        sanity.check_nonzero_settlement([_entered(move=0.0), _entered(move=0.0)])


def test_nonzero_fires_when_nothing_entered():
    with pytest.raises(sanity.SanityViolationError, match="#5"):
        sanity.check_nonzero_settlement([])
