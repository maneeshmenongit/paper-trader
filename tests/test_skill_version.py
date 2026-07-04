"""Skill-version registry DoD tests (DT-10.1, Steward Wave 1).

Proves G2: identity + content_hash, content-in-row, lineage nullability, DC-2
CHECK constraints, version rows append-only (triggers), the currency pointer as
the one mutable cell (upsert succeeds), and its own distinct file.
"""

from __future__ import annotations

import sqlite3

import pytest

from steward.storage.skill_version import SkillVersionRegistry

SKILL_VERSION_COLUMNS = [
    "version_id",
    "application_id",
    "agent_name",
    "skill_name",
    "version_ordinal",
    "content_hash",
    "content",
    "parent_version_id",
    "created_by_proposal_id",
    "origin",
    "grounding_refs",
    "validation_status",
    "validation_updated_at",
    "validation_evidence_refs",
    "created_at",
]

SKILL_CURRENCY_COLUMNS = [
    "application_id",
    "agent_name",
    "skill_name",
    "current_version_id",
    "updated_at",
]


def _v1_kwargs(**overrides) -> dict:
    base = dict(
        version_id="paper-trader/predict/predict@v1",
        application_id="paper-trader",
        agent_name="predict",
        skill_name="predict",
        version_ordinal=1,
        content_hash="deadbeef",
        content="mandate: produce views ...",
        parent_version_id=None,
        created_by_proposal_id=None,
        origin="initial-authoring",
        grounding_refs=None,
        validation_status="UNVALIDATED",
        validation_updated_at="2026-07-04T00:00:00Z",
        validation_evidence_refs='["T02-T04"]',
        created_at="2026-07-04T00:00:00Z",
    )
    base.update(overrides)
    return base


@pytest.fixture
def reg(tmp_path):
    return SkillVersionRegistry(tmp_path / "skills.sqlite")


def _columns(reg: SkillVersionRegistry, table: str) -> list[str]:
    with reg.connection() as conn:
        return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


# ─── schema shape ────────────────────────────────────────────────────────

def test_skill_versions_exact_columns(reg):
    assert _columns(reg, "skill_versions") == SKILL_VERSION_COLUMNS


def test_skill_currency_exact_columns(reg):
    assert _columns(reg, "skill_currency") == SKILL_CURRENCY_COLUMNS


def test_two_tables_only(reg):
    with reg.connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    assert tables == {"skill_versions", "skill_currency"}


# ─── content-in-row + round-trip ─────────────────────────────────────────

def test_insert_and_roundtrip(reg):
    reg.insert_skill_version(**_v1_kwargs())
    with reg.connection() as conn:
        row = conn.execute(
            "SELECT * FROM skill_versions WHERE version_id='paper-trader/predict/predict@v1'"
        ).fetchone()
    assert row["content"] == "mandate: produce views ..."
    assert row["content_hash"] == "deadbeef"
    assert row["parent_version_id"] is None       # null only for @v1
    assert row["created_by_proposal_id"] is None
    assert row["origin"] == "initial-authoring"


def test_v2_lineage(reg):
    reg.insert_skill_version(**_v1_kwargs())
    reg.insert_skill_version(
        **_v1_kwargs(
            version_id="paper-trader/predict/predict@v2",
            version_ordinal=2,
            content_hash="cafef00d",
            parent_version_id="paper-trader/predict/predict@v1",
            created_by_proposal_id="prop-1",
            origin="slow-loop-fork",
        )
    )
    with reg.connection() as conn:
        row = conn.execute(
            "SELECT * FROM skill_versions WHERE version_ordinal=2"
        ).fetchone()
    assert row["parent_version_id"] == "paper-trader/predict/predict@v1"
    assert row["created_by_proposal_id"] == "prop-1"


# ─── DC-2 CHECK constraints ──────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["invented", "fork", ""])
def test_origin_check(reg, bad):
    with pytest.raises(sqlite3.IntegrityError):
        reg.insert_skill_version(**_v1_kwargs(origin=bad))


