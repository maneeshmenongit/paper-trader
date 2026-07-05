# Steward Wave 5 — Gate + Atomic Fork Completion Report

**Branch:** `wave5-gate-fork` (off wave4 tip; NOT merged — for review)
**Scope:** The gate CLI, anti-rubber-stamp ritual, and the atomic fork — the one
wave that mutates the currency pointer and changes runtime behavior. Plus the
equity-freeze amendment (Wave 4 deviation-3 fix). Framework code under `steward/`.
**Status:** All six tasks complete. STOP — Wave 5 boundary reached.

---

## Equity-freeze neutrality result (Task 1)

Execute records the portfolio equity in effect at Execute time (cash + open
position notionals) and exposes `frozen_facts()`; the emission boundary merges it
into that invocation's Store A `agent_input`. Equity is domain state, not a secret
(DT-4.2 freeze checklist). **NEUTRALITY RE-PROVEN:** emission on-vs-off still
yields BYTE-IDENTICAL `trade_decisions` + `paper_trades` (Wave 3 + Wave 4
neutrality tests green). Inert — never affects a trade decision.

## Observer C1 upgrade (Task 2)

`execute_no_cap_breach` now recomputes `notional <= max_position_pct *
frozen_equity` when the frozen equity is present (float tolerance so exact-cap is
not a false positive). Pre-amendment records lack the field (Store A is
append-only — old rows cannot gain it), so those fall back cleanly to the
symmetry-only check (unauthorized-execution). Tested: compliant passes, oversized
authorized trade flags, exact-cap not flagged, pre-amendment falls back, symmetry
still catches an unauthorized execution.

## Gate CLI (Tasks 3–5)

Framework machinery, `steward/officer/gate.py`. A small LOCAL gate (ruling: build,
don't adopt HumanLayer). It is the ONLY approve path and the ONLY place the fork
runs.

- **`list_proposals`** — open proposals (PROPOSED/APPROVED/IN_WINDOW), summary.
- **`show <id>`** — renders the Wave 4 review doc (evidence inlined in full) and
  stamps a first-viewed session+timestamp ONCE (idempotent — a later view never
  overwrites the first). No other mutation.
- **`reject <id>`** — mandatory non-empty `decision_note`; → REJECTED via the
  lifecycle machine (illegal from a terminal state); records `decided_by`/`at`.
- **`approve <id>`** — see atomic fork below.

## Ritual enforcement (Task 4)

`decision_note` is mandatory + non-empty on EVERY decision (approve AND reject).
Cooling-off (`_ensure_cooling_off`, §8.4): **low** complexity → same-session ack
allowed; **high** → approval blocked unless the deciding session differs from the
first-viewed session, and blocked entirely if never shown. The calendar
substitutes for a second person.

## Atomic-fork test results (Task 5)

`registry.fork_version` is an additive framework primitive (the ruling locates the
atomic core in the skill registry): in ONE single-file transaction it inserts the
new version row (parent=base, proposal FK, origin=slow-loop-fork, grounding_refs
copied, UNVALIDATED, ordinal=parent+1) AND flips the currency pointer — all-or-
nothing.

`gate approve` runs the DT-12.1 sequence: **(a)** write approval → **(b)** atomic
registry fork → **(c)** window (14 days OR 20 settled trades, whichever later;
`evaluation` stays null) + IN_WINDOW. In-process rollback-on-error: a fork failure
reverts the approval.

Tests:
- **full approve** → exactly one `@v2` row (parent @v1, origin slow-loop-fork,
  UNVALIDATED) + pointer flipped to @v2 + proposal IN_WINDOW with window recorded.
- **empty note** → refused.
- **forced failure in (b)** → NO version row, NO pointer move, proposal reverted to
  PROPOSED (no partial state).
- **registry fork atomic** → a duplicate-PK insert fails and the pointer never
  moves (same rolled-back transaction) → the pointer never references a missing
  version.

## Crash-reconciliation results (Task 6)

`gate.reconcile()` runs at startup over APPROVED proposals (a transient status; a
lingering APPROVED means a mid-sequence crash):
- **crash between (b) and (c)** (fork committed, bookkeeping not done) → COMPLETE
  step (c): stamp window + IN_WINDOW, repair the pointer if needed. Tested.
- **crash between (a) and (b)** (approval written, fork not done) → ROLL BACK the
  approval to PROPOSED (pointer unmoved, no version row). Tested.
- Invariant after reconcile: **IN_WINDOW ⟺ a fork exists; PROPOSED ⟺ no fork** —
  never a half-applied fork. Tested. A consistent IN_WINDOW proposal is a no-op.

## Fork-is-gate-CLI-only — confirmed

`registry.fork_version` has exactly one caller: `gate.approve` (verified by grep).
The only other pointer-mutation call, `set_current_version` in `_repair_pointer`,
is gate-internal (startup reconciliation completing an already-committed fork), not
a new fork path. **No code path inserts a slow-loop-fork version or flips the
pointer outside the gate approve/reconcile machinery** (the optional-gate-leak
inoculation holds).

## Aggregate tests

**343 passed, 0 failed** (was 313 pre-wave). ruff + mypy clean. DC-1 green. No
network. **No Store A/B DDL change. No UPDATE/DELETE of any append-only row** (the
proposals table — the one legitimately-mutable lifecycle record — is the only
UPDATE target; Store A/B stay append-only with their triggers).

Commits (branch `wave5-gate-fork`): `d442c47` T1 · `6b97e14` T2 · `c417578` T3 ·
`53eb991` T4 · `99860d5` T5 · `2d16504` T6.

## Deviations & ambiguities

1. **`skill_version.py` extended with `fork_version` + `version_by_proposal`.**
   Wave 1 marked the framework "frozen," but the ruling explicitly locates the
   atomic fork core "in the skill registry," and a single-file atomic transaction
   REQUIRES both writes on one connection — impossible by composing the existing
   separate methods. These additions are additive (existing methods unchanged) and
   ruling-directed. The Wave 1 registry-surface test was updated (+2 methods; the
   no-delete guard stands).
2. **`new_content` is human-authored at approval, not derived from
   `proposed_change`.** The docs define `proposed_change` as "the additive change
   (structured, not prose)" but do NOT specify a YAML-patch engine that turns it
   into new skill content. `gate approve` takes `new_content` as a parameter — the
   human authors @vN's exact content at approval, consistent with human-gated
   approval. Not a spec gap (the fork mechanism is fully defined; only content
   authoring is delegated to the human).
3. **Window encoding.** `window_closes_at` stores a JSON `{time_bound (14d),
   min_settled_trades: 20, rule: whichever_later}` since the schema has one
   `window_closes_at` column but DT-12.3's condition is two-part. Both are recorded
   at approval; `evaluation` stays null (v1 stub).
4. **`_repair_pointer` uses `set_current_version`** — a belt-and-braces flip during
   reconciliation for an already-committed fork (the fork is atomic so the pointer
   should already be flipped; this is idempotent safety). Gate-internal, not a new
   fork path.

No hard-stop conditions hit. No replay, no DT-12.5 acceptance test, no
IN_WINDOW→verdict. No spec amendment required.

## Deferred to Wave 6 (do NOT do until opened)

Replay; the DT-12.5 governance acceptance test; any resolution of IN_WINDOW →
SUCCEEDED/FAILED/INCONCLUSIVE (`evaluation` stays null in v1).
