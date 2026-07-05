# Steward Wave 4 — Observer + Proposer Completion Report

**Branch:** `wave4-officer` (off merged main; NOT merged — for review)
**Scope:** The correction officer's OBSERVER half (append-only ledger writes) and
the PROPOSER (append-only proposal records). The fork-executing gate, currency-
pointer flip, and stabilization window are DEFERRED to Wave 5. The officer is
FRAMEWORK machinery under `steward/`, not a sixth agent.
**Status:** All six tasks complete. STOP — Wave 4 boundary reached.

---

## Store B wiring (Task 1)

- `config.store_b_path()` / `open_store_b()` open the frozen framework `StoreB`
  (Wave 1 DDL — append-only + no-mutation triggers — not recreated). Distinct
  file from Store A / app db / checkpointer / registry. `.env.example` documents
  `STORE_B_DB_PATH`. Two Wave 3 "Store B unwired" tests updated (it is now wired
  for the observer; fast-loop agents still never touch it).

## Observer check-set + neutrality proof (Tasks 2–4)

**Predicate runner (framework, `steward/officer/`, DC-1 clean):** deterministic,
no-LLM. Per invocation it loads the PINNED skill via the Wave 2 loader — judged
against the record's `skill_version_id`, NEVER the current pointer (verified: a
record pinned @v1 is checked by @v1 even when @v2 exists) — runs each declared
constraint's predicate, and emits one Store B entry per divergence through the
observer-only, insert-only `ObserverLedgerWriter` (stamps the officer identity;
no update/delete method; append-only trigger stands — DT-6.4). A declared
constraint with no registered predicate is a BUILD ERROR, never a silent skip.

**v1 check-set (paper_trader, DT-11.3):** Execute (no unauthorized trade / skips
carry risk_reason), Predict (View ≥ T, NoView carries reason, rationale-iff-llm),
Filter (skips carry the failed criterion), Research (per-asset call budget),
PostMortem (scoring completeness). Structurally-guaranteed constraints (zero-LLM,
write-set) are registered no-ops so they are not build errors. `build_v1_registry`
covers EVERY declared @v1 constraint (tested). CONDUCT not PERFORMANCE — a bad
forecast is not a divergence.

**Outcome-mismatch (DT-11.5):** a recorded PostMortem miss yields an
`outcome-mismatch` entry citing the settling PostMortem invocation (`invocation_id`)
and referencing the original prediction in evidence. Tagged outcome-mismatch, not
constraint-violation.

