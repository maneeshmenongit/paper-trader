"""Skill loader DoD tests (DT-10.2, Steward Wave 2).

Proves: a good row loads and parses; a tampered row raises SkillIntegrityError
(strict, nothing materialized); the returned structure is read-only (cannot be
mutated back into the row); an absent row raises.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from steward.storage.content_hash import compute_content_hash
from steward.storage.skill_loader import (
    SkillIntegrityError,
    SkillNotFoundError,
    load_skill,
)
from steward.storage.skill_version import SkillVersionRegistry

SKILL_YAML = """\
mandate: produce per-symbol views
rules:
  - id: R1
    condition: method lacks minimum history
    action: ineligible
constraints:
  - id: C1
    type: confidence_floor
    params:
      threshold: 0.60
terminal_outputs:
  - View
  - NoView
escalation: LLM selects among eligible methods only
"""


def _insert_v1(reg: SkillVersionRegistry, content: str = SKILL_YAML) -> str:
    version_id = "paper-trader/predict/predict@v1"
    reg.insert_skill_version(
        version_id=version_id,
        application_id="paper-trader",
        agent_name="predict",
        skill_name="predict",
        version_ordinal=1,
        content=content,
        parent_version_id=None,
        created_by_proposal_id=None,
        origin="initial-authoring",
        grounding_refs=None,
        validation_status="UNVALIDATED",
        validation_updated_at="2026-07-04T00:00:00Z",
        validation_evidence_refs=None,
        created_at="2026-07-04T00:00:00Z",
    )
    return version_id


@pytest.fixture
def reg(tmp_path):
    return SkillVersionRegistry(tmp_path / "skills.sqlite")


# ─── good row loads ──────────────────────────────────────────────────────

def test_good_row_loads_and_parses(reg):
    vid = _insert_v1(reg)
    with reg.connection() as conn:
        skill = load_skill(conn, vid)
    assert skill["mandate"] == "produce per-symbol views"
    assert skill["rules"][0]["id"] == "R1"
    assert skill["constraints"][0]["params"]["threshold"] == 0.60
    assert skill["terminal_outputs"] == ("View", "NoView")


# ─── read-only structure ─────────────────────────────────────────────────

def test_returned_structure_is_read_only(reg):
    vid = _insert_v1(reg)
    with reg.connection() as conn:
        skill = load_skill(conn, vid)

    assert isinstance(skill, MappingProxyType)
    with pytest.raises(TypeError):
        skill["mandate"] = "hacked"          # top-level frozen
    with pytest.raises(TypeError):
        skill["constraints"][0]["params"]["threshold"] = 0.10  # nested frozen
    # lists became tuples -> no append
    with pytest.raises(AttributeError):
        skill["terminal_outputs"].append("Extra")


def test_no_path_back_into_row(reg):
    """Mutating the loaded structure must not change the stored content."""
    vid = _insert_v1(reg)
    with reg.connection() as conn:
        skill = load_skill(conn, vid)
        try:
            skill["mandate"] = "hacked"  # raises; even if it didn't, no writeback
        except TypeError:
            pass
        stored = conn.execute(
            "SELECT content FROM skill_versions WHERE version_id = ?", (vid,)
        ).fetchone()["content"]
    assert stored == SKILL_YAML  # unchanged


# ─── tampered row -> strict raise ────────────────────────────────────────

def test_tampered_content_raises(reg):
    # Insert a row whose stored hash does NOT match its stored content, by
    # bypassing the writer with a raw INSERT (simulates post-insert corruption /
    # a hand-edited row). The no-mutation triggers block UPDATE/DELETE, not a
    # crafted INSERT, so this is the way to stage a mismatch.
    vid = "paper-trader/filter/filter@v1"
    wrong_hash = compute_content_hash("some other content")
    with reg.connection() as conn:
        conn.execute(
            """
            INSERT INTO skill_versions (
                version_id, application_id, agent_name, skill_name,
                version_ordinal, content_hash, content,
                parent_version_id, created_by_proposal_id,
                origin, grounding_refs,
                validation_status, validation_updated_at,
                validation_evidence_refs, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vid, "paper-trader", "filter", "filter", 1,
                wrong_hash, "mandate: real content",
                None, None, "initial-authoring", None,
                "UNVALIDATED", "2026-07-04T00:00:00Z", None, "2026-07-04T00:00:00Z",
            ),
        )

    with reg.connection() as conn:
        with pytest.raises(SkillIntegrityError):
            load_skill(conn, vid)


def test_hash_verified_with_canonical_function(reg):
    # A row the writer produced (hash computed canonically) must verify clean.
    vid = _insert_v1(reg)
    with reg.connection() as conn:
        stored = conn.execute(
            "SELECT content, content_hash FROM skill_versions WHERE version_id = ?",
            (vid,),
        ).fetchone()
    assert stored["content_hash"] == compute_content_hash(stored["content"])


# ─── absent row ──────────────────────────────────────────────────────────

def test_absent_row_raises(reg):
    with reg.connection() as conn:
        with pytest.raises(SkillNotFoundError):
            load_skill(conn, "paper-trader/nope/nope@v1")
