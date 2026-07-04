"""Four-store connection discipline DoD tests (DT-8.5, Steward Wave 1).

Proves: each store opens on its own injected path; five distinct physical
paths; any two sharing a path is rejected (never co-mingled); the governance
stores are usable through the factory.
"""

from __future__ import annotations

import pytest

from steward.storage.connections import CoMingledStoreError, StoreConnections
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB


def _paths(tmp_path, **overrides) -> dict:
    base = dict(
        checkpointer_path=tmp_path / "checkpointer.sqlite",
        app_db_path=tmp_path / "paper_trader.sqlite",
        store_a_path=tmp_path / "store_a.sqlite",
        store_b_path=tmp_path / "store_b.sqlite",
        skill_registry_path=tmp_path / "skills.sqlite",
    )
    base.update(overrides)
    return base


@pytest.fixture
def conns(tmp_path):
    return StoreConnections(**_paths(tmp_path))


# ─── each store on its own path ──────────────────────────────────────────

def test_governance_stores_constructed(conns):
    assert isinstance(conns.store_a, StoreA)
    assert isinstance(conns.store_b, StoreB)
    assert isinstance(conns.skill_registry, SkillVersionRegistry)


def test_five_distinct_paths(conns):
    resolved = {p.resolve() for p in conns.paths.values()}
    assert len(resolved) == 5
    assert set(conns.paths) == {
        "checkpointer",
        "app_db",
        "store_a",
        "store_b",
        "skill_registry",
    }


def test_each_store_files_are_separate(conns):
    # The three governance files physically exist and differ.
    assert conns.store_a.path != conns.store_b.path
    assert conns.store_a.path != conns.skill_registry.path
    assert conns.store_b.path != conns.skill_registry.path
    for p in (conns.store_a.path, conns.store_b.path, conns.skill_registry.path):
        assert p.exists()


# ─── never co-mingled ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "collide",
    [
        ("store_a_path", "store_b_path"),
        ("store_a_path", "skill_registry_path"),
        ("store_b_path", "skill_registry_path"),
        ("store_a_path", "checkpointer_path"),
        ("app_db_path", "store_b_path"),
        ("checkpointer_path", "app_db_path"),
    ],
)
def test_co_mingled_paths_rejected(tmp_path, collide):
    a, b = collide
    shared = tmp_path / "shared.sqlite"
    paths = _paths(tmp_path, **{a: shared, b: shared})
    with pytest.raises(CoMingledStoreError):
        StoreConnections(**paths)


def test_co_mingled_detects_after_resolution(tmp_path):
    # Same file reached two ways (./x vs sub/../x) must still be caught.
    (tmp_path / "sub").mkdir()
    direct = tmp_path / "store_a.sqlite"
    indirect = tmp_path / "sub" / ".." / "store_a.sqlite"
    paths = _paths(tmp_path, store_a_path=direct, store_b_path=indirect)
    with pytest.raises(CoMingledStoreError):
        StoreConnections(**paths)


# ─── usable through the factory ──────────────────────────────────────────

def test_stores_usable_through_factory(conns):
    conns.store_a.insert_cycle_header(
        cycle_id="cyc-1",
        application_id="paper-trader",
        started_at="2026-07-04T00:00:00Z",
        ended_at="2026-07-04T00:00:05Z",
        trigger_kind="schedule",
        orchestrator_input="{}",
        orchestrator_decision="{}",
        decision_mode="rule",
        orchestrator_rationale=None,
        status="completed",
    )
    conns.store_b.insert_ledger_entry(
        entry_id="ent-1",
        cycle_id="cyc-1",
        invocation_id=None,
        observed_at="2026-07-04T00:00:06Z",
        author="correction-officer",
        subject="Predict@v1",
        observation_type="constraint-violation",
        evidence="{}",
    )
    conns.skill_registry.set_current_version(
        application_id="paper-trader",
        agent_name="predict",
        skill_name="predict",
        current_version_id="paper-trader/predict/predict@v1",
        updated_at="2026-07-04T00:00:00Z",
    )

    with conns.store_a.connection() as c:
        assert c.execute("SELECT COUNT(*) n FROM cycle_headers").fetchone()["n"] == 1
    with conns.store_b.connection() as c:
        assert c.execute("SELECT COUNT(*) n FROM ledger_entries").fetchone()["n"] == 1
    assert conns.skill_registry.get_current_version_id(
        application_id="paper-trader", agent_name="predict", skill_name="predict"
    ) == "paper-trader/predict/predict@v1"


def test_app_paths_exposed_but_not_opened(conns):
    # Checkpointer + app db are app-owned: paths held, files not created here.
    assert conns.checkpointer_path.name == "checkpointer.sqlite"
    assert conns.app_db_path.name == "paper_trader.sqlite"
    assert not conns.checkpointer_path.exists()
    assert not conns.app_db_path.exists()
