# Steward Wave 6 — Replay + DT-12.5 Acceptance Completion Report

**Branch:** `wave6-replay-acceptance` (off merged main; NOT merged — for review)
**Scope:** Reconstructive replay (read-only) + the DT-12.5 governance acceptance
test — the final wave, the governance half's definition of done. Framework code
under `steward/`.
**Status:** All four tasks complete. STOP — Wave 6 boundary reached. **§9.2 Waves
1–6 are done.**

---

## Four-source join (Task 1, DT-13.x)

`steward/officer/replay.py` (framework, DC-1 clean — 0 paper_trader imports).
Replay is a READER: never executes agents, calls an LLM, or writes/mutates.
`reconstruct(cycle_id)` joins on cycle_id:
1. the cycle_header (Store A);
2. all agent_invocations, ordered (Store A);
3. the pinned skill content per invocation — resolved by the RECORD's
   `skill_version_id`, **never the current pointer** (a cycle whose Predict pinned
   @v1 reconstructs @v1 content even when @v2 is current — verified);
4. Store B ledger entries for the cycle.

**READ-ONLY BY CONSTRUCTION:** every connection opens `file:...?mode=ro` (a stray
write raises — tested). A missing pinned version is marked MISSING, not raised.

## Hash-verification behavior (Task 2, I-8 / DT-13.2)

Each pin's stored content is re-hashed with the single canonical
`compute_content_hash` and compared to the stored `content_hash`, attaching a
per-pin trust status: **VERIFIED | UNTRUSTED | MISSING**. On mismatch → mark
UNTRUSTED and CONTINUE; the reconstruction is still returned, content still
rendered, other pins unaffected. **NEVER raises** — deliberately softer than the
Wave 2 runtime loader (which raises), because replay is a human-facing reader: a
corrupted row is evidence to see, not an exception to hide behind. Tampered rows
staged via raw INSERT (the no-mutation triggers block UPDATE/DELETE). Tested:
intact → all VERIFIED; one tampered pin → UNTRUSTED + others VERIFIED + continues;
every-pin-tampered → still returns.

## Sample replay markdown (Task 3, I-7 / DT-13.3)

`render_markdown(reconstruction)` — read-only, all four sources + a loud
top-of-document trust flag + per-pin trust badges:

```markdown
# Replay — cycle `C1`

> ✓ All skill pins hash-VERIFIED.

## Frozen situation (cycle header)
- **trigger:** schedule
- **decision_mode:** rule  (rule|llm tag)
- **status:** completed
**Frozen orchestrator_input:** { "calibration_version": "identity-v1",
  "watchlist": [{ "symbol": "AAPL" }] }
**Cycle-shape decision:** { "completed_agents": ["predict"], "trade_decision_count": 1 }

## Agent invocations (frozen decisions + pinned skill)
### predict — `paper-trader/predict/predict@v1`  [✓ VERIFIED]
… agent_input / agent_output (frozen) … skill content it ran under (content-in-row) …

## Ledger findings (Store B)
### `C1:obs:000` — outcome-mismatch   (evidence inlined, cross-cycle refs)
```

An UNTRUSTED pin flips the top banner to a loud warning; an empty ledger renders
"meaningful silence."

## DT-12.5 walk — step-by-step result (Task 4, THE definition of done)

**PASSES.** One walk of the conservative-cap path through the REAL machinery (only
market inputs faked; @v2 human-authored at approve):

| Step | What ran (real component) | Asserted |
|------|---------------------------|----------|
| (a) | pre-fork cycle under predict@v1 (supervisor + emitter) | actionable View traded; Predict invocation **pins @v1** |
| (b) | settle a controlled MISS; **real observer** (terminal node) | PostMortem scored `direction_correct=False`; observer emitted an **outcome-mismatch** entry to Store B citing the settling PostMortem invocation |
| (c) | **real proposer** reads Store B | PROPOSED against predict@v1, **citing that real evidence** (empty would be illegal) |
| (d) | **real gate** (show in one session, approve in a later one) | **atomic fork** predict@v1→@v2 (slow-loop-fork, UNVALIDATED) + **pointer flip** + window + **IN_WINDOW** |
| (e) | post-fork cycle | its Predict invocation **pins @v2** |
| (f) | **replay** pre + post cycles | both reconstruct, **all pins VERIFIED**, the Predict pin **differs across the fork** (@v1 pre, @v2 post); each cycle shows its own skill text (@v2 carries the 0.65 conservative cap) |

Every governance component — emission, observer, proposer, gate, atomic fork,
currency-pointer flip, replay, hash verification — is exercised once in this single
walk. **Phase 4 governance definition of done: MET.**

## Aggregate tests

**357 passed, 0 failed** (was 343 pre-wave). ruff + mypy clean. DC-1 green (replay
imports no paper_trader). No network. Replay makes no writes, no re-execution, no
LLM calls.

Commits (branch `wave6-replay-acceptance`): `33bcf87` T1 · `7305e82` T2 ·
`23b31f0` T3 · `3e414fb` T4.

## Deviations & ambiguities

1. **Replay fetches skill rows itself (soft-hash) rather than via the Wave 2
   loader.** The loader RAISES on mismatch (correct for the trade path); replay
   must flag-and-continue (I-8). So replay reads `content`+`content_hash` directly
   and compares with `compute_content_hash` — same canonical function, softer
   handling. Not a spec gap; it's the I-8 requirement.
2. **Outcome-mismatch subject = the Predict skill identity (DT-11.5 refinement).**
   The Wave 4 detector filed the entry under the PostMortem that observed it. But
   an outcome-mismatch is *about the Predict skill* whose forecast missed, and the
   proposer targets Predict — so the subject now names the Predict skill
   (`paper-trader/predict/predict`), while the settling PostMortem is cited via
   `invocation_id` + an `observed_by` provenance field, and the original prediction
   is referenced in evidence. This is the faithful reading of DT-11.5's "cites the
   settling PostMortem invocation and references the original prediction in
   evidence." Wave 4 outcome-mismatch tests unaffected (they asserted
   `original_prediction_ref` + type, both unchanged).
3. **@v2 content is human-authored at approve** (carried over from Wave 5): the
   docs define `proposed_change` structurally but not a YAML-patch engine, so the
   walk supplies the exact @v2 content at approve, consistent with human-gated
   approval.

No hard-stop conditions hit. Replay is read-only (no writes, no re-execution, no
LLM). No IN_WINDOW→verdict resolution (`evaluation` stays null). No spec amendment.

## Steward + paper_trader — build complete

Waves 1–6 (§9.2) are done. The fast loop trades; the governance half observes,
proposes, gates, forks, and replays — every component demonstrated end-to-end by
the DT-12.5 walk.

## Deferred to the post-v1 register (do NOT do until opened)

Full method-selector Predict (mean_reversion, arima, LLM selection);
IN_WINDOW→SUCCEEDED/FAILED/INCONCLUSIVE evaluation; live data clients; DT-7.1
frozen-value re-execution / deterministic-verification diagnostic.
