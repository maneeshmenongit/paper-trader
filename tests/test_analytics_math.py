"""Analytics math (Stage 0 extraction) — the ONE real P&L/direction path.

These functions were extracted VERBATIM from PostMortemAgent. The invariant that
matters: they must reproduce the live loop's arithmetic exactly, so the Stage-0
backtest scoring through them is scoring through the *real* path. The
behavior-identical proof for the live loop is test_postmortem_agent.py staying
green; these tests pin the extracted functions directly.
"""

from __future__ import annotations

import math

import pytest

from paper_trader.analytics.direction_score import direction_correct
from paper_trader.analytics.pnl import (
    actual_move_fraction,
    baseline_shadow_pnl,
    realized_pnl,
)


def test_realized_pnl_gain():
    assert realized_pnl(100.0, 110.0, 10.0) == pytest.approx(100.0)


def test_realized_pnl_loss():
    assert realized_pnl(100.0, 90.0, 10.0) == pytest.approx(-100.0)


def test_realized_pnl_flat_is_zero():
    assert realized_pnl(100.0, 100.0, 10.0) == pytest.approx(0.0)


def test_actual_move_fraction():
    assert actual_move_fraction(100.0, 110.0) == pytest.approx(0.10)
    assert actual_move_fraction(100.0, 90.0) == pytest.approx(-0.10)


def test_direction_correct_long_only():
    assert direction_correct(100.0, 110.0) is True
    assert direction_correct(100.0, 90.0) is False


def test_direction_correct_flat_counts_as_hit():
    # Verbatim: exit >= entry. A flat close is a hit (matches live loop).
    assert direction_correct(100.0, 100.0) is True


def test_baseline_shadow_up_call():
    # UP baseline (+1) on a +10% move over $1000 notional == +$100.
    assert baseline_shadow_pnl(1000.0, 0.10, 1.0) == pytest.approx(100.0)


def test_baseline_shadow_down_call_inverts():
    # DOWN baseline (-1) on a +10% move == -$100 (the call was wrong).
    assert baseline_shadow_pnl(1000.0, 0.10, -1.0) == pytest.approx(-100.0)


def test_pnl_functions_are_finite():
    assert math.isfinite(realized_pnl(100.0, 110.0, 10.0))
    assert math.isfinite(baseline_shadow_pnl(1000.0, 0.10, 1.0))
