# Steward Wave 1 — Completion Report

**Branch:** `wave1-monorepo-setup` (NOT merged — left for human review)
**Scope:** Storage + versioning substrate (reconcile §9.2, Wave 1). No dependencies.
**Status:** All Wave 1 tasks complete and individually signed off. STOP here —
Wave 2 is gated on human rulings DT-15.1 / DT-15.2, which are not in this repo.

---

## What now exists

The five governance/instance stores of the four-store map (CLAUDE.md), each a
distinct SQLite file on its own connection path, never co-mingled:

| # | Store | File (basename) | Framework module | Mutability | Opened by |
|---|-------|-----------------|------------------|------------|-----------|
| 1 | Checkpointer (crash recovery) | `checkpointer.sqlite` | — (app: LangGraph) | app-owned | application |
| 2 | App domain history | `paper_trader.sqlite` | — (app: `paper_trader.persistence`) | app-owned | application |
| 3 | Store A (execution trace) | `store_a.sqlite` | `steward.storage.store_a` | immutable / append-only | factory |
| 4 | Store B (correction ledger) | `store_b.sqlite` | `steward.storage.store_b` | append-only | factory |
| 5 | Skill-version registry | `skills.sqlite` | `steward.storage.skill_version` | versions append-only; currency pointer is the one mutable cell | factory |

Basenames are illustrative — the framework hardcodes no paths; the application
injects each one (DC-1 / spec §4.5).

### Tables

- **Store A** (`store_a_schema.sql`): `cycle_headers`, `agent_invocations`
  (intra-file FK on `cycle_id`; index on `agent_invocations(cycle_id)`).
  No-mutation triggers on both (DT-8.2 ruling).
- **Store B** (`store_b_schema.sql`): `ledger_entries` — **no
  action/recommendation/severity column** (that absence is the membrane, §5.3);
  index on `cycle_id`; no-mutation triggers. Merkle chaining deferred (DT-8.2).
- **Skill-version registry** (`skill_version_schema.sql`): `skill_versions`
  (append-only, content-in-row, G2 identity/lineage/DC-2 fields, no-mutation
  triggers) + `skill_currency` (the one mutable pointer cell — no trigger).

### Cross-file references (logical, app-layer-verified — NOT DB FKs)

The stores are separate files, so these are logical references, not enforced FKs:

- `agent_invocations.skill_version_id`  →  `skill_versions.version_id`
- `ledger_entries.cycle_id`             →  `cycle_headers.cycle_id`
- `ledger_entries.invocation_id`        →  `agent_invocations.invocation_id` (nullable)
- `skill_currency.current_version_id`   →  `skill_versions.version_id` (same file)

Only intra-file relationships are DB-enforced FKs (Store A's `cycle_id`).

## Connection map (DT-8.5)

`steward.storage.connections.StoreConnections` takes all five paths as injected
constructor arguments, resolves them, and raises `CoMingledStoreError` if any
two coincide. It constructs the three framework governance stores (A, B, skill
registry) and holds the two app-owned paths (checkpointer, app db) for the
distinctness guarantee, leaving them for the app to open. No env/config reading
here — path selection is app-layer and was deliberately not wired (would touch
running fast-loop config).

## Immutability posture

Append-only enforced at BOTH layers:
- **App layer** — writer surfaces expose inserts only (Store A: 2 inserts;
  Store B: 1 insert; registry: 1 version insert + the mutable-pointer upsert).
  No update/delete methods anywhere.
- **DB layer** — no-mutation triggers reject UPDATE/DELETE on Store A's two
  tables, Store B's ledger, and `skill_versions`. The currency pointer is the
  single deliberate exception (it must move on a gated fork).

## Aggregate test results

**110 passed, 0 failed** (full suite). ruff + mypy clean on all new modules.
DC-1 boundary test green (steward/ imports no paper_trader). Fast-loop source
(`src/paper_trader/`, `scripts/`) untouched across all four tasks — the trading
loop is unaffected.

Per task:

| Task | New tests | Files added/changed |
|------|-----------|---------------------|
| DT-8.1 (prior) | 23 (`test_store_a.py`) | store_a.py, store_a_schema.sql |
| DT-8.2 | 12 (`test_store_b.py`) + Store A trigger tests | store_b.{py,sql}, store_a_schema.sql (triggers) |
| DT-10.1 | 24 (`test_skill_version.py`) | skill_version.{py,sql} |
| DT-8.5 | 12 (`test_connections.py`) | connections.py |

Commits (branch `wave1-monorepo-setup`, oldest→newest):
`8969461` monorepo scaffolding · `0f31344` DT-8.1 · `b052752` DT-8.2 ·
`540e628` DT-10.1 · `a667524` DT-8.5.

## Deviations & ambiguities encountered

1. **Cross-file "FK" language.** Spec §5.3 labels Store B's `cycle_id`/
   `invocation_id` as FKs, but §5.4 mandates separate files and SQLite can't
   enforce cross-file FKs. Resolved to the spec's own two-store-separation rule:
   modeled as logical, app-layer-verified references (the pattern already used
   for `skill_version_id`). Not a spec gap — an internal tension the spec itself
   resolves.
2. **Store A no-mutation triggers** were added, reversing DT-8.1's "no triggers
   here" note, per the explicit DT-8.2 ruling. Two DT-8.1 tests updated.
3. **Currency-pointer surface.** The registry exposes `set_current_version`
   (upsert) + `get_current_version_id` beyond the append-only version insert,
   because the pointer is G2's one mutable cell. The ATOMIC fork transaction
   (version insert + pointer flip as one op) is DT-12.1 (Wave 5), not built here.
4. **`content_hash` is caller-supplied**, not computed in the module (hashing's
   first consumer is replay, DT-13.2). The column is stored; computation is
   downstream.
5. **DT-8.5 opens no env/config and no app-owned files.** The app has
   `PAPER_TRADER_DB_PATH` / `CHECKPOINTER_DB_PATH` in `.env` but no keys for the
   three governance stores. Wiring those is app-layer and would touch running
   config — deliberately deferred to avoid the alter-fast-loop hard-stop.

No hard-stop conditions were hit. No spec amendments were required.

## Handoff / next

Wave 2 (DT-10.2 loader, DT-15.3 skill YAMLs, DT-9.1/9.2) is **blocked on human
rulings DT-15.1 and DT-15.2**. Do not begin Wave 2 until those are ruled and
this branch is reviewed. Branch is unmerged and ready for review.
