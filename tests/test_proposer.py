"""Proposer tests (Wave 4 Task 5, DT-11.3/DT-12.4). Fakes for LLM; no fork."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.proposer import OFFICER_AUTHOR, Proposer, ProposerDeclinedError
from steward.storage.proposals import EmptyEvidenceError, ProposalStore
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
TARGET = "paper-trader/predict/predict"
BASE = "paper-trader/predict/predict@v1"


class _Clock:
    def now(self):
        return NOW


def _seed_entry(store_b, entry_id, *, subject=BASE, otype="outcome-mismatch"):
    # subject carries the pinned version id (e.g. paper-trader/predict/predict@v1),
    # which contains the target skill string the proposer's LIKE query matches.
    store_b.insert_ledger_entry(
        entry_id=entry_id, cycle_id="cyc-1", invocation_id="cyc-1:004",
        observed_at=NOW.isoformat(), author="correction-officer",
        subject=f"predict/{subject}", observation_type=otype,
        evidence=json.dumps({"miss": True}),
    )


@pytest.fixture
def stores(tmp_path):
    return StoreB(tmp_path / "store_b.sqlite"), ProposalStore(tmp_path / "proposals.sqlite")


def _proposer(store_b, proposals, narrator=None):
    return Proposer(store_b=store_b, proposal_store=proposals,
                    application_id="paper-trader", clock=_Clock(), narrator=narrator)


# ─── well-formed PROPOSED record ─────────────────────────────────────────

def test_well_formed_proposed(stores):
    store_b, proposals = stores
    _seed_entry(store_b, "cyc-1:obs:000")
    _seed_entry(store_b, "cyc-1:obs:001")
    pid = _proposer(store_b, proposals).propose(
        proposal_id="prop-1", target_skill=TARGET, base_version_id=BASE,
        proposed_change={"constraint": "raise T to 0.65"}, complexity_tag="high",
    )
    rec = proposals.get(pid)
    assert rec["status"] == "PROPOSED"
    assert rec["author"] == OFFICER_AUTHOR
    assert rec["target_skill"] == TARGET
    assert rec["base_version_id"] == BASE
    assert rec["complexity_tag"] == "high"
    assert json.loads(rec["evidence_refs"]) == ["cyc-1:obs:000", "cyc-1:obs:001"]
    assert rec["rationale"]                      # non-empty
    # not advanced past PROPOSED — no fork/gate happened
    assert rec["decided_at"] is None and rec["new_version_id"] is None


# ─── cite-never-assert: empty evidence rejected ──────────────────────────

def test_empty_evidence_declined(stores):
    store_b, proposals = stores
    # no Store B entries for the target -> propose declines
    with pytest.raises(ProposerDeclinedError):
        _proposer(store_b, proposals).propose(
            proposal_id="prop-x", target_skill=TARGET, base_version_id=BASE,
            proposed_change={"x": 1},
        )


def test_store_rejects_empty_evidence_directly(stores):
    _, proposals = stores
    with pytest.raises(EmptyEvidenceError):
        proposals.insert_proposed(
            proposal_id="p", created_at=NOW.isoformat(), author=OFFICER_AUTHOR,
            application_id="paper-trader", evidence_refs=[], target_skill=TARGET,
            base_version_id=BASE, proposed_change={}, rationale="r", complexity_tag="low",
        )


# ─── one-proposal-at-a-time guard (DT-12.4) ──────────────────────────────

def test_guard_declines_second_open_proposal(stores):
    store_b, proposals = stores
    _seed_entry(store_b, "cyc-1:obs:000")
    p = _proposer(store_b, proposals)
    p.propose(proposal_id="prop-1", target_skill=TARGET, base_version_id=BASE,
              proposed_change={"x": 1})
    # a second proposal against the same skill (still PROPOSED) is declined
    with pytest.raises(ProposerDeclinedError):
        p.propose(proposal_id="prop-2", target_skill=TARGET, base_version_id=BASE,
                  proposed_change={"y": 2})


def test_guard_allows_different_skill(stores):
    store_b, proposals = stores
    _seed_entry(store_b, "e-predict")
    store_b.insert_ledger_entry(
        entry_id="e-execute", cycle_id="c", invocation_id=None, observed_at=NOW.isoformat(),
        author="correction-officer", subject="execute/paper-trader/execute/execute@v1",
        observation_type="constraint-violation", evidence="{}",
    )
    p = _proposer(store_b, proposals)
    p.propose(proposal_id="p-predict", target_skill=TARGET, base_version_id=BASE,
              proposed_change={"x": 1})
    # different skill -> allowed
    p.propose(proposal_id="p-execute", target_skill="paper-trader/execute/execute",
              base_version_id="paper-trader/execute/execute@v1", proposed_change={"z": 3})
    assert proposals.get("p-execute")["status"] == "PROPOSED"


# ─── narrator (LLM seam) drafts prose but grounding stays anchored ───────

def test_narrator_used_but_grounding_present(stores):
    store_b, proposals = stores
    _seed_entry(store_b, "cyc-1:obs:000")
    calls = []

    def narrator(system, user):
        calls.append((system, user))
        return "LLM-drafted narrative prose", 12

    _proposer(store_b, proposals, narrator=narrator).propose(
        proposal_id="prop-1", target_skill=TARGET, base_version_id=BASE,
        proposed_change={"x": 1},
    )
    assert calls  # the narrator was consulted
    rationale = proposals.get("prop-1")["rationale"]
    assert "LLM-drafted narrative prose" in rationale
    assert "ledger observation" in rationale  # deterministic evidence anchor present


# ─── reads only Store B (never the app db / fast loop) ───────────────────

def test_proposer_reads_only_store_b(stores):
    store_b, proposals = stores
    p = _proposer(store_b, proposals)
    # the proposer holds Store B + proposal store handles only — no app db / Store A
    attrs = vars(p)
    assert "store_b" in attrs and "proposals" in attrs
    assert not any("store_a" in k or "app_db" in k or "repository" in k for k in attrs)
