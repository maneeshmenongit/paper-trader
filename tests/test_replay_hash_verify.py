"""Replay hash-verification tests (Wave 6 Task 2, I-8/DT-13.2).

A tampered pin -> UNTRUSTED + CONTINUE (never raise); other pins unaffected.
This is deliberately SOFTER than the Wave 2 runtime loader (which raises).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from steward.officer.replay import UNTRUSTED, VERIFIED, Replay
from steward.storage.content_hash import compute_content_hash
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
CID = "01HASHVERIFYCYCLE000000AA"


def _tamper_insert(registry, version_id, *, agent, content, stored_hash):
    """Stage a row whose stored hash does NOT match its content (out-of-band
    tampering / disk corruption). The no-mutation triggers block UPDATE/DELETE,
    not a crafted INSERT — so a raw INSERT is the way to stage a mismatch."""
    with registry.connection() as conn:
        conn.execute(
            """
            INSERT INTO skill_versions (
                version_id, application_id, agent_name, skill_name, version_ordinal,
                content_hash, content, parent_version_id, created_by_proposal_id,
                origin, grounding_refs, validation_status, validation_updated_at,
                validation_evidence_refs, created_at
            ) VALUES (?, 'paper-trader', ?, ?, 5, ?, ?, NULL, NULL,
                      'initial-authoring', NULL, 'UNVALIDATED', ?, NULL, ?)
            """,
            (version_id, agent, agent, stored_hash, content, NOW.isoformat(), NOW.isoformat()),
        )


@pytest.fixture
def env(tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(registry, created_at="2026-07-05T00:00:00Z")
    store_a.insert_cycle_header(
        cycle_id=CID, application_id="paper-trader", started_at=NOW.isoformat(),
        ended_at=NOW.isoformat(), trigger_kind="schedule", orchestrator_input="{}",
        orchestrator_decision="{}", decision_mode="rule", orchestrator_rationale=None,
        status="completed")
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=registry.path)
    return store_a, store_b, registry, replay


def _inv(store_a, seq, agent, version_id):
    store_a.insert_agent_invocation(
        invocation_id=f"{CID}:{seq:03d}", cycle_id=CID, application_id="paper-trader",
        agent_name=agent, skill_version_id=version_id, agent_input="{}",
        agent_output="{}", started_at=NOW.isoformat(), ended_at=NOW.isoformat(),
        status="completed")


# ─── intact cycle: all pins VERIFIED ─────────────────────────────────────

def test_intact_cycle_all_verified(env):
    store_a, _, _, replay = env
    _inv(store_a, 0, "filter", version_id_for("filter"))
    _inv(store_a, 1, "predict", version_id_for("predict"))
    rec = replay.reconstruct(CID)
    assert rec.all_verified
    for i in rec.invocations:
        assert i.trust == VERIFIED
        assert i.stored_hash == i.recomputed_hash


# ─── tampered row: that pin UNTRUSTED, others VERIFIED, NOT halted ───────

def test_tampered_pin_untrusted_reconstruction_continues(env):
    store_a, _, registry, replay = env
    # a tampered predict version: content changed, stored hash left as the OLD one
    tampered_vid = "paper-trader/predict/predict@tampered"
    real_hash = compute_content_hash("the ORIGINAL content")
    _tamper_insert(registry, tampered_vid, agent="predict",
                   content="the TAMPERED content", stored_hash=real_hash)

    _inv(store_a, 0, "filter", version_id_for("filter"))       # intact
    _inv(store_a, 1, "predict", tampered_vid)                  # tampered

    rec = replay.reconstruct(CID)  # must NOT raise
    by_agent = {i.agent_name: i for i in rec.invocations}
    # the tampered pin is UNTRUSTED, content still rendered (returned, not hidden)
    assert by_agent["predict"].trust == UNTRUSTED
    assert by_agent["predict"].skill_content == "the TAMPERED content"
    assert by_agent["predict"].stored_hash != by_agent["predict"].recomputed_hash
    # the other pin is unaffected
    assert by_agent["filter"].trust == VERIFIED
    # reconstruction reports the untrusted pin loudly
    assert rec.untrusted_pins == [tampered_vid]
    assert rec.all_verified is False


def test_replay_never_raises_on_mismatch(env):
    # even if EVERY pin is tampered, replay returns a reconstruction
    store_a, _, registry, replay = env
    for seq, agent in enumerate(("filter", "predict", "execute")):
        vid = f"paper-trader/{agent}/{agent}@bad{seq}"
        _tamper_insert(registry, vid, agent=agent, content="x",
                       stored_hash="0" * 64)  # deliberately wrong hash
        _inv(store_a, seq, agent, vid)
    rec = replay.reconstruct(CID)  # no raise
    assert len(rec.invocations) == 3
    assert all(i.trust == UNTRUSTED for i in rec.invocations)