@pytest.mark.parametrize("good", ["initial-authoring", "slow-loop-fork", "human-seeded"])
def test_origin_accepts_valid(reg, good):
    reg.insert_skill_version(
        **_v1_kwargs(
            version_id=f"paper-trader/a/{good}@v1",
            agent_name=good,
            skill_name=good,
            origin=good,
        )
    )


@pytest.mark.parametrize("bad", ["unvalidated", "PENDING", "OK"])
def test_validation_status_check(reg, bad):
    with pytest.raises(sqlite3.IntegrityError):
        reg.insert_skill_version(**_v1_kwargs(validation_status=bad))


@pytest.mark.parametrize("good", ["UNVALIDATED", "VALIDATED", "FAILED"])
def test_validation_status_accepts_valid(reg, good):
    reg.insert_skill_version(
        **_v1_kwargs(
            version_id=f"paper-trader/a/s@v{good}",
            skill_name=good,
            validation_status=good,
        )
    )


def test_unique_ordinal_per_identity(reg):
    reg.insert_skill_version(**_v1_kwargs())
    with pytest.raises(sqlite3.IntegrityError):
        # Same application/agent/skill/ordinal, different version_id -> rejected.
        reg.insert_skill_version(**_v1_kwargs(version_id="paper-trader/predict/predict@v1-dup"))


# ─── version rows are append-only ────────────────────────────────────────

def test_version_update_rejected(reg):
    reg.insert_skill_version(**_v1_kwargs())
    with reg.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE skill_versions SET content='tamper'")


def test_version_delete_rejected(reg):
    reg.insert_skill_version(**_v1_kwargs())
    with reg.connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM skill_versions")


# ─── currency pointer: the one mutable cell ──────────────────────────────

def test_currency_pointer_is_mutable(reg):
    reg.insert_skill_version(**_v1_kwargs())
    reg.set_current_version(
        application_id="paper-trader", agent_name="predict", skill_name="predict",
        current_version_id="paper-trader/predict/predict@v1", updated_at="2026-07-04T00:00:00Z",
    )
    assert reg.get_current_version_id(
        application_id="paper-trader", agent_name="predict", skill_name="predict"
    ) == "paper-trader/predict/predict@v1"

    # Flip to @v2 — the pointer legitimately moves (upsert, not a second row).
    reg.insert_skill_version(
        **_v1_kwargs(version_id="paper-trader/predict/predict@v2", version_ordinal=2,
                     parent_version_id="paper-trader/predict/predict@v1",
                     created_by_proposal_id="prop-1", origin="slow-loop-fork")
    )
    reg.set_current_version(
        application_id="paper-trader", agent_name="predict", skill_name="predict",
        current_version_id="paper-trader/predict/predict@v2", updated_at="2026-07-05T00:00:00Z",
    )
    assert reg.get_current_version_id(
        application_id="paper-trader", agent_name="predict", skill_name="predict"
    ) == "paper-trader/predict/predict@v2"

    with reg.connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM skill_currency").fetchone()["c"]
    assert n == 1  # one row per identity — upsert, not append


def test_get_current_version_absent_returns_none(reg):
    assert reg.get_current_version_id(
        application_id="x", agent_name="y", skill_name="z"
    ) is None


# ─── own distinct file ───────────────────────────────────────────────────

def test_registry_is_own_file(tmp_path):
    store_a = tmp_path / "store_a.sqlite"
    store_b = tmp_path / "store_b.sqlite"
    app_db = tmp_path / "paper_trader.sqlite"
    checkpointer = tmp_path / "checkpointer.sqlite"
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")

    assert reg.path.exists()
    assert reg.path not in {store_a, store_b, app_db, checkpointer}


# ─── no delete on the module surface ─────────────────────────────────────

def test_no_delete_method_on_surface():
    import inspect

    public = [
        name
        for name, _ in inspect.getmembers(SkillVersionRegistry, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    assert set(public) == {
        "insert_skill_version",
        "set_current_version",
        "get_current_version_id",
        "connection",
    }
    for name in public:
        assert "delete" not in name.lower()
