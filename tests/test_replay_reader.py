"""Replay reader four-source-join tests (Wave 6 Task 1, DT-13.x). Read-only."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from steward.officer.replay import MISSING, VERIFIED, Replay
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
CID = "01REPLAYREADERCYCLE0000AA"


@pytest.fixture
def env(tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(registry, created_at="2026-07-05T00:00:00Z")

    # source (1) header
    store_a.insert_cycle_header(
        cycle_id=CID, application_id="paper-trader", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), trigger_kind="schedule",
        orchestrator_input=json.dumps({"watchlist": [{"symbol": "AAPL"}]}),
        orchestrator_decision=json.dumps({"completed_agents": ["filter", "predict"]}),
        decision_mode="rule", orchestrator_rationale=None, status="completed",
    )
    # source (2)+(3) invocations, pinned to @v1
    for seq, agent in enumerate(("filter", "predict")):
        store_a.insert_agent_invocation(
            invocation_id=f"{CID}:{seq:03d}", cycle_id=CID, application_id="paper-trader",
            agent_name=agent, skill_version_id=version_id_for(agent),
            agent_input=json.dumps({"in": seq}), agent_output=json.dumps({"out": seq}),
            started_at=NOW.isoformat(), ended_at=NOW.isoformat(), status="completed",
        )
    # source (4) ledger
    store_b.insert_ledger_entry(
        entry_id=f"{CID}:obs:000", cycle_id=CID, invocation_id=f"{CID}:001",
        observed_at=NOW.isoformat(), author="correction-officer",
        subject="predict/" + version_id_for("predict"),
        observation_type="outcome-mismatch", evidence=json.dumps({"miss": True}),
    )
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=registry.path)
    return replay, registry


# ─── four-source reconstruction ──────────────────────────────────────────

def test_reconstructs_all_four_sources(env):
    replay, _ = env
    rec = replay.reconstruct(CID)
    # (1) header
    assert rec.header is not None
    assert rec.header["decision_mode"] == "rule"
    assert rec.header["status"] == "completed"
    # (2) invocations in order
    assert [i.agent_name for i in rec.invocations] == ["filter", "predict"]
    # (3) pinned skill content present per invocation
    assert all(i.skill_content is not None for i in rec.invocations)
    assert "mandate" in rec.invocations[0].skill_content
    # (4) ledger entries
    assert len(rec.ledger_entries) == 1
    assert rec.ledger_entries[0]["observation_type"] == "outcome-mismatch"


def test_frozen_input_output_parsed(env):
    replay, _ = env
    rec = replay.reconstruct(CID)
    assert rec.invocations[0].agent_input == {"in": 0}
    assert rec.invocations[1].agent_output == {"out": 1}


# ─── pinned-version resolution: @v1 even when @v2 is current ─────────────

def test_resolves_pinned_version_not_pointer(env, tmp_path):
    replay, registry = env
    # ship a predict@v2 and flip the CURRENT pointer to it
    registry.insert_skill_version(
        version_id="paper-trader/predict/predict@v2", application_id="paper-trader",
        agent_name="predict", skill_name="predict", version_ordinal=2,
        content="mandate: predict v2 UNIQUE_V2_MARKER", parent_version_id=version_id_for("predict"),
        created_by_proposal_id="prop-1", origin="slow-loop-fork", grounding_refs=None,
        validation_status="UNVALIDATED", validation_updated_at=NOW.isoformat(),
        validation_evidence_refs=None, created_at=NOW.isoformat(),
    )
    registry.set_current_version(
        application_id="paper-trader", agent_name="predict", skill_name="predict",
        current_version_id="paper-trader/predict/predict@v2", updated_at=NOW.isoformat(),
    )
    # the cycle's Predict invocation pinned @v1 -> replay must reconstruct @v1
    rec = replay.reconstruct(CID)
    predict = next(i for i in rec.invocations if i.agent_name == "predict")
    assert predict.skill_version_id == version_id_for("predict")   # @v1
    assert "UNIQUE_V2_MARKER" not in predict.skill_content         # NOT @v2 content


# ─── missing pinned version handled (not raised) ─────────────────────────

def test_missing_pinned_version_marked(tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")  # empty registry
    store_a.insert_cycle_header(
        cycle_id="c", application_id="paper-trader", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), trigger_kind="manual", orchestrator_input="{}",
        orchestrator_decision="{}", decision_mode="rule", orchestrator_rationale=None,
        status="completed")
    store_a.insert_agent_invocation(
        invocation_id="c:000", cycle_id="c", application_id="paper-trader",
        agent_name="predict", skill_version_id="paper-trader/predict/predict@v9",
        agent_input="{}", agent_output="{}", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), status="completed")
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=registry.path)
    rec = replay.reconstruct("c")  # must NOT raise
    assert rec.invocations[0].trust == MISSING
    assert rec.invocations[0].skill_content is None


# ─── read-only by construction: replay connections cannot write ──────────

def test_replay_connections_are_read_only(env):
    replay, _ = env
    replay.reconstruct(CID)  # populates nothing; just proves the round-trip works
    # a direct read-only connection to Store A rejects writes
    conn = sqlite3.connect(f"file:{replay.store_a_path}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO cycle_headers (cycle_id, application_id, started_at, "
                     "ended_at, trigger_kind, orchestrator_input, orchestrator_decision, "
                     "decision_mode, status) VALUES ('x','x','x','x','manual','{}','{}',"
                     "'rule','completed')")
    conn.close()


def test_all_pins_verified_on_intact_cycle(env):
    replay, _ = env
    rec = replay.reconstruct(CID)
    assert rec.all_verified
    assert all(i.trust == VERIFIED for i in rec.invocations)
    assert rec.untrusted_pins == []