**Wired as the TERMINAL graph node (I-1):** runs post-hoc after header emission
(so this cycle's Store A exists to read), read-only on the trade path, non-blocking.

**NEUTRALITY PROOF (Task 4):** the same deterministic cycle run observer-PRESENT
vs observer-ABSENT yields **BYTE-IDENTICAL trade_decisions AND paper_trades**.

## Proposer — guard + cite-never-assert (Task 5)

Framework machinery SEPARATE from the observer (the ledger is the only channel).
`steward/officer/proposer.py` reads ONLY Store B + skill versions; never the fast
loop or app db (asserted). It MAY use an LLM narrator to draft prose, but
**cite-never-assert is structural**: evidence is gathered first, empty →
`ProposerDeclinedError`; the rationale keeps a deterministic evidence anchor even
with an LLM draft. The proposal store (`steward/storage/proposals.py`, §8 record,
own file) rejects empty `evidence_refs` (`EmptyEvidenceError`). One-proposal-at-a-
time guard (DT-12.4): declines a second proposal against a skill already in
PROPOSED/APPROVED/IN_WINDOW; allows a different skill. `run_proposer.py` is the
slow-cadence entry point. **NO approve / fork / pointer-flip / skill-version-write
anywhere** (verified).

## Lifecycle state machine (Task 6)

`steward/officer/lifecycle.py` encodes spec §8.1: PROPOSED →
APPROVED/REJECTED/SUPERSEDED; APPROVED → IN_WINDOW/SUPERSEDED; IN_WINDOW →
SUCCEEDED/FAILED/INCONCLUSIVE/SUPERSEDED; terminals have no outgoing.
`validate_transition` rejects illegal transitions. `execute_transition` is the
**Wave 5 SEAM** — it validates now and raises `NotImplementedError` for the
side-effecting fork path; **no proposal is advanced in Wave 4**.

## Sample rendered review doc (Task 6 / DT-12.2)

A PROPOSED proposal renders as markdown with EVERY cited Store B entry inlined IN
FULL (evidence read, not referenced), a high-complexity cooling-off banner (§8.4),
a mandatory-decision-note note, and loud flagging of unresolved refs. Example:

```markdown
# Proposal prop-2026-07-06-a — PROPOSED

- **target_skill:** `paper-trader/predict/predict`
- **base_version_id:** `paper-trader/predict/predict@v1`
- **complexity:** high

## Proposed change
{ "constraint": "raise confidence threshold T 0.60 -> 0.65" }

## Cited evidence (1 entry)
> Every cited ledger entry is inlined IN FULL below — read the evidence …
**⚠ HIGH complexity** — mandatory cooling-off; gate in a different session …

### Ledger entry `cyc-1:obs:000`
- observation_type: outcome-mismatch
- subject: predict/paper-trader/predict/predict@v1
**evidence:** { "magnitude_error": 3.0, "original_prediction_ref": "42",
                "simulated_pnl": -50.0 }
```

## Aggregate tests

**313 passed, 0 failed** (was 256 pre-wave). ruff + mypy clean across all new
modules. DC-1 boundary green (the observer/proposer under `steward/` import no
`paper_trader`). No network in tests. Observer/proposer are deterministic (the
proposer's LLM narrator is faked).

Commits (branch `wave4-officer`): `b7e683c` T1 · `d950b90` T2 · `da98fe3` T3 ·
`18bc51b` T4 · `41c16c1` T5 · `21ba5f3` T6.

## Deviations & ambiguities

1. **Predicate key = `(agent, constraint_id)`, not G6's typed `type`.** The
   ratified @v1 skills carry `{id, text}` (prose, verbatim from Appendix A), not
   `{id, type, params}`. Predicates key on the composite the skills actually
   provide; the build-error-on-missing-predicate invariant is preserved. Recorded
   in `predicates.py`.
2. **Proposal is a new framework store** (`steward/storage/proposals.py`, own
   file). Reconcile line 228 names the proposal a framework-defined governance
   record alongside Store A/B/skill-version; none of the docs pin its file, so it
   gets its own — consistent with the never-co-mingle pattern. Its lifecycle
   columns are mutable (the proposal is the one record whose state moves), unlike
   the append-only Store A/B — noted in the schema. Not a spec gap.
3. **Execute C1 absolute-cap check is structural-symmetry only** — the frozen
   write-set snapshot (Wave 3) carries `trade_decisions`/`new_paper_trades` but
   not cycle equity, so the observer checks that every recorded trade has a
   matching executed decision (unauthorized execution = breach) rather than
   recomputing `notional ≤ max_position_pct × equity`. Flagged in code; a richer
   input freeze would enable the full arithmetic check.
4. **Observer requires emission** (Store A must be populated to observe). With
   emission OFF the observer does not run — consistent, and tested.

No fast-loop behavior changed (neutrality proven). No Store B UPDATE/DELETE. No
fork, pointer flip, skill-version row, or gate CLI. No spec amendment required.

## Deferred to Wave 5 (do NOT do until opened)

The gate CLI (list/show/approve/reject); the atomic fork (new version row +
currency-pointer flip + window timestamps); HumanLayer build-vs-adopt;
stabilization-window recording; advancing any proposal past PROPOSED.

## Deferred to Wave 6

Replay; the DT-12.5 governance acceptance test.
