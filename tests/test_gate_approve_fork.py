"""Atomic-fork approve tests (Wave 5 Task 5, DT-12.1). Fork is gate-only."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.gate import Gate, GateError
from steward.storage.proposals import ProposalStore
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
BASE = version_id_for("predict")           # paper-trader/predict/predict@v1
NEW = "paper-trader/predict/predict@v2"
NEW_CONTENT = "mandate: predict (v2 forked)\nconstraints:\n  - id: C1\n    text: confidence >= 0.65"


class _Clock:
    def now(self):
        return NOW


def _make(tmp_path, *, complexity="low"):
    store_b = StoreB(tmp_path / "store_b.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(registry, created_at="2026-07-05T00:00:00Z")
    # point the pointer at @v1 initially
    registry.set_current_version(
        application_id="paper-trader", agent_name="predict", skill_name="predict",
        current_version_id=BASE, updated_at=NOW.isoformat(),
    )
    store_b.insert_ledger_entry(
        entry_id="e-1", cycle_id="c", invocation_id=None, observed_at=NOW.isoformat(),
        author="correction-officer", subject="predict/" + BASE,
        observation_type="outcome-mismatch", evidence=json.dumps({"x": 1}),
    )
    proposals.insert_proposed(
        proposal_id="prop-1", created_at=NOW.isoformat(), author="correction-officer",
        application_id="paper-trader", evidence_refs=["e-1"],
        target_skill="paper-trader/predict/predict", base_version_id=BASE,
        proposed_change={"raise_threshold": 0.65}, rationale="raise T",
        complexity_tag=complexity,
    )
    return store_b, proposals, registry


def _gate(env, session="s1"):
    store_b, proposals, registry = env
    return Gate(proposal_store=proposals, store_b=store_b, registry=registry,
               clock=_Clock(), session=session)


def _current_pointer(registry):
    return registry.get_current_version_id(
        application_id="paper-trader", agent_name="predict", skill_name="predict")


# ─── full approve: one @v2 row + flipped pointer + IN_WINDOW ─────────────

def test_full_approve_forks_and_windows(tmp_path):
    env = _make(tmp_path, complexity="low")
    _, proposals, registry = env
    ret = _gate(env).approve(
        proposal_id="prop-1", decided_by="alice", decision_note="evidence is solid",
        new_version_id=NEW, new_content=NEW_CONTENT,
    )
    assert ret == NEW

    # exactly one @v2 row exists, forked from @v1
    with registry.connection() as conn:
        row = conn.execute(
            "SELECT * FROM skill_versions WHERE version_id=?", (NEW,)).fetchone()
    assert row is not None
    assert row["parent_version_id"] == BASE
    assert row["created_by_proposal_id"] == "prop-1"
    assert row["origin"] == "slow-loop-fork"
    assert row["validation_status"] == "UNVALIDATED"
    assert row["version_ordinal"] == 2

    # pointer flipped to @v2
    assert _current_pointer(registry) == NEW

    # proposal is IN_WINDOW with a recorded window + note
    rec = proposals.get("prop-1")
    assert rec["status"] == "IN_WINDOW"
    assert rec["new_version_id"] == NEW
    assert rec["decision_note"] == "evidence is solid"
    assert rec["decided_by"] == "alice"
    assert rec["window_opened_at"] == NOW.isoformat()
    window = json.loads(rec["window_closes_at"])
    assert window["min_settled_trades"] == 20
    assert rec["evaluation"] is None  # v1 stub — stays null


# ─── approve requires a non-empty decision_note ──────────────────────────

def test_approve_empty_note_refused(tmp_path):
    env = _make(tmp_path)
    with pytest.raises(GateError):
        _gate(env).approve(proposal_id="prop-1", decided_by="a", decision_note="  ",
                           new_version_id=NEW, new_content=NEW_CONTENT)


# ─── forced failure in (b): no version row, no pointer move, not approved ─

def test_fork_failure_leaves_no_partial_state(tmp_path):
    env = _make(tmp_path)
    _, proposals, registry = env

    # make the registry fork blow up
    def boom(**kw):
        raise RuntimeError("simulated fork failure")

    registry.fork_version = boom  # type: ignore[assignment]

    with pytest.raises(RuntimeError):
        _gate(env).approve(proposal_id="prop-1", decided_by="a", decision_note="note",
                           new_version_id=NEW, new_content=NEW_CONTENT)

    # NO version row, pointer unchanged, proposal reverted to PROPOSED
    assert proposals.get("prop-1")["status"] == "PROPOSED"
    assert proposals.get("prop-1")["decided_at"] is None
    with registry.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM skill_versions WHERE version_id=?",
                            (NEW,)).fetchone()["c"] == 0
    assert _current_pointer(registry) == BASE  # never moved


# ─── the registry fork is itself atomic (pointer never dangles) ──────────

def test_registry_fork_atomic_pointer_never_dangles(tmp_path):
    import sqlite3

    env = _make(tmp_path)
    _, _, registry = env
    # a duplicate version_id makes the INSERT fail; the pointer flip must NOT happen
    with pytest.raises(sqlite3.IntegrityError):
        registry.fork_version(
            base_version_id=BASE, new_version_id=BASE,  # dup PK -> insert fails
            content="x", created_by_proposal_id="prop-1", grounding_refs=None,
            created_at=NOW.isoformat(),
        )
    # pointer still at @v1 (the flip was in the same rolled-back transaction)
    assert _current_pointer(registry) == BASE


# ─── the pointer never references a missing version (invariant) ──────────

def test_pointer_always_references_existing_version(tmp_path):
    env = _make(tmp_path)
    _, _, registry = env
    _gate(env).approve(proposal_id="prop-1", decided_by="a", decision_note="ok",
                       new_version_id=NEW, new_content=NEW_CONTENT)
    current = _current_pointer(registry)
    with registry.connection() as conn:
        exists = conn.execute("SELECT COUNT(*) c FROM skill_versions WHERE version_id=?",
                              (current,)).fetchone()["c"]
    assert exists == 1
