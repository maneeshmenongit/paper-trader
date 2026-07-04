# Steward + paper_trader — build context

## Repo layout (DC-1 three-layer separation)
- `steward/` — FRAMEWORK. Engine code and record shapes (Store A/B DDL,
  skill-version table, correction officer, replay). Reusable verbatim across apps.
- `paper_trader/` — APPLICATION. Domain agents, skill *content*, app db, config,
  data-client seams. Imports `steward`.
- Instance data (`.sqlite` files) — framework-shaped, app-scoped. Lives in
  paper_trader's data directory. Framework opens connections by injected PATH;
  it never hardcodes where instance data lives.

## The one-way import rule (enforced by tests/test_dc1_boundary.py)
`steward/` MUST NOT import from `paper_trader/`. Only `paper_trader/` imports
`steward/`. A violation is a build error, not a style note.

## Authority documents (docs/steward/)
- STEWARD_FRAMEWORK_SPEC_001.md — the record-shape authority. Author table
  columns and record schemas from this.
- PAPER_TRADER_ARCH_002.md — the existing app (CycleState, tables, agents).
  Reconciliation target; do not break it.
- STEWARD_PAPER_TRADER_RECONCILE_001.md — the BUILD AUTHORITY. Waves 1–6,
  gates G1–G7, DC-1/DC-2, the DT punch-list, and Appendix A's five @v1 skill
  YAMLs. Wave 2 skill files are authored VERBATIM from Appendix A, never from
  memory.

## Execution discipline
- One bounded task per prompt; a human gate sits between tasks.
- Store A and Store B records are immutable / append-only. Never emit code that
  UPDATEs or DELETEs a governance row.
- The fast loop keeps trading throughout the build. Governance components attach
  alongside; they never block a trading cycle.
- No framework feature without a demonstrated paper_trader need.
- Any spec gap discovered during build is a RECORDED spec amendment, flagged
  loudly — never a silent bend.
- Gate reports are brief: what changed, test results, deviations. No architecture prose.

## Four-store map
checkpointer.sqlite (crash recovery) · paper_trader.sqlite (domain history) ·
Store A (execution trace, immutable) · Store B (ledger, append-only).
Four stores, four connection paths, never co-mingled.
