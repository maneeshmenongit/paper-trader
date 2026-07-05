"""DT-15.3 seed tests (Steward Wave 2).

Proves: the five @v1 rows insert with correct identity/origin/validation and a
computed hash; each loads clean through the loader (hash verifies); seeding is
idempotent; Predict carries its thesis evidence; the two ratified edits are
present and the PENDING markers are gone.
"""

from __future__ import annotations

import pytest

from steward.storage.content_hash import compute_content_hash
from steward.storage.seed_skills import (
    PREDICT_VALIDATION_EVIDENCE,
    SKILL_AGENTS,
    seed_v1_skills,
    version_id_for,
)
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry

CREATED_AT = "2026-07-04T00:00:00Z"


@pytest.fixture
def reg(tmp_path):
    return SkillVersionRegistry(tmp_path / "skills.sqlite")


@pytest.fixture
def seeded(reg):
    seed_v1_skills(reg, created_at=CREATED_AT)
    return reg


def test_five_rows_seeded(seeded):
    with seeded.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_versions ORDER BY agent_name"
        ).fetchall()
    assert len(rows) == 5
    assert {r["agent_name"] for r in rows} == set(SKILL_AGENTS)


@pytest.mark.parametrize("agent", SKILL_AGENTS)
def test_row_identity_and_biography(seeded, agent):
    with seeded.connection() as conn:
        row = conn.execute(
            "SELECT * FROM skill_versions WHERE agent_name = ?", (agent,)
        ).fetchone()
    assert row["version_id"] == version_id_for(agent)
    assert row["version_id"] == f"paper-trader/{agent}/{agent}@v1"
    assert row["application_id"] == "paper-trader"
    assert row["skill_name"] == agent            # skill_name == agent name
    assert row["version_ordinal"] == 1
    assert row["origin"] == "initial-authoring"
    assert row["parent_version_id"] is None
    assert row["created_by_proposal_id"] is None
    assert row["validation_status"] == "UNVALIDATED"
    assert row["validation_updated_at"] == CREATED_AT
    # hash present and canonical over the stored content
    assert row["content_hash"] == compute_content_hash(row["content"])
    assert len(row["content_hash"]) == 64


def test_predict_carries_thesis_evidence(seeded):
    with seeded.connection() as conn:
        predict = conn.execute(
            "SELECT validation_evidence_refs FROM skill_versions WHERE agent_name='predict'"
        ).fetchone()
        others = conn.execute(
            "SELECT validation_evidence_refs FROM skill_versions WHERE agent_name != 'predict'"
        ).fetchall()
    assert predict["validation_evidence_refs"] == PREDICT_VALIDATION_EVIDENCE
    assert "T02-T04 FAIL" in predict["validation_evidence_refs"]
    assert all(o["validation_evidence_refs"] is None for o in others)


@pytest.mark.parametrize("agent", SKILL_AGENTS)
def test_each_row_loads_clean_through_loader(seeded, agent):
    with seeded.connection() as conn:
        skill = load_skill(conn, version_id_for(agent))
    # five-section shape present
    for section in ("mandate", "rules", "constraints", "terminal_outputs", "escalation"):
        assert section in skill


def test_idempotent_reseed(reg):
    first = seed_v1_skills(reg, created_at=CREATED_AT)
    assert len(first) == 5
    second = seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    assert second == []  # nothing re-inserted
    with reg.connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM skill_versions").fetchone()["c"]
    assert n == 5


# ─── ratified edits present; PENDING markers gone ────────────────────────

def test_filter_r2_values_present_no_pending(seeded):
    with seeded.connection() as conn:
        content = conn.execute(
            "SELECT content FROM skill_versions WHERE agent_name='filter'"
        ).fetchone()["content"]
    assert "$10M" in content and "$50M" in content
    assert "PENDING" not in content
    assert "DT-15.1" not in content  # doc-tracking marker must not leak into content


EXECUTE_ANNOTATION = (
    "confidence ≥ 0.55 — Execute's independent risk-to-act floor. Currently "
    "shadowed by Predict's forecast-quality threshold of 0.60 (I-10): every View "
    "reaching Execute already clears 0.60, so this gate does not bind under @v1. "
    "Retained deliberately, not as redundancy — Predict's 0.60 answers 'is the "
    "forecast good enough to be a View at all,' Execute's 0.55 answers 'is it "
    "confident enough to risk capital on,' two decisions the membrane keeps "
    "separately ownable. The higher of the two floors binds; either is re-tunable "
    "via its own gated fork. Execute's gate firing is an officer-observable signal "
    "that the upstream threshold has dropped below 0.55."
)


def test_execute_confidence_annotation_present(seeded):
    # Check the PARSED rule text (folded), not the raw wrapped YAML bytes.
    with seeded.connection() as conn:
        skill = load_skill(conn, version_id_for("execute"))
        raw = conn.execute(
            "SELECT content FROM skill_versions WHERE agent_name='execute'"
        ).fetchone()["content"]
    gate = next(r["text"] for r in skill["rules"] if r["id"] == "execution_gates")
    assert gate.startswith("Execution gates: require confidence ≥ 0.55 [")
    assert EXECUTE_ANNOTATION in gate               # verbatim annotation
    assert gate.endswith("; require expected magnitude ≥ 0.5%.")
    # doc-tracking markers must not leak into content
    assert "PENDING" not in raw
    assert "DT-15.2" not in raw
