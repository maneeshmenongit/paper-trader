"""v1 check-set predicate tests (Wave 4 Task 3, DT-11.3). Passing + violating each."""

from __future__ import annotations

import pytest

from paper_trader.officer_predicates import (
    build_v1_registry,
    execute_symmetric_logging,
    filter_skips_carry_criterion,
    postmortem_scoring_completeness,
    predict_rationale_iff_llm,
    predict_view_threshold,
    research_call_budget,
)
from steward.officer.predicates import InvocationView
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry


@pytest.fixture
def skills(tmp_path):
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    out = {}
    with reg.connection() as conn:
        for a in ("filter", "research", "predict", "execute", "postmortem"):
            out[a] = load_skill(conn, version_id_for(a))
    return out


def _view(agent, skill, output):
    return InvocationView(
        invocation_id="cyc:000", cycle_id="cyc", agent_name=agent,
        skill_version_id=version_id_for(agent), agent_input={}, agent_output=output,
        skill=skill,
    )


# ─── Execute C2: symmetric logging ───────────────────────────────────────

def test_execute_symmetric_logging_pass(skills):
    out = {"trade_decisions": {"AAPL": {"executed": False, "risk_reason": "below_cap"}}}
    assert execute_symmetric_logging({"id": "C2"}, _view("execute", skills["execute"], out)) == []


def test_execute_symmetric_logging_violation(skills):
    out = {"trade_decisions": {"AAPL": {"executed": False, "risk_reason": None}}}
    divs = execute_symmetric_logging({"id": "C2"}, _view("execute", skills["execute"], out))
    assert len(divs) == 1
    assert divs[0].detail["skips_without_reason"] == ["AAPL"]


# ─── Predict C1: View >= threshold; NoView carries reason ────────────────

def test_predict_view_threshold_pass(skills):
    out = {"predictions": {
        "AAPL": {"confidence": 0.7, "selection_mode": "rule"},
        "TSLA": {"reason": "no_eligible_method"},
    }}
    assert predict_view_threshold({"id": "C1"}, _view("predict", skills["predict"], out)) == []


def test_predict_view_threshold_violation(skills):
    out = {"predictions": {"AAPL": {"confidence": 0.40, "selection_mode": "rule"}}}
    divs = predict_view_threshold({"id": "C1"}, _view("predict", skills["predict"], out))
    assert len(divs) == 1
    assert divs[0].detail["violations"][0]["issue"] == "view_below_threshold"


def test_predict_noview_missing_reason_violation(skills):
    out = {"predictions": {"AAPL": {"reason": ""}}}
    divs = predict_view_threshold({"id": "C1"}, _view("predict", skills["predict"], out))
    assert divs[0].detail["violations"][0]["issue"] == "noview_missing_reason"


# ─── Predict C3: rationale iff llm ───────────────────────────────────────

def test_predict_rationale_pass(skills):
    out = {"predictions": {
        "AAPL": {"confidence": 0.7, "selection_mode": "rule", "selection_rationale": None},
        "MSFT": {"confidence": 0.8, "selection_mode": "llm", "selection_rationale": "why"},
    }}
    assert predict_rationale_iff_llm({"id": "C3"}, _view("predict", skills["predict"], out)) == []


def test_predict_rationale_violation(skills):
    # llm mode but no rationale
    out = {"predictions": {"AAPL": {"confidence": 0.8, "selection_mode": "llm",
                                    "selection_rationale": None}}}
    divs = predict_rationale_iff_llm({"id": "C3"}, _view("predict", skills["predict"], out))
    assert len(divs) == 1


# ─── Filter C1/C2: skips carry criterion ─────────────────────────────────

def test_filter_skip_criterion_pass(skills):
    out = {"skip_reasons": {"AAPL": "market_closed"}}
    assert filter_skips_carry_criterion({"id": "C2"}, _view("filter", skills["filter"], out)) == []


