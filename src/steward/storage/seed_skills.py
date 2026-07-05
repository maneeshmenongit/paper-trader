"""Seed the five @v1 skills into a skill-version registry (DT-15.3, Wave 2).

FRAMEWORK-adjacent seeding. Authors the five paper_trader @v1 skill rows from the
non-authoritative YAML artifacts under docs/steward/skills/ (the transcription
source) into an injected-path registry. The registry ROW is the source of truth
(G2 content-in-row); the YAML files are convenience artifacts only.

Idempotent: re-running against a registry that already holds a given @v1 row
skips it (the version row is append-only and its version_id is a PRIMARY KEY).
No durable registry path is chosen here — the caller injects the registry (the
governance-store paths are wired in Wave 3). This is why seeding is a function,
not a script with a baked-in path.

All five: application=paper_trader, ordinal=1, origin=initial-authoring,
parent_version_id=null, created_by_proposal_id=null, validation_status=UNVALIDATED.
skill_name == agent name. Predict additionally carries its thesis evidence in the
validation_evidence_refs slot (the thesis flag is a companion biography field, not
skill content — G2 content purity keeps it out of the YAML).
"""

from __future__ import annotations

from pathlib import Path

from steward.storage.skill_version import SkillVersionRegistry

APPLICATION_ID = "paper-trader"
SKILLS_DIR = (
    Path(__file__).resolve().parents[3] / "docs" / "steward" / "skills"
)

# agent_name -> yaml filename. skill_name == agent_name for all five (ruling).
SKILL_AGENTS = ["predict", "filter", "research", "execute", "postmortem"]

# Predict's companion thesis-status flag (Appendix A.1) — biography, not content.
PREDICT_VALIDATION_EVIDENCE = (
    "UNVALIDATED, 2026-07-04, evidence: T02-T04 FAIL of predecessor "
    "(+0.1pp vs +3pp; momentum 47 / LLM 36)"
)


def _yaml_path(agent: str) -> Path:
    return SKILLS_DIR / f"{agent}@v1.yaml"


def version_id_for(agent: str) -> str:
    """The @v1 identity for one agent: {application}/{agent}/{skill}@v1."""
    return f"{APPLICATION_ID}/{agent}/{agent}@v1"


def seed_v1_skills(
    registry: SkillVersionRegistry, *, created_at: str
) -> list[str]:
    """Insert the five @v1 rows into ``registry``. Returns the version_ids seeded.

    Idempotent: rows whose version_id already exists are skipped. ``created_at``
    (and the validation timestamp) are injected so the function stays free of the
    forbidden clock calls.
    """
    seeded: list[str] = []
    existing = _existing_version_ids(registry)

    for agent in SKILL_AGENTS:
        version_id = version_id_for(agent)
        if version_id in existing:
            continue

        content = _yaml_path(agent).read_text(encoding="utf-8")
        validation_evidence = (
            PREDICT_VALIDATION_EVIDENCE if agent == "predict" else None
        )

        registry.insert_skill_version(
            version_id=version_id,
            application_id=APPLICATION_ID,
            agent_name=agent,
            skill_name=agent,
            version_ordinal=1,
            content=content,
            parent_version_id=None,
            created_by_proposal_id=None,
            origin="initial-authoring",
            grounding_refs=None,
            validation_status="UNVALIDATED",
            validation_updated_at=created_at,
            validation_evidence_refs=validation_evidence,
            created_at=created_at,
        )
        seeded.append(version_id)

    return seeded


def _existing_version_ids(registry: SkillVersionRegistry) -> set[str]:
    with registry.connection() as conn:
        rows = conn.execute("SELECT version_id FROM skill_versions").fetchall()
    return {r["version_id"] for r in rows}
