# Steward Wave 2 — Completion Report

**Branch:** `wave2-versioned-skills` (NOT merged — left for human review)
**Scope:** Versioned skills live (reconcile §9.2, Wave 2). Needs Wave 1.
**Status:** All five tasks complete and individually signed off. STOP here — the
Wave 2 boundary is reached; Wave 3 items are deferred (see end).

---

## The five @v1 skill rows

Seeded by `steward.storage.seed_skills.seed_v1_skills` from the non-authoritative
YAML artifacts under `docs/steward/skills/`. The registry ROW is the source of
truth (G2 content-in-row). Verified facts (seeded into a temp registry, all load
clean through the loader with hashes verifying):

| version_id | origin | validation | hash | thesis evidence |
|------------|--------|------------|------|-----------------|
| `paper-trader/predict/predict@v1` | initial-authoring | UNVALIDATED | present (64-hex) | **yes** — T02–T04 |
| `paper-trader/filter/filter@v1` | initial-authoring | UNVALIDATED | present (64-hex) | — |
| `paper-trader/research/research@v1` | initial-authoring | UNVALIDATED | present (64-hex) | — |
| `paper-trader/execute/execute@v1` | initial-authoring | UNVALIDATED | present (64-hex) | — |
| `paper-trader/postmortem/postmortem@v1` | initial-authoring | UNVALIDATED | present (64-hex) | — |

All: `application=paper-trader`, `skill_name == agent`, `ordinal=1`,
`parent_version_id=null`, `created_by_proposal_id=null`. Content carries no
version number and no provenance (G2 purity). Predict's thesis flag
(`UNVALIDATED, 2026-07-04, evidence: T02-T04 FAIL of predecessor (+0.1pp vs +3pp;
momentum 47 / LLM 36)`) lives in the row's `validation_evidence_refs` slot —
biography, not skill content.

**Two ratified edits only** (transcription otherwise verbatim from Appendix A):
- Filter R2: `$10M`/`$50M` kept; `[PENDING DT-15.1]` marker removed (DT-15.1).
- Execute gate: `confidence ≥ 0.55` kept; PENDING bracket replaced with the exact
  DT-15.2 annotation, byte-checked verbatim after YAML fold.

## Hash authority (Task 1 — Wave 1 deviation-4 fix)

`steward.storage.content_hash.compute_content_hash(content) -> str` = SHA-256 hex
of `content.encode("utf-8")`. The **sole** hashing authority. The skill-version
writer computes and stores the hash internally (the `content_hash` parameter is
removed), so the stored hash can never disagree with the stored content. The
loader and future replay call the same function.

## Loader behavior (Task 2 — DT-10.2)

`steward.storage.skill_loader.load_skill(registry_conn, skill_version_id)`:
- fetches the row, recomputes the hash via `compute_content_hash`, compares;
- **match** → parses YAML, returns a recursively-frozen (`MappingProxyType`/tuple)
  READ-ONLY structure — an agent cannot mutate it back into the row;
- **mismatch** → raises `SkillIntegrityError` (STRICT; nothing materialized — per
  the Wave 2 ruling, distinct from replay's flag-and-continue in Wave 6);
- **absent row** → `SkillNotFoundError`.

Declared `pyyaml>=6.0` (skill content is YAML per I-9; was transitive only).

## Mirror-contract result (Task 4 — DT-9.1, re-scoped)

DT-9.1 as written asserts skill values == the live loop's config (from
`risk_gates.toml` + Filter inline thresholds). **Neither exists** — the domain
agents and their config are unbuilt. This was surfaced as a hard-stop; the ruling
(option 1) was to build the forward half only:
- `tests/test_skill_mirror_contract.py` (10 tests) loads each skill through the
  loader and locks the ratified values as a contract the future live loop must
  match. **Passes.** No `risk_gates.toml` was fabricated.
- SUPERSEDED-banner placement + the value-equality upgrade are recorded in
  `docs/steward/skills/README.md` as **Wave 3** work (attach when the sources exist).

## Freeze checklist (Task 5 — DT-9.2)

`docs/steward/DT-4.2_freeze_checklist.md`: the config the frozen trace (DT-4.2,
Wave 3) must capture — `watchlist`, `CYCLE_TIME_HORIZON_HOURS`,
`CYCLE_TOKEN_BUDGET`, Research semaphore bounds (yfinance 2; Finnhub/CoinGecko 4),
`calibration_version`, log level — plus an explicit MUST-NOT-freeze list (API keys
= secrets; store paths = plumbing) and what other mechanisms already freeze (skill
content via the version pin). Checklist artifact only; runtime verification is
Wave 3.

## Aggregate test results

**147 passed, 0 failed** (full suite; was 110 at Wave 1 merge). ruff + mypy clean
on all new modules. DC-1 boundary green (steward/ imports no paper_trader).
**Fast-loop source (`src/paper_trader/`, `scripts/`) untouched across all five
tasks** — the trading loop is unaffected, and no agent was rewired to read the
registry (that is Wave 3).

New tests this wave: `test_content_hash.py` (5), `test_skill_loader.py` (6),
`test_seed_skills.py` (15), `test_skill_mirror_contract.py` (10); plus updated
`test_skill_version.py` for the new writer signature.

Commits (branch `wave2-versioned-skills`, oldest→newest):
`635235c` Task 1 · `279ebbf` Task 2 · `837acce` Task 3 · `876422a` Task 4 ·
`1fd9d1d` Task 5.

## Deviations & ambiguities

1. **DT-9.1 hard-stop + re-scope.** `risk_gates.toml` and Filter's inline
   thresholds do not exist (agents unbuilt). Surfaced as a hard-stop; per ruling,
   built the forward mirror-contract instead of a fabricated baseline. The
   destructive/equality half is Wave 3 (and the END CONDITION already defers
   deletion + before/after diffing there).
2. **Predict has a 6th top-level YAML key, `methods`.** Appendix A.1 lists a
   "methods (declared roster)" field beside the five sections; it is verbatim
   content that must not be omitted, so it rides alongside the five-section shape.
3. **Predict thesis flag placed in the row, not the YAML content** (G2 purity —
   provenance/biography never lives in content).
4. **`pyyaml>=6.0` newly declared** (was transitive; the loader hard-depends on it).
5. **Freeze checklist adds a MUST-NOT-freeze section** beyond the task's list —
   §5.1's "nothing it didn't" cuts both ways, and freezing API keys into an
   immutable trace would be an unredactable secrets leak.

No spec amendments were required. No governance row is ever UPDATEd or DELETEd.

## Deferred to Wave 3 (do NOT do until ruled/opened)

- Rewire agents to load skills from the registry via the loader.
- Diff trade decisions before/after; delete `risk_gates.toml` + Filter inline
  thresholds; attach SUPERSEDED banners; upgrade the mirror-contract to
  value-equality.
- Wire the three governance-store paths + the registry path into config
  (`.env`) — nothing durable is seeded until then.
- DT-4.2 emission code + runtime freeze-coverage verification.
