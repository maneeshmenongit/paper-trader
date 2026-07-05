"""Supervisor decision tests (Wave 2.5 Task 8). Deterministic; Decision B demoted."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

from paper_trader.domain import NoView, PaperPortfolio, PaperTrade, View
from paper_trader.graph import decisions
from paper_trader.graph.state import CycleState

NOW = datetime(2026, 7, 6, tzinfo=UTC)


def _state(**kw):
    return CycleState(
        cycle_id="cyc-1", started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[], calibration_version="identity-v1", **kw,
    )


def _view(direction="UP", is_baseline=False):
    return View(
        symbol="AAPL", method_selected="momentum", selection_mode="rule",
        direction=direction, magnitude_pct=1.0, horizon=24, confidence=0.7,
        is_baseline=is_baseline,
    )


# ─── Decision A: settle-before-scan ──────────────────────────────────────

def test_decision_a_settles_first():
    trade = PaperTrade(prediction_id="p", symbol="AAPL", entry_price=1, quantity=1,
                       notional_value=1, entry_time=NOW, expected_exit_time=NOW)
    assert decisions.decide_after_start(_state(pending_settlements=[trade])) == "postmortem"
    assert decisions.decide_after_start(_state()) == "filter"


# ─── Decision B: RECONCILED — deterministic, no LLM, adaptation not built ─

def test_decision_b_is_deterministic_proceed():
    assert decisions.decide_after_postmortem(_state()) == "filter"
    assert decisions.decide_after_postmortem(_state(budget_exhausted=True)) == "filter"


def test_decision_b_has_no_llm_call_and_slot_dormant():
    src = inspect.getsource(decisions.decide_after_postmortem)
    # no live LLM routing: the always-on Gemini node of ARCH_002 is not built
    assert "llm_router.call" not in src
    assert "post_settlement" not in src.lower()
    # dormant slot exists but always returns inactive
    assert decisions._llm_fallback_active(_state()) is False


def test_decision_b_no_in_cycle_adaptation_field():
    # the demoted trap: no predict_prompt_mode / adaptation state on CycleState
    assert not hasattr(_state(), "predict_prompt_mode")


# ─── Decision C: tradeable gate ──────────────────────────────────────────

def test_decision_c():
    from paper_trader.domain import Asset
    assert decisions.decide_after_filter(_state()) == "end"
    assert decisions.decide_after_filter(
        _state(tradeable_assets=[Asset(symbol="AAPL", kind="stock")])
    ) == "research"


# ─── Decision D: budget downgrade ────────────────────────────────────────

def test_decision_d():
    assert decisions.decide_after_research(_state()) == "predict"
    assert decisions.decide_after_research(_state(budget_exhausted=True)) == "end"


# ─── Decision E: actionable View, NOT "any UP" (DT-5.5) ──────────────────

def test_decision_e_actionable_view():
    assert decisions.decide_after_predict(_state(predictions={"AAPL": _view("UP")})) == "execute"


def test_decision_e_hold_is_not_actionable():
    assert decisions.decide_after_predict(_state(predictions={"AAPL": _view("HOLD")})) == "end"


def test_decision_e_down_is_actionable_signal():
    # direction != HOLD is actionable (DOWN maps to a tracked decision downstream)
    assert decisions.decide_after_predict(_state(predictions={"AAPL": _view("DOWN")})) == "execute"


def test_decision_e_noview_not_actionable():
    assert decisions.decide_after_predict(
        _state(predictions={"AAPL": NoView(symbol="AAPL", reason="no_eligible_method")})
    ) == "end"


def test_decision_e_baseline_shadow_not_actionable():
    # a baseline View must never drive execution (C4 measuring-stick separation)
    assert decisions.decide_after_predict(
        _state(predictions={"AAPL": _view("UP", is_baseline=True)})
    ) == "end"
