-- Skill-version registry DDL (DT-10.1, Steward Wave 1).
-- Authored from reconcile G2 (STEWARD_PAPER_TRADER_RECONCILE_001.md §, "G2 —
-- Skill-version record") and spec §6.
--
-- OWN SQLite file, its own connection path (DT-10.1 ruling: NOT co-located with
-- Store A). The invocation skill_version_id pin in Store A is a LOGICAL,
-- app-layer-verified reference to skill_versions.version_id here (cross-file).
--
-- Two tables:
--   skill_versions  — one row per version of one agent's skill. INSERT-only /
--                     append-only; content lives IN the row; no-mutation triggers.
--   skill_currency  — "which version is live". THE ONE MUTABLE CELL in the
--                     subsystem (§ "Immutability + currency"): it accepts UPDATE
--                     by design, so it carries NO no-mutation trigger.

CREATE TABLE IF NOT EXISTS skill_versions (
    -- Identity: legible handle + tamper-evidence hash.
    version_id             TEXT PRIMARY KEY,   -- '{application}/{agent}/{skill}@v{N}'
    application_id         TEXT NOT NULL,      -- DC-1 prefix, decomposed for scoping/query
    agent_name             TEXT NOT NULL,
    skill_name             TEXT NOT NULL,
    version_ordinal        INTEGER NOT NULL,   -- the N in @vN; legible orderable handle
    content_hash           TEXT NOT NULL,      -- tamper-evidence; replay verifies before trusting

    -- Content lives IN the row (serialized whole), embedding NO version number
    -- and NO provenance (content purity — trivial forks must not pollute hashes).
    content                TEXT NOT NULL,

    -- Lineage (anti-floating rule applied to versions).
    parent_version_id      TEXT,               -- null ONLY for @v1 (logical ref to another version_id)
    created_by_proposal_id TEXT,               -- null ONLY for @v1 (origin: initial-authoring)

    -- DC-2 provenance-for-harvest.
    origin                 TEXT NOT NULL CHECK (origin IN
                               ('initial-authoring','slow-loop-fork','human-seeded')),
    grounding_refs         TEXT,               -- evidence chain denormalized from the proposal (JSON)
    validation_status      TEXT NOT NULL CHECK (validation_status IN
                               ('UNVALIDATED','VALIDATED','FAILED')),
    validation_updated_at  TEXT,               -- timestamp of the last validation-status change
    validation_evidence_refs TEXT,             -- evidence refs backing the validation verdict (JSON)

    created_at             TEXT NOT NULL,      -- ISO-8601 UTC from Clock seam

    -- One version per (application, agent, skill, ordinal).
    UNIQUE (application_id, agent_name, skill_name, version_ordinal)
);

CREATE INDEX IF NOT EXISTS idx_skill_versions_identity
    ON skill_versions(application_id, agent_name, skill_name);

-- ─── No-mutation triggers: version rows are INSERT-only ──────────────────
CREATE TRIGGER IF NOT EXISTS skill_versions_no_update
BEFORE UPDATE ON skill_versions
BEGIN
    SELECT RAISE(ABORT, 'skill_versions is append-only: UPDATE rejected');
END;

CREATE TRIGGER IF NOT EXISTS skill_versions_no_delete
BEFORE DELETE ON skill_versions
BEGIN
    SELECT RAISE(ABORT, 'skill_versions is append-only: DELETE rejected');
END;

-- ─── Currency pointer: THE ONE MUTABLE CELL (no no-mutation trigger) ─────
-- (application/agent/skill) -> current_version_id. A gated fork flips this.
CREATE TABLE IF NOT EXISTS skill_currency (
    application_id     TEXT NOT NULL,
    agent_name         TEXT NOT NULL,
    skill_name         TEXT NOT NULL,
    current_version_id TEXT NOT NULL,   -- logical ref -> skill_versions.version_id (same file)
    updated_at         TEXT NOT NULL,   -- ISO-8601 UTC; the pointer is mutable, so this moves
    PRIMARY KEY (application_id, agent_name, skill_name)
);
