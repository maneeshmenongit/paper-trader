"""Predict agent tests (Wave 2.5 Task 7). Provisional momentum-only; View/NoView."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.agents.predict import PredictAgent
from paper_trader.domain import NoView, PaperPortfolio, ResearchBundle, View
from paper_trader.graph.state import CycleState
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def predict_skill(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    with reg.connection() as conn:
        return load_skill(conn, version_id_for("predict"))


def _bundle(symbol, closes):
    return ResearchBundle(
        symbol=symbol,
        ohlcv=[{"close": c} for c in closes],
    )


def _state(bundles):
    return CycleState(
        cycle_id="cyc-1", started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[], calibration_version="identity-v1",
        research_bundles={b.symbol: b for b in bundles},
    )


# ─── declared roster read + reported; only momentum implemented ──────────

def test_reads_and_reports_full_roster(predict_skill):
    agent = PredictAgent(predict_skill)
    assert agent.declared_roster == ["momentum", "mean_reversion", "arima"]
    assert agent.implemented == ["momentum"]
    assert agent.unimplemented_roster() == ["mean_reversion", "arima"]


def test_confidence_threshold_from_skill(predict_skill):
    agent = PredictAgent(predict_skill)
    assert agent.confidence_threshold == 0.60


# ─── emits View/NoView union, never DirectionalPrediction ────────────────

async def test_emits_view_for_strong_move(predict_skill):
    # a large up-move -> confident momentum View
    state = await PredictAgent(predict_skill).run(_state([_bundle("AAPL", [100.0, 110.0])]))
    v = state.predictions["AAPL"]
    assert isinstance(v, View)
    assert v.method_selected == "momentum"
    assert v.selection_mode == "rule"          # R3
    assert v.selection_rationale is None        # C3: rationale iff llm
    assert v.direction == "UP"
    assert v.is_baseline is False


async def test_noview_when_no_history(predict_skill):
    # only one close -> momentum ineligible (R1) -> NoView (R2)
    state = await PredictAgent(predict_skill).run(_state([_bundle("AAPL", [100.0])]))
    nv = state.predictions["AAPL"]
    assert isinstance(nv, NoView)
    assert nv.reason == "no_eligible_method"    # C2: non-empty reason


async def test_noview_below_confidence(predict_skill):
    # a tiny move -> confidence below 0.60 -> NoView(below_confidence_threshold) (C1)
    state = await PredictAgent(predict_skill).run(_state([_bundle("AAPL", [100.0, 100.001])]))
    nv = state.predictions["AAPL"]
    assert isinstance(nv, NoView)
    assert nv.reason == "below_confidence_threshold"


# ─── C4: momentum baseline shadow, tagged, independent of selection ──────

async def test_baseline_shadow_computed_and_tagged(predict_skill):
    # even when the View is a NoView (tiny move), the baseline shadow still computes
    state = await PredictAgent(predict_skill).run(_state([_bundle("AAPL", [100.0, 100.001])]))
    base = state.baseline_predictions["AAPL"]
    assert isinstance(base, View)
    assert base.is_baseline is True
    assert base.method_selected == "momentum"


async def test_baseline_shadow_for_every_symbol(predict_skill):
    bundles = [_bundle("AAPL", [100.0, 110.0]), _bundle("MSFT", [50.0, 45.0])]
    state = await PredictAgent(predict_skill).run(_state(bundles))
    assert set(state.baseline_predictions) == {"AAPL", "MSFT"}
    assert all(b.is_baseline for b in state.baseline_predictions.values())


# ─── no DirectionalPrediction anywhere ───────────────────────────────────

async def test_predictions_are_union_only(predict_skill):
    bundles = [_bundle("AAPL", [100.0, 110.0]), _bundle("TSLA", [100.0])]
    state = await PredictAgent(predict_skill).run(_state(bundles))
    for p in state.predictions.values():
        assert isinstance(p, (View, NoView))
