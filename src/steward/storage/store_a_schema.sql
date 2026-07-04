-- Store A — execution-trace DDL (DT-8.1, Steward Wave 1).
--
-- Two tables in ONE SQLite file, physically separate from the app db, the
-- checkpointer, and Store B. Store A is IMMUTABLE at the app layer: the
-- framework module exposes inserts only and no mutation path. No rejection
-- triggers are declared here (that is Store B / DT-8.2 territory).

CREATE TABLE IF NOT EXISTS cycle_headers (
    cycle_id               TEXT PRIMARY KEY,   -- ULID target (DT-4.1); TEXT accepts current uuid4
    application_id         TEXT NOT NULL,      -- DC-1 scoping id, e.g. 'paper-trader'
    started_at             TEXT NOT NULL,      -- ISO-8601 UTC from Clock seam
    ended_at               TEXT NOT NULL,      -- header is INSERTed once at cycle terminus
    trigger_kind           TEXT NOT NULL CHECK (trigger_kind IN ('schedule','event','manual')),
    orchestrator_input     TEXT NOT NULL,      -- FROZEN situation snapshot (JSON)
    orchestrator_decision  TEXT NOT NULL,      -- FROZEN cycle-shape decision (JSON)
    decision_mode          TEXT NOT NULL CHECK (decision_mode IN ('rule','llm')),  -- rule-made|LLM-made tag
    orchestrator_rationale TEXT,               -- nullable; justification if captured, never raw chain-of-thought
    status                 TEXT NOT NULL CHECK (status IN ('completed','failed','partial'))
);

CREATE TABLE IF NOT EXISTS agent_invocations (
    invocation_id    TEXT PRIMARY KEY,
    cycle_id         TEXT NOT NULL REFERENCES cycle_headers(cycle_id),  -- intra-file FK, enforced
    application_id   TEXT NOT NULL,           -- DC-1
    agent_name       TEXT NOT NULL,
    skill_version_id TEXT NOT NULL,           -- load-bearing pin; LOGICAL reference to the skill-version
                                              -- table (DT-10.1), verified at app layer, NOT a DB FK
    agent_input      TEXT NOT NULL,           -- FROZEN
    agent_output     TEXT NOT NULL,           -- FROZEN ("no output" is serialized explicitly, never left null)
    started_at       TEXT NOT NULL,
    ended_at         TEXT NOT NULL,
    status           TEXT NOT NULL
);

-- Serves the replay four-source join.
CREATE INDEX IF NOT EXISTS idx_agent_invocations_cycle_id
    ON agent_invocations(cycle_id);
