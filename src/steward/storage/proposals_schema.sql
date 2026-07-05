-- Proposal store DDL (DT-11.3 / spec §8, Steward Wave 4).
-- A framework-defined governance record (reconcile: "Store A, Store B,
-- skill-version, PROPOSAL — framework-defined shape + application-scoped
-- contents"). Own file, own connection path, never co-mingled.
--
-- The proposal is the first place state MOVES (spec §8): every transition is a
-- human gate or an evidence verdict. Wave 4 creates PROPOSED rows only. The
-- APPROVE executor (fork + pointer flip + window) is Wave 5 — NOT built here.
--
-- Immutability posture: version rows analogue. The record's lifecycle columns
-- (status, decided_*, window_*, new_version_id, evaluation) DO move as the
-- proposal is gated — so this table is NOT append-only-immutable like Store A/B.
-- It is the proposal's own mutable lifecycle record. (Wave 4 writes PROPOSED and
-- never advances it; the transition executor is Wave 5.)

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id       TEXT PRIMARY KEY,   -- ULID target; TEXT
    created_at        TEXT NOT NULL,
    author            TEXT NOT NULL,      -- officer (v1)
    application_id    TEXT NOT NULL,      -- DC-1 scoping

    evidence_refs     TEXT NOT NULL,      -- JSON list of Store B entry_ids (NON-EMPTY)
    target_skill      TEXT NOT NULL,      -- '{application}/{agent}/{skill}' (G2 ID format)
    base_version_id   TEXT NOT NULL,      -- the EXACT version being changed (e.g. @v1)
    proposed_change   TEXT NOT NULL,      -- structured additive change (JSON, not prose)
    rationale         TEXT NOT NULL,      -- why the evidence justifies the change
    complexity_tag    TEXT NOT NULL CHECK (complexity_tag IN ('low','high')),

    status            TEXT NOT NULL CHECK (status IN
                          ('PROPOSED','APPROVED','REJECTED','IN_WINDOW',
                           'SUCCEEDED','FAILED','INCONCLUSIVE','SUPERSEDED')),

    -- Gate outcome (null until the human rules — Wave 5).
    decided_at        TEXT,
    decided_by        TEXT,
    decision_note     TEXT,

    -- Stabilization window (null until approved — Wave 5).
    window_opened_at  TEXT,
    window_closes_at  TEXT,
    new_version_id    TEXT,

    -- Three-signal verdict at window close (null until then; v1 STUBBED).
    evaluation        TEXT,

    -- Cooling-off ritual (DT-12.1 / §8.4): first-viewed session + timestamp,
    -- stamped by `gate show`. A high-complexity approve is blocked unless the
    -- approving session differs from the first-viewed session.
    first_viewed_at      TEXT,
    first_viewed_session TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_target_status
    ON proposals(target_skill, status);
