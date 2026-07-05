# Steward Wave 3 — Store A Emission Completion Report

**Branch:** `wave3-store-a-emission` (stacked on Waves 1/2/2.5; NOT merged — for review)
**Scope:** Attach execution-trace (Store A) emission onto the Wave 2.5 domain
loop. Pure emission — **Store B untouched**, nothing in the fast loop writes the
ledger. Framework Store A writer is frozen; this wave writes application-level
emission under `src/paper_trader/`.
**Status:** All six tasks complete. STOP — Wave 3 boundary reached.

---

## Config wiring (Task 1)

- `config.store_a_path()` reads `STORE_A_DB_PATH` (default `./data/store_a.sqlite`);
  `config.open_store_a()` opens the frozen framework `StoreA` by injected path
  (schema applied, distinct file). `APPLICATION_ID = "paper-trader"` for record
  stamping.
- `.env.example` documents `SKILL_REGISTRY_DB_PATH` + `STORE_A_DB_PATH`.
- **Store B deliberately NOT wired** (asserted) — no ledger write path exists.

## ULID switch (Task 2, DT-4.1)

- `graph.ids.new_cycle_id(clock)` → 26-char ULID timestamped from the **injected
  Clock** (deterministic, replay-orderable). Declared `python-ulid>=2.0`.
- **Downstream note:** `cycle_id` was never actually generated in code before this
  (CycleState declared it as an opaque `str`; callers/tests passed literals).
  **No consumer assumed uuid4 format** — no length checks, no parsing, no
  format-bound checkpointer key; all DB columns are `TEXT`. The ULID is a drop-in
  with zero schema/behavior change (asserted against predictions/trade_decisions/
  paper_trades).

## Emission-off-vs-on diff result — THE NEUTRALITY PROOF (Task 5)

**PASS — trade_decisions and paper_trades are BYTE-IDENTICAL emission-OFF vs
emission-ON** for the same deterministic cycle (same fakes, frozen Clock, frozen
inputs, fixed cycle_id). Emission is additive: it reads frozen facts and writes
Store A; it never alters a trade decision. Emitted rows are insert-only (Store A
no-mutation triggers reject UPDATE/DELETE); the header is emitted exactly once.

Emission is behind a flag: `emitter=None` (or disabled) → the plain
write-enforcement path; an `Emitter` present → the emission path. Same returned
state either way.

## Emission architecture (Tasks 3, 4)

- **App-level adapter** (`emission.py`): reads CycleState frozen facts, calls the
  generic framework writer. **Orchestrator-level** — domain agents get NO Store A
  seam (verified: no `store_a`/`emit` references in any agent).
- **Invocation emission** (DT-4.3): a boundary wrapper (`graph/emit_boundary.py`)
  runs around each agent after write-enforcement, capturing frozen `agent_input`
  (write-set before) + `agent_output` (write-set after) + the `skill_version_id`
  pin + `application_id`. One invocation per agent that ran.
- **Header emission** (DT-4.2/4.4): one immutable `cycle_header` at terminus.
  Frozen `orchestrator_input` per the freeze checklist; `orchestrator_decision`
  (cycle shape); `decision_mode='rule'` for all v1 (dormant LLM slot never yields
  'llm'); `trigger_kind='schedule'`; `status` completed|partial.
- **NON-BLOCKING:** emission never raises. Failures are logged at ERROR and
  recorded in `Emitter.failed_emissions` (untraced writes detectable, never
  silent). A committed paper trade always stands.

## Replay-sufficiency findings (Task 6)

**No gap found.** A completed cycle's Store A record contains everything replay
needs from the Store A sources of the four-source join:
- **Header** — every replay field non-null; frozen input + decision are valid
  JSON (re-derivable); `decision_mode` is the rule|llm tag; status/trigger/timing
  present.
- **Invocations** — one per agent that ran; each carries the pin + frozen
  input/output + timing + status; `agent_output` is never null ("no output" would
  be serialized explicitly).
- **Pin → content** — every emitted `skill_version_id` resolves to real skill
  content via the loader (hash-verified) — replay source (3) reachable by pin.
- **Join** — anchored on `cycle_id`; all invocations join to the one header.

Source (4), Store B, is out of scope this wave (no ledger emission).

## Aggregate tests

**256 passed, 0 failed** (was 234 at Wave 3 start / 228 pre-wave). ruff + mypy
clean across all new modules. DC-1 boundary green. No network in tests (fakes
only). Clock injected everywhere.

Commits (branch `wave3-store-a-emission`): `9667334` T1 · `09e3dbb` T2 ·
`b13bff8` T3 · `75166ac` T4 · `1b91e13` T5 · `8768150` T6.

## Deviations & ambiguities

1. **Invocation buffering (FK-driven, NOT a spec gap).** The frozen Store A schema
   enforces `agent_invocations.cycle_id → cycle_headers` FK. DT-4.2 emits the
   header at cycle terminus, but invocations are captured mid-cycle. Resolved by
   **buffering invocations** during the cycle and flushing them after the header
   lands. Header-at-terminus + the FK are reconciled; the framework's own schema
   forces this order. If the header fails, buffered invocations are recorded as
   un-emittable (loud).
2. **`trigger_kind='schedule'`** chosen for the live cron loop (Store A CHECK is
   schedule|event|manual). Configurable on the supervisor; v1 default is the cron
   schedule. Flag if a different default is wanted.
3. **`agent_input`/`agent_output` = the agent's write-set snapshot** (before/after)
   rather than a full read-set capture. The write-set is what's declared and
   auditable; a precise read-set isn't declared on agents. Sufficient for replay's
   "what each agent produced"; a richer input capture can be added if replay later
   wants the full upstream context.
4. **`decision_mode` is always 'rule'** this wave — correct per DT-4.4 (all v1
   decisions deterministic; the dormant LLM slot never fires). The header schema
   accepts 'llm'; nothing emits it yet.
5. **New env var `STORE_A_DB_PATH`** added to `.env.example`; `SKILL_REGISTRY_DB_PATH`
   documented there too (was undocumented from Wave 2.5).
6. Updated one Wave 2.5 test whose "Store A unwired" assumption Wave 3 legitimately
   supersedes (now asserts only Store B stays unwired).

No framework code changed. **No Store B write anywhere.** No spec amendment required.

## Deferred (do NOT do until opened)

Store B emission; the officer; replay (the reader); full method-selector Predict;
provisional cleanup (Kelly interior math, sector cap, baseline settlement); live
data clients; wiring Store B path into config.
