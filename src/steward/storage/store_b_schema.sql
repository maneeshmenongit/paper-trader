-- Store B — correction ledger DDL (DT-8.2, Steward Wave 1).
-- Authored from STEWARD_FRAMEWORK_SPEC_001.md §5.3.
--
-- ONE SQLite file, physically separate from Store A, the app db, and the
-- checkpointer. The ledger is APPEND-ONLY: enforced at the app layer (insert
-- only) and backed by no-mutation triggers at the db layer (spec §5.4).
--
-- ABSENT BY DESIGN (spec §5.3): no `action`, no `recommendation`, no
-- `severity-that-triggers`. That absence IS the membrane (§2.3) — the ledger
-- observes and never prescribes. Do not add such a column.
--
-- Merkle chaining is DEFERRED (DT-8.2 ruling, solo-operator threat model); the
-- no-mutation trigger is the tamper defence in v1.
--
-- cycle_id and invocation_id are LOGICAL references to Store A rows. Store A
-- lives in a different file, so these are NOT db-level FKs (spec §5.4's
-- two-store separation makes a cross-file FK impossible); they are verified at
-- the app layer, the same discipline as the skill_version_id pin.

CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id         TEXT PRIMARY KEY,   -- append-only, monotonic (ULID target; TEXT accepts uuid4)
    cycle_id         TEXT NOT NULL,      -- LOGICAL ref -> Store A cycle_headers.cycle_id (cross-file)
    invocation_id    TEXT,               -- LOGICAL ref -> Store A agent_invocations.invocation_id; nullable
    observed_at      TEXT NOT NULL,      -- ISO-8601 UTC from Clock seam
    author           TEXT NOT NULL,      -- who wrote it — correction officer (always, in v1)
    subject          TEXT NOT NULL,      -- what it's about: which agent / which skill_version_id
    observation_type TEXT NOT NULL,      -- category, e.g. constraint-violation, outcome-mismatch
    evidence         TEXT NOT NULL       -- the structured observation itself (FROZEN JSON)
);

-- Serves the replay four-source join (Store B entries for a cycle).
CREATE INDEX IF NOT EXISTS idx_ledger_entries_cycle_id
    ON ledger_entries(cycle_id);

-- ─── No-mutation triggers (spec §5.4; DT-8.2) ───────────────────────────
-- The ledger is append-only. Reject every UPDATE and DELETE at the db layer.

CREATE TRIGGER IF NOT EXISTS ledger_entries_no_update
BEFORE UPDATE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'ledger_entries is append-only: UPDATE rejected');
END;

CREATE TRIGGER IF NOT EXISTS ledger_entries_no_delete
BEFORE DELETE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'ledger_entries is append-only: DELETE rejected');
END;