def test_filter_skip_criterion_violation(skills):
    out = {"skip_reasons": {"AAPL": ""}}
    divs = filter_skips_carry_criterion({"id": "C2"}, _view("filter", skills["filter"], out))
    assert divs[0].detail["skips_without_criterion"] == ["AAPL"]


# ─── Research C1: call budget ────────────────────────────────────────────

def test_research_budget_pass(skills):
    out = {"research_bundles": {"AAPL": {"narrative": "one summary"}}}
    assert research_call_budget({"id": "C1"}, _view("research", skills["research"], out)) == []


def test_research_budget_violation(skills):
    out = {"research_bundles": {"AAPL": {"narrative": ["s1", "s2"]}}}  # >1 summary
    divs = research_call_budget({"id": "C1"}, _view("research", skills["research"], out))
    assert divs[0].detail["assets_over_budget"] == ["AAPL"]


# ─── PostMortem C1: scoring completeness ─────────────────────────────────

def test_postmortem_complete_pass(skills):
    out = {"new_post_mortems": [{"direction_correct": True, "simulated_pnl": 1.0}]}
    assert postmortem_scoring_completeness(
        {"id": "C1"}, _view("postmortem", skills["postmortem"], out)) == []


def test_postmortem_incomplete_violation(skills):
    out = {"new_post_mortems": [{"direction_correct": True}]}  # missing simulated_pnl
    divs = postmortem_scoring_completeness(
        {"id": "C1"}, _view("postmortem", skills["postmortem"], out))
    assert divs[0].detail["incomplete_postmortem_rows"] == [0]


# ─── registry completeness: every declared @v1 constraint has a predicate ─

def test_registry_covers_every_declared_constraint(skills):
    reg = build_v1_registry()
    for agent, skill in skills.items():
        for constraint in skill.get("constraints", []):
            assert reg.has(agent, constraint["id"]), \
                f"no predicate for {agent}:{constraint['id']} — would be a build error"


# ─── DT-11.5 outcome-mismatch ────────────────────────────────────────────

def test_outcome_mismatch_on_recorded_miss(skills):
    from paper_trader.officer_predicates import outcome_mismatch_detector

    pm_view = InvocationView(
        invocation_id="cyc:004", cycle_id="cyc", agent_name="postmortem",
        skill_version_id=version_id_for("postmortem"), agent_input={},
        agent_output={"new_post_mortems": [
            {"paper_trade_id": "42", "direction_correct": False,
             "magnitude_error": 3.0, "simulated_pnl": -50.0},
        ]},
        skill=skills["postmortem"],
    )
    divs = outcome_mismatch_detector([pm_view])
    assert len(divs) == 1
    d = divs[0]
    assert d.observation_type == "outcome-mismatch"
    assert d.invocation_id == "cyc:004"                    # cites settling PM invocation
    assert d.detail["original_prediction_ref"] == "42"     # references original


def test_outcome_mismatch_none_on_hit(skills):
    from paper_trader.officer_predicates import outcome_mismatch_detector

    pm_view = InvocationView(
        invocation_id="cyc:004", cycle_id="cyc", agent_name="postmortem",
        skill_version_id=version_id_for("postmortem"), agent_input={},
        agent_output={"new_post_mortems": [{"paper_trade_id": "1", "direction_correct": True}]},
        skill=skills["postmortem"],
    )
    assert outcome_mismatch_detector([pm_view]) == []  # a hit is not a divergence


def test_outcome_mismatch_is_conduct_neutral(skills):
    # a miss is OUTCOME data, tagged outcome-mismatch — NOT constraint-violation
    from paper_trader.officer_predicates import outcome_mismatch_detector

    pm_view = InvocationView(
        invocation_id="i", cycle_id="c", agent_name="postmortem",
        skill_version_id=version_id_for("postmortem"), agent_input={},
        agent_output={"new_post_mortems": [{"paper_trade_id": "1", "direction_correct": False}]},
        skill=skills["postmortem"],
    )
    assert outcome_mismatch_detector([pm_view])[0].observation_type == "outcome-mismatch"
