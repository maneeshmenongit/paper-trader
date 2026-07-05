"""Gate ritual + reject tests (Wave 5 Task 4). Note mandatory; cooling-off."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.gate import Gate, GateError
from steward.officer.lifecycle import IllegalTransitionError
from steward.storage.proposals import ProposalStore
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


class _Clock:
    def now(self):
        return NOW


def _make(tmp_path, *, complexity="high"):
    store_b = StoreB(tmp_path / "store_b.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    store_b.insert_ledger_entry(
        entry_id="e-1", cycle_id="c", invocation_id=None, observed_at=NOW.isoformat(),
        author="correction-officer", subject="predict/paper-trader/predict/predict@v1",
        observation_type="outcome-mismatch", evidence=json.dumps({"x": 1}),
    )
    proposals.insert_proposed(
        proposal_id="prop-1", created_at=NOW.isoformat(), author="correction-officer",
        application_id="paper-trader", evidence_refs=["e-1"],
        target_skill="paper-trader/predict/predict",
        base_version_id="paper-trader/predict/predict@v1",
        proposed_change={"raise_threshold": 0.65}, rationale="r", complexity_tag=complexity,
    )
    return store_b, proposals, registry


def _gate(env, session):
    store_b, proposals, registry = env
    return Gate(proposal_store=proposals, store_b=store_b, registry=registry,
               clock=_Clock(), session=session)


# ─── reject requires a non-empty decision_note ───────────────────────────

def test_reject_empty_note_refused(tmp_path):
    env = _make(tmp_path)
    for note in ("", "   ", None):
        with pytest.raises(GateError):
            _gate(env, "s1").reject("prop-1", decided_by="alice", decision_note=note)  # type: ignore[arg-type]


def test_reject_records_decision(tmp_path):
    env = _make(tmp_path)
    _, proposals, _ = env
    _gate(env, "s1").reject("prop-1", decided_by="alice", decision_note="not enough evidence")
    rec = proposals.get("prop-1")
    assert rec["status"] == "REJECTED"
    assert rec["decided_by"] == "alice"
    assert rec["decision_note"] == "not enough evidence"
    assert rec["decided_at"] == NOW.isoformat()


def test_reject_terminal_proposal_illegal(tmp_path):
    env = _make(tmp_path)
    g = _gate(env, "s1")
    g.reject("prop-1", decided_by="alice", decision_note="no")
    # already REJECTED (terminal) -> a second reject is an illegal transition
    with pytest.raises(IllegalTransitionError):
        g.reject("prop-1", decided_by="alice", decision_note="again")


# ─── cooling-off ritual (used by approve; tested directly here) ──────────

def test_high_complexity_same_session_blocked(tmp_path):
    env = _make(tmp_path, complexity="high")
    g = _gate(env, "session-A")
    g.show("prop-1")                       # first viewed in session-A
    proposal = g._require("prop-1")
    with pytest.raises(GateError):
        g._ensure_cooling_off(proposal)    # same session -> blocked


def test_high_complexity_different_session_allowed(tmp_path):
    env = _make(tmp_path, complexity="high")
    _gate(env, "session-A").show("prop-1")       # first viewed in session-A
    g2 = _gate(env, "session-B")                 # a later, different session
    proposal = g2._require("prop-1")
    g2._ensure_cooling_off(proposal)             # different session -> allowed (no raise)


def test_high_complexity_never_shown_blocked(tmp_path):
    env = _make(tmp_path, complexity="high")
    g = _gate(env, "session-A")
    proposal = g._require("prop-1")              # never shown -> no first-view
    with pytest.raises(GateError):
        g._ensure_cooling_off(proposal)


def test_low_complexity_same_session_allowed(tmp_path):
    env = _make(tmp_path, complexity="low")
    g = _gate(env, "session-A")
    g.show("prop-1")
    proposal = g._require("prop-1")
    g._ensure_cooling_off(proposal)              # low complexity: no cooling-off
