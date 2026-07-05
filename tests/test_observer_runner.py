"""Observer predicate-runner tests (Wave 4 Task 2, DT-11.1/11.2). Framework."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from steward.officer.observer import OBSERVER_IDENTITY, Observer, ObserverLedgerWriter
from steward.officer.predicates import (
    Divergence,
    InvocationView,
    PredicateRegistry,
    UnregisteredPredicateError,
)
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)


class _Clock:
    def now(self):
        return NOW


def _seed_header(store_a: StoreA, cycle_id: str):
    store_a.insert_cycle_header(
        cycle_id=cycle_id, application_id="paper-trader",
        started_at=NOW.isoformat(), ended_at=NOW.isoformat(), trigger_kind="manual",
        orchestrator_input="{}", orchestrator_decision="{}", decision_mode="rule",
        orchestrator_rationale=None, status="completed",
    )


def _seed_invocation(store_a, cycle_id, *, agent, version_id, output, seq=0):
    store_a.insert_agent_invocation(
        invocation_id=f"{cycle_id}:{seq:03d}", cycle_id=cycle_id,
        application_id="paper-trader", agent_name=agent, skill_version_id=version_id,
        agent_input="{}", agent_output=json.dumps(output),
        started_at=NOW.isoformat(), ended_at=NOW.isoformat(), status="completed",
    )


def _seed_skill(reg, version_id, *, agent, constraints, ordinal=1):
    import yaml
    content = yaml.safe_dump({
        "mandate": "test", "rules": [], "constraints": constraints,
        "terminal_outputs": [], "escalation": "none",
    }, allow_unicode=True)
    reg.insert_skill_version(
        version_id=version_id, application_id="paper-trader", agent_name=agent,
        skill_name=agent, version_ordinal=ordinal, content=content,
        parent_version_id=None, created_by_proposal_id=None, origin="initial-authoring",
        grounding_refs=None, validation_status="UNVALIDATED",
        validation_updated_at=NOW.isoformat(), validation_evidence_refs=None,
        created_at=NOW.isoformat(),
    )


@pytest.fixture
def stores(tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    return store_a, store_b, reg


def _make_observer(store_a, store_b, reg_conn, predicates):
    return Observer(
        store_a=store_a, registry_conn=reg_conn,
        ledger_writer=ObserverLedgerWriter(store_b, application_id="paper-trader"),
        predicates=predicates, clock=_Clock(),
    )


# ─── clean cycle -> zero entries ─────────────────────────────────────────

def test_clean_cycle_zero_entries(stores):
    store_a, store_b, reg = stores
    vid = "paper-trader/filter/filter@v1"
    _seed_skill(reg, vid, agent="filter", constraints=[{"id": "C1", "text": "ok"}])
    _seed_header(store_a, "cyc-1")
    _seed_invocation(store_a, "cyc-1", agent="filter", version_id=vid, output={"ok": True})

    # a predicate that never diverges on a clean output
    preds = PredicateRegistry()
    preds.register("filter", "C1", lambda c, inv: [])

    with reg.connection() as conn:
        obs = _make_observer(store_a, store_b, conn, preds)
        found = obs.observe_cycle("cyc-1")
    assert found == []
    with store_b.connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM ledger_entries").fetchone()["c"] == 0


# ─── seeded violation -> exactly one attributed entry ────────────────────

def test_one_violation_one_entry(stores):
    store_a, store_b, reg = stores
    vid = "paper-trader/execute/execute@v1"
    _seed_skill(reg, vid, agent="execute", constraints=[{"id": "C1", "text": "no breach"}])
    _seed_header(store_a, "cyc-2")
    _seed_invocation(store_a, "cyc-2", agent="execute", version_id=vid,
                     output={"breach": True})

    def breach_predicate(constraint, inv: InvocationView):
        if inv.agent_output.get("breach"):
            return [Divergence(
                observation_type="constraint-violation",
                detail={"agent_name": inv.agent_name, "skill_version_id": inv.skill_version_id,
                        "constraint_id": constraint["id"]},
                invocation_id=inv.invocation_id,
            )]
        return []

    preds = PredicateRegistry()
    preds.register("execute", "C1", breach_predicate)
    with reg.connection() as conn:
        found = _make_observer(store_a, store_b, conn, preds).observe_cycle("cyc-2")
    assert len(found) == 1
    with store_b.connection() as conn:
        rows = conn.execute("SELECT * FROM ledger_entries").fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["author"] == OBSERVER_IDENTITY
    assert r["observation_type"] == "constraint-violation"
    assert r["cycle_id"] == "cyc-2"
    assert r["invocation_id"] == "cyc-2:000"
    assert vid in r["subject"]                       # attributed to the pinned version
    assert json.loads(r["evidence"])["constraint_id"] == "C1"


# ─── unregistered predicate -> build error (never silent skip) ───────────

def test_unregistered_predicate_is_build_error(stores):
    store_a, store_b, reg = stores
    vid = "paper-trader/filter/filter@v1"
    _seed_skill(reg, vid, agent="filter", constraints=[{"id": "C9", "text": "unmapped"}])
    _seed_header(store_a, "cyc-3")
    _seed_invocation(store_a, "cyc-3", agent="filter", version_id=vid, output={})

    preds = PredicateRegistry()  # C9 not registered
    with reg.connection() as conn:
        obs = _make_observer(store_a, store_b, conn, preds)
        # the runner surfaces the build error (observe_cycle catches -> records);
        # the underlying _observe raises UnregisteredPredicateError.
        with pytest.raises(UnregisteredPredicateError):
            obs._observe("cyc-3")


# ─── judged against the PINNED version, not the current pointer ──────────

def test_judged_against_pinned_version(stores):
    store_a, store_b, reg = stores
    v1 = "paper-trader/predict/predict@v1"
    v2 = "paper-trader/predict/predict@v2"
    # @v1 declares C1; @v2 (a later version) declares a DIFFERENT constraint set.
    _seed_skill(reg, v1, agent="predict", constraints=[{"id": "C1", "text": "v1 rule"}], ordinal=1)
    _seed_skill(reg, v2, agent="predict", constraints=[{"id": "CX", "text": "v2 rule"}], ordinal=2)
    _seed_header(store_a, "cyc-4")
    # the invocation ran under @v1 (its pin) even though @v2 now exists
    _seed_invocation(store_a, "cyc-4", agent="predict", version_id=v1, output={})

    seen_constraints = []

    def rec(constraint, inv):
        seen_constraints.append((inv.skill_version_id, constraint["id"]))
        return []

    preds = PredicateRegistry()
    preds.register("predict", "C1", rec)   # only @v1's C1 is registered
    with reg.connection() as conn:
        _make_observer(store_a, store_b, conn, preds).observe_cycle("cyc-4")
    # exactly @v1's C1 was checked — @v2's CX was never consulted
    assert seen_constraints == [(v1, "C1")]


# ─── non-blocking: an observer failure is recorded, not raised ───────────

def test_observer_failure_non_blocking(stores):
    store_a, store_b, reg = stores
    vid = "paper-trader/filter/filter@v1"
    _seed_skill(reg, vid, agent="filter", constraints=[{"id": "C9", "text": "x"}])
    _seed_header(store_a, "cyc-5")
    _seed_invocation(store_a, "cyc-5", agent="filter", version_id=vid, output={})
    preds = PredicateRegistry()  # C9 unregistered -> _observe raises
    with reg.connection() as conn:
        obs = _make_observer(store_a, store_b, conn, preds)
        found = obs.observe_cycle("cyc-5")  # must NOT raise
    assert found == []
    assert obs.failed == ["observe:cyc-5"]


# ─── write-auth: ledger writer stamps observer identity, INSERT-only ─────

def test_ledger_writer_is_insert_only_observer_identity(stores):
    _, store_b, _ = stores
    writer = ObserverLedgerWriter(store_b, application_id="paper-trader")
    public = [m for m in dir(writer) if not m.startswith("_")]
    assert "insert" in public
    assert not any("update" in m or "delete" in m for m in public)
    writer.insert(
        entry_id="e1", cycle_id="c1", invocation_id=None, observed_at=NOW.isoformat(),
        subject="filter/v1", observation_type="constraint-violation", evidence={"x": 1},
    )
    with store_b.connection() as conn:
        assert conn.execute("SELECT author FROM ledger_entries").fetchone()["author"] \
            == OBSERVER_IDENTITY
