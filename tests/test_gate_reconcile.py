"""Startup reconciliation tests (Wave 5 Task 6, DT-12.3 crash-safety)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.gate import Gate
from steward.storage.proposals import ProposalStore
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
BASE = version_id_for("predict")
NEW = "paper-trader/predict/predict@v2"
NEW_CONTENT = "mandate: predict v2"


class _Clock:
    def now(self):
        return NOW


def _make(tmp_path):
    store_b = StoreB(tmp_path / "store_b.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(registry, created_at="2026-07-05T00:00:00Z")
    registry.set_current_version(
        application_id="paper-trader", agent_name="predict", skill_name="predict",
        current_version_id=BASE, updated_at=NOW.isoformat())
    store_b.insert_ledger_entry(
        entry_id="e-1", cycle_id="c", invocation_id=None, observed_at=NOW.isoformat(),
        author="correction-officer", subject="predict/" + BASE,
        observation_type="outcome-mismatch", evidence=json.dumps({"x": 1}))
    proposals.insert_proposed(
        proposal_id="prop-1", created_at=NOW.isoformat(), author="correction-officer",
        application_id="paper-trader", evidence_refs=["e-1"],
        target_skill="paper-trader/predict/predict", base_version_id=BASE,
        proposed_change={"raise_threshold": 0.65}, rationale="r", complexity_tag="low")
    return store_b, proposals, registry


def _gate(env, session="s1"):
    store_b, proposals, registry = env
    return Gate(proposal_store=proposals, store_b=store_b, registry=registry,
               clock=_Clock(), session=session)


def _pointer(registry):
    return registry.get_current_version_id(
        application_id="paper-trader", agent_name="predict", skill_name="predict")


# ─── crash between (b) and (c): fork committed, bookkeeping not done ─────

def test_reconcile_completes_window_after_bc_crash(tmp_path):
    env = _make(tmp_path)
    _, proposals, registry = env
    g = _gate(env)

    # make step (c) fail -> simulates crash after the fork committed
    def boom(*a, **k):
        raise RuntimeError("crash before window")

    proposals.set_in_window = boom  # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        g.approve(proposal_id="prop-1", decided_by="a", decision_note="ok",
                  new_version_id=NEW, new_content=NEW_CONTENT)

    # state after crash: APPROVED, fork committed, pointer flipped, NOT IN_WINDOW
    assert proposals.get("prop-1")["status"] == "APPROVED"
    assert registry.version_by_proposal("prop-1")["version_id"] == NEW
    assert _pointer(registry) == NEW

    # a FRESH gate reconciles at startup -> completes the window
    fresh = _gate((env[0], ProposalStore(tmp_path / "proposals.sqlite"), registry))
    actions = fresh.reconcile()
    assert {"proposal_id": "prop-1", "action": "completed_window"} in actions
    rec = fresh.proposals.get("prop-1")
    assert rec["status"] == "IN_WINDOW"
    assert rec["new_version_id"] == NEW
    assert rec["window_opened_at"] == NOW.isoformat()


# ─── crash between (a) and (b): approval written, fork NOT done ──────────

def test_reconcile_rolls_back_after_ab_crash(tmp_path):
    env = _make(tmp_path)
    _, proposals, registry = env
    # simulate a crash after (a): the proposal is APPROVED but no fork happened
    proposals.set_status_with_decision(
        "prop-1", status="APPROVED", decided_at=NOW.isoformat(),
        decided_by="alice", decision_note="ok")
    # no version row for the proposal, pointer still @v1
    assert registry.version_by_proposal("prop-1") is None
    assert _pointer(registry) == BASE

    actions = _gate(env).reconcile()
    assert {"proposal_id": "prop-1", "action": "rolled_back_to_proposed"} in actions
    rec = proposals.get("prop-1")
    assert rec["status"] == "PROPOSED"          # rolled back
    assert rec["decided_at"] is None
    assert _pointer(registry) == BASE           # pointer never moved
    with registry.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM skill_versions WHERE version_id=?",
                            (NEW,)).fetchone()["c"] == 0


# ─── nothing to reconcile: a clean IN_WINDOW proposal is untouched ──────

def test_reconcile_noop_when_consistent(tmp_path):
    env = _make(tmp_path)
    g = _gate(env)
    g.approve(proposal_id="prop-1", decided_by="a", decision_note="ok",
              new_version_id=NEW, new_content=NEW_CONTENT)
    # already IN_WINDOW -> reconcile finds nothing APPROVED to fix
    assert g.reconcile() == []
    assert g.proposals.get("prop-1")["status"] == "IN_WINDOW"


# ─── no half-applied fork ever persists after reconciliation ────────────

def test_no_half_applied_fork_after_reconcile(tmp_path):
    env = _make(tmp_path)
    _, proposals, registry = env
    # AB crash then reconcile -> either fully forked+windowed or fully rolled back
    proposals.set_status_with_decision(
        "prop-1", status="APPROVED", decided_at=NOW.isoformat(),
        decided_by="a", decision_note="ok")
    _gate(env).reconcile()
    rec = proposals.get("prop-1")
    forked = registry.version_by_proposal("prop-1")
    # invariant: IN_WINDOW <=> a fork exists; PROPOSED <=> no fork
    if rec["status"] == "IN_WINDOW":
        assert forked is not None
    else:
        assert rec["status"] == "PROPOSED" and forked is None
