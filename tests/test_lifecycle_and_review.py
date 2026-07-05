"""Lifecycle state-machine + review-doc tests (Wave 4 Task 6, DT-12.2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.lifecycle import (
    IllegalTransitionError,
    execute_transition,
    is_legal,
    is_terminal,
    validate_transition,
)
from steward.officer.review_doc import render_review_doc
from steward.storage.proposals import ProposalStore
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


# ─── lifecycle: legal transitions ────────────────────────────────────────

@pytest.mark.parametrize("frm,to", [
    ("PROPOSED", "APPROVED"),
    ("PROPOSED", "REJECTED"),
    ("PROPOSED", "SUPERSEDED"),
    ("APPROVED", "IN_WINDOW"),
    ("IN_WINDOW", "SUCCEEDED"),
    ("IN_WINDOW", "FAILED"),
    ("IN_WINDOW", "INCONCLUSIVE"),
    ("APPROVED", "SUPERSEDED"),
])
def test_legal_transitions(frm, to):
    assert is_legal(frm, to)
    validate_transition(frm, to)  # does not raise


@pytest.mark.parametrize("frm,to", [
    ("PROPOSED", "IN_WINDOW"),     # can't skip APPROVED
    ("PROPOSED", "SUCCEEDED"),
    ("REJECTED", "APPROVED"),      # terminal
    ("SUCCEEDED", "IN_WINDOW"),    # terminal
    ("APPROVED", "PROPOSED"),      # no going back
    ("IN_WINDOW", "APPROVED"),
])
def test_illegal_transitions_rejected(frm, to):
    assert not is_legal(frm, to)
    with pytest.raises(IllegalTransitionError):
        validate_transition(frm, to)


def test_terminal_states():
    for s in ("REJECTED", "SUCCEEDED", "FAILED", "INCONCLUSIVE", "SUPERSEDED"):
        assert is_terminal(s)
    for s in ("PROPOSED", "APPROVED", "IN_WINDOW"):
        assert not is_terminal(s)


def test_unknown_state_rejected():
    with pytest.raises(IllegalTransitionError):
        validate_transition("BOGUS", "APPROVED")


# ─── APPROVE executor is a Wave 5 seam (validates, does not perform) ─────

def test_approve_executor_is_wave5_seam():
    # validation passes, but performing the fork is not implemented (Wave 5)
    with pytest.raises(NotImplementedError):
        execute_transition("PROPOSED", "APPROVED")


def test_illegal_transition_fails_before_seam():
    # an illegal transition raises the lifecycle error, not NotImplementedError
    with pytest.raises(IllegalTransitionError):
        execute_transition("PROPOSED", "SUCCEEDED")


# ─── review doc: every cited entry inlined IN FULL ───────────────────────

@pytest.fixture
def rendered(tmp_path):
    store_b = StoreB(tmp_path / "store_b.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    # two ledger entries with distinctive evidence payloads
    store_b.insert_ledger_entry(
        entry_id="e-1", cycle_id="cyc-1", invocation_id="cyc-1:004",
        observed_at=NOW.isoformat(), author="correction-officer",
        subject="predict/paper-trader/predict/predict@v1",
        observation_type="outcome-mismatch",
        evidence=json.dumps({"UNIQUE_MARKER_ONE": 111, "magnitude_error": 3.0}),
    )
    store_b.insert_ledger_entry(
        entry_id="e-2", cycle_id="cyc-2", invocation_id=None,
        observed_at=NOW.isoformat(), author="correction-officer",
        subject="predict/paper-trader/predict/predict@v1",
        observation_type="constraint-violation",
        evidence=json.dumps({"UNIQUE_MARKER_TWO": 222}),
    )
    proposals.insert_proposed(
        proposal_id="prop-1", created_at=NOW.isoformat(), author="correction-officer",
        application_id="paper-trader", evidence_refs=["e-1", "e-2"],
        target_skill="paper-trader/predict/predict",
        base_version_id="paper-trader/predict/predict@v1",
        proposed_change={"raise_threshold": 0.65}, rationale="evidence says raise T",
        complexity_tag="high",
    )
    return render_review_doc(proposals.get("prop-1"), store_b=store_b)


def test_doc_inlines_full_evidence(rendered):
    # BOTH cited entries' full evidence payloads appear inline
    assert "UNIQUE_MARKER_ONE" in rendered
    assert "111" in rendered
    assert "UNIQUE_MARKER_TWO" in rendered
    assert "222" in rendered
    # both entry ids are headed
    assert "e-1" in rendered and "e-2" in rendered
    # observation types rendered
    assert "outcome-mismatch" in rendered
    assert "constraint-violation" in rendered


def test_doc_has_proposal_metadata(rendered):
    assert "prop-1" in rendered
    assert "paper-trader/predict/predict" in rendered
    assert "raise_threshold" in rendered           # proposed change inlined
    assert "evidence says raise T" in rendered      # rationale


def test_doc_high_complexity_cooling_off(rendered):
    assert "HIGH complexity" in rendered
    assert "cooling-off" in rendered


def test_doc_flags_unresolved_refs(tmp_path):
    store_b = StoreB(tmp_path / "store_b.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    store_b.insert_ledger_entry(
        entry_id="e-real", cycle_id="c", invocation_id=None, observed_at=NOW.isoformat(),
        author="correction-officer", subject="x", observation_type="t", evidence="{}",
    )
    proposals.insert_proposed(
        proposal_id="p", created_at=NOW.isoformat(), author="correction-officer",
        application_id="paper-trader", evidence_refs=["e-real", "e-missing"],
        target_skill="paper-trader/predict/predict",
        base_version_id="paper-trader/predict/predict@v1",
        proposed_change={}, rationale="r", complexity_tag="low",
    )
    doc = render_review_doc(proposals.get("p"), store_b=store_b)
    assert "Unresolved evidence refs" in doc
    assert "e-missing" in doc
