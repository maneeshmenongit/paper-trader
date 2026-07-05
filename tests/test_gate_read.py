"""Gate CLI read-side tests (Wave 5 Task 3). list + show + first-view stamp."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.gate import Gate, GateError
from steward.storage.proposals import ProposalStore
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, t=NOW):
        self.t = t

    def now(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    store_b = StoreB(tmp_path / "store_b.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    registry = SkillVersionRegistry(tmp_path / "skills.sqlite")
    store_b.insert_ledger_entry(
        entry_id="e-1", cycle_id="cyc-1", invocation_id="cyc-1:004",
        observed_at=NOW.isoformat(), author="correction-officer",
        subject="predict/paper-trader/predict/predict@v1",
        observation_type="outcome-mismatch",
        evidence=json.dumps({"UNIQUE_EVIDENCE_MARK": 777}),
    )
    proposals.insert_proposed(
        proposal_id="prop-1", created_at=NOW.isoformat(), author="correction-officer",
        application_id="paper-trader", evidence_refs=["e-1"],
        target_skill="paper-trader/predict/predict",
        base_version_id="paper-trader/predict/predict@v1",
        proposed_change={"raise_threshold": 0.65}, rationale="raise T",
        complexity_tag="high",
    )
    return store_b, proposals, registry


def _gate(env, session="session-A", clock=None):
    store_b, proposals, registry = env
    return Gate(proposal_store=proposals, store_b=store_b, registry=registry,
               clock=clock or _Clock(), session=session)


# ─── gate list ───────────────────────────────────────────────────────────

def test_list_shows_open_proposals(env):
    rows = _gate(env).list()
    assert len(rows) == 1
    assert rows[0]["proposal_id"] == "prop-1"
    assert rows[0]["status"] == "PROPOSED"
    assert rows[0]["complexity_tag"] == "high"
    assert rows[0]["first_viewed_at"] is None  # not viewed yet


# ─── gate show renders evidence inline ───────────────────────────────────

def test_show_renders_evidence_inline(env):
    doc = _gate(env).show("prop-1")
    assert "prop-1" in doc
    assert "UNIQUE_EVIDENCE_MARK" in doc and "777" in doc   # full evidence inlined
    assert "HIGH complexity" in doc                         # cooling-off banner


def test_show_unknown_proposal_raises(env):
    with pytest.raises(GateError):
        _gate(env).show("nope")


# ─── first-view stamp: idempotent, records the FIRST session/time ────────

def test_show_stamps_first_view(env):
    _, proposals, _ = env
    _gate(env, session="session-A", clock=_Clock(NOW)).show("prop-1")
    rec = proposals.get("prop-1")
    assert rec["first_viewed_session"] == "session-A"
    assert rec["first_viewed_at"] == NOW.isoformat()


def test_first_view_is_idempotent(env):
    _, proposals, _ = env
    later = datetime(2026, 7, 8, tzinfo=UTC)
    _gate(env, session="session-A", clock=_Clock(NOW)).show("prop-1")
    # a second, later view from a different session must NOT overwrite the first
    _gate(env, session="session-B", clock=_Clock(later)).show("prop-1")
    rec = proposals.get("prop-1")
    assert rec["first_viewed_session"] == "session-A"
    assert rec["first_viewed_at"] == NOW.isoformat()


# ─── read side mutates nothing but the first-view stamp ──────────────────

def test_read_side_does_not_change_status(env):
    _, proposals, _ = env
    _gate(env).show("prop-1")
    assert proposals.get("prop-1")["status"] == "PROPOSED"  # unchanged
    assert proposals.get("prop-1")["decided_at"] is None
    assert proposals.get("prop-1")["new_version_id"] is None
