"""Replay markdown-render tests (Wave 6 Task 3, I-7/DT-13.3). Read-only."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.replay import Replay, render_markdown
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
CID = "01REPLAYMARKDOWNCYCLE00AA"


@pytest.fixture
def rec(tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(registry, created_at="2026-07-05T00:00:00Z")
    store_a.insert_cycle_header(
        cycle_id=CID, application_id="paper-trader", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), trigger_kind="schedule",
        orchestrator_input=json.dumps({"watchlist": [{"symbol": "WLIST_MARK"}]}),
        orchestrator_decision=json.dumps({"completed_agents": ["predict"]}),
        decision_mode="rule", orchestrator_rationale=None, status="completed")
    store_a.insert_agent_invocation(
        invocation_id=f"{CID}:000", cycle_id=CID, application_id="paper-trader",
        agent_name="predict", skill_version_id=version_id_for("predict"),
        agent_input=json.dumps({"IN_MARK": 1}), agent_output=json.dumps({"OUT_MARK": 2}),
        started_at=NOW.isoformat(), ended_at=NOW.isoformat(), status="completed")
    store_b.insert_ledger_entry(
        entry_id=f"{CID}:obs:000", cycle_id=CID, invocation_id=f"{CID}:000",
        observed_at=NOW.isoformat(), author="correction-officer",
        subject="predict/" + version_id_for("predict"),
        observation_type="outcome-mismatch",
        evidence=json.dumps({"original_prediction_ref": "ORIG_REF_MARK"}))
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=registry.path)
    return replay.reconstruct(CID)


def test_markdown_contains_all_four_sources(rec):
    md = render_markdown(rec)
    # (1) frozen situation
    assert "Frozen situation" in md
    assert "WLIST_MARK" in md               # frozen input
    assert "decision_mode" in md and "rule" in md
    assert "status" in md and "completed" in md
    # (2)+(3) agent decision + skill version + content
    assert "predict" in md
    assert version_id_for("predict") in md  # the version it ran under
    assert "IN_MARK" in md and "OUT_MARK" in md
    assert "mandate" in md                  # content-in-row rendered
    # (4) observer findings incl. cross-cycle reference
    assert "outcome-mismatch" in md
    assert "ORIG_REF_MARK" in md


def test_markdown_trust_line_verified(rec):
    md = render_markdown(rec)
    assert "VERIFIED" in md
    assert "All skill pins hash-VERIFIED" in md


def test_markdown_untrusted_flag(tmp_path):
    # a tampered pin surfaces a loud UNTRUSTED banner
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    with registry.connection() as conn:
        conn.execute(
            "INSERT INTO skill_versions (version_id, application_id, agent_name, "
            "skill_name, version_ordinal, content_hash, content, parent_version_id, "
            "created_by_proposal_id, origin, grounding_refs, validation_status, "
            "validation_updated_at, validation_evidence_refs, created_at) VALUES "
            "('paper-trader/predict/predict@bad','paper-trader','predict','predict',9,"
            "'0000','tampered',NULL,NULL,'initial-authoring',NULL,'UNVALIDATED',?,NULL,?)",
            (NOW.isoformat(), NOW.isoformat()))
    store_a.insert_cycle_header(
        cycle_id="c", application_id="paper-trader", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), trigger_kind="manual", orchestrator_input="{}",
        orchestrator_decision="{}", decision_mode="rule", orchestrator_rationale=None,
        status="completed")
    store_a.insert_agent_invocation(
        invocation_id="c:000", cycle_id="c", application_id="paper-trader",
        agent_name="predict", skill_version_id="paper-trader/predict/predict@bad",
        agent_input="{}", agent_output="{}", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), status="completed")
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=registry.path)
    md = render_markdown(replay.reconstruct("c"))
    assert "UNTRUSTED" in md
    assert "failed hash verification" in md


def test_markdown_meaningful_silence(tmp_path):
    # a cycle with no ledger entries renders the "meaningful silence" note
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(registry, created_at="2026-07-05T00:00:00Z")
    store_a.insert_cycle_header(
        cycle_id="c", application_id="paper-trader", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), trigger_kind="manual", orchestrator_input="{}",
        orchestrator_decision="{}", decision_mode="rule", orchestrator_rationale=None,
        status="completed")
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=registry.path)
    md = render_markdown(replay.reconstruct("c"))
    assert "meaningful silence" in md
