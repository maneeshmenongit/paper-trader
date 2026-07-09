# STEWARD_PAPER_TRADER_RECONCILE_001

**Status:** Phase 3 — Reconciliation record (v1, consolidated)
**Date:** 2026-07-04
**Inputs:** `STEWARD_FRAMEWORK_SPEC_001.md` (frozen), `PAPER_TRADER_ARCH_002.md` (current), `STEWARD_ALTERNATIVES_REGISTER_001.md` (reference lens)
**Purpose:** The single artifact Phase 4 builds from. Records every section verdict, every governance gate decision, every design constraint, every deferral, and the full design-task punch-list. All content herein was gated section-by-section and signed off individually before consolidation.

**Headline result: ZERO spec amendments.** Every conflict in the pass resolved *to* the frozen spec. The gap-detector ran the full reconciliation and found nothing requiring the framework to bend.

**RATIFIED (2 items, both Gate 7 — ruled 2026-07-04; see §11 Ruling record):**
- **DT-15.1** — Filter volume thresholds: **RATIFIED as written** — 20-day avg daily dollar volume ≥ $10M (stocks), 24h volume ≥ $50M (crypto), as the v1 floor, slow-loop-tunable. Ratified against the actual watchlist (majors + ~5 marginal mid-caps; no live crypto), where R2 is mostly dormant.
- **DT-15.2** — Shadowed confidence gate: **RULED — keep both, as two independently-ownable floors (higher binds), with the annotation frozen into Execute @v1** (see §11). Reframed from "defense-in-depth" to "two distinct decisions the membrane keeps separately ownable"; Execute's gate firing is an officer-observable signal that the upstream threshold dropped below 0.55.

---

## 0. How to read this document

- §1 records the method (so future readers know how verdicts were produced).
- §2 is the fast-loop reconciliation: five section verdicts against ARCH_002 §4–§8.
- §3 is the governance pass: seven gate decisions (G1–G7).
- §4 holds the two binding design constraints (DC-1, DC-2).
- §5 lists the corrections this pass made to ARCH_002's own provisional map (§0.3).
- §6 is the instantiation-decisions register — choices that are **ours**, permitted but not mandated by the spec, each with rationale. These are legitimate re-litigation targets later; spec invariants are not.
- §7 is the deferrals log, each with its named absent-need (the falsifiable un-deferral test, per spec §9.4).
- §8 records updates to the alternatives register.
- §9 is the consolidated, deduplicated DT punch-list with dependency-ordered build sequencing.
- §10 is the Phase 4 handoff: acceptance test, entry conditions, build order.
- Appendix A carries the five `@v1` skill definitions **in full** — Phase 4 authors the YAML files verbatim from Appendix A.

---

## 1. Method (recorded for provenance)

- **Posture: audit, not derive.** ARCH_002 §0.3 shipped a provisional map; this pass stress-tested it section by section, looking hardest for over-optimistic placements. Confirmations state why; corrections cite the forcing invariant.
- **Verdict schema:** survives-unchanged / survives-but-remaps / net-new, plus a **conflict flag** that can ride any verdict (a section describing something Steward forbids is a conflict, not a remap).
- **Direction is one-way:** ARCH_002 reconciles *to* the frozen spec. Anything unresolvable without changing the spec surfaces as a recorded amendment candidate. (None surfaced.)
- **Verdicts separate from design:** each section produced a verdict plus *spawned design tasks*; design was executed in its own gated units (G1–G7), never inline with a verdict.
- **Cadence:** section-level gates, one sign-off per unit, eleven gated units total (§4, §5, §6, §7, §8, G1–G7 with G6/G7 splitting the skill-content pass).

---

## 2. Fast-loop reconciliation — section verdicts

### 2.1 Summary table

| ARCH_002 § | Subject | Verdict | Maps onto (spec §) | Conflict? |
|---|---|---|---|---|
| §4 | CycleState | survives-but-remaps | Store A: cycle header §5.1 + invocations §5.2 | No |
| §5 | Supervisor | survives-but-remaps | Orchestrator §4.4 | **Yes — Decision B** (resolved) |
| §6 | Agent contracts | survives-but-remaps (Predict output **replaced**) | Agents + skill files §4.1–4.2 | No |
| §7 | Data layer | survives-unchanged | n/a (domain) | No |
| §8 | Persistence | survives-but-remaps | Stores §5.4 (four logical stores) | No |

### 2.2 §4 CycleState — survives-but-remaps

**Sharpened placement:** not a rename but a **one-to-two emission**. CycleState survives exactly as-is (mutable, ephemeral, checkpointer-serialized, crash-recovery). At defined decision points it *emits* immutable frozen facts into Store A — a new artifact alongside, not a replacement. Purpose split: crash recovery (CycleState) vs reconstructive replay (Store A, spec §3).

**Deltas found (line-level):**
1. `cycle_id` is uuid4; spec §5.1 requires monotonic/ordered (ULID). Type correction. → DT-4.1
2. No `trigger` field (schedule/event/manual). → DT-4.2
3. No `skill_version_id` pin — the most important field in the membrane (spec §5.2). Was blocked on versioning; unblocked by G2. → DT-4.3
4. No rule-made|LLM-made decision tag — the field that makes LLM escalations officer-observable. → DT-4.4
5. Freeze discipline unmet: `orchestrator_input` must hold "everything the decision depended on and nothing it didn't" (§5.1); CycleState's inputs block is broader. Identifying the decision-relevant frozen subset is design work. → DT-4.2
6. `[v2-FLAG]` working memory typed `dict[str, DirectionalPrediction]` — dead-thesis type; resolved by the G6 output union. → DT-4.5 (resolved)

### 2.3 §5 Supervisor — survives-but-remaps, one conflict (resolved)

**Clean part:** Decisions A, C, D, E are deterministic `if/elif` — they *are* the rules-first sequencer (spec §4.4). Each gains a rule-made tag and Store A freezing. Decision E's `[v2-FLAG]` ("any UP") becomes "any actionable View (direction ≠ HOLD)" per the G6 output union.

**The conflict — Decision B.** ARCH_002 §0.3 filed B as "seed of Steward's LLM-fallback slot." Corrected: B is an **always-on LLM routing node** (positive trigger: fires whenever settlements exist and budget allows), whereas the spec's fallback slot activates on a *negative* trigger (no rule covered the case) and stays dormant until a genuine no-writable-`if` case appears (§4.4, §9.1, §9.3). Worse, B observes this cycle's settlement outcomes and immediately adjusts predict behavior within the same cycle — the fast loop doing the slow loop's job, the exact fusion the framework exists to prevent (spec §2). ARCH_002 itself concedes (line ~495) a deterministic rule would work.

**Resolution (signed off):** demote and split.
- Routing half (proceed vs skip-cycle) → deterministic rule, rule-tagged, frozen. → DT-5.1
- Adaptation half ("go conservative on recent miscalibration") → re-homed to the governed slow loop as the framework's flagship worked example: PostMortem scores → officer observes divergence → proposer drafts Predict-skill change → human gate → version fork. → DT-5.2 (later elevated to Phase 4 acceptance test, DT-12.5)
- LLM-fallback slot: built but **dormant** in v1 per spec. → DT-5.4
- **Named trap (do not do):** do not "fix" B by letting Predict read `recent_post_mortems` to self-adjust in-cycle — that relocates the same fusion and imports the v2-deferred agent-performance-memory (§9.3). This line held through the G6/G7 skill authoring.

**Tension 1 resolved:** budget-downgrade (resource trigger) and rule-miss escalation (capability trigger) are orthogonal axes; they collide only in one cell — *no rule covers AND budget exhausted*. Resolution: recorded safe-default (end/skip the undecided step) **plus** a ledger entry ("no-rule case, could not escalate, budget-exhausted") feeding the convergence path. With B demoted, v1 has no live LLM routing at all, so the cell is dormant — specified, seamed, cannot fire. → DT-5.3

**Cost, named honestly:** v1 loses same-cycle LLM pattern-spotting; the adjustment arrives one governed slow-loop later. That latency is spec §2.4's governance gap working as designed, not a regression.

### 2.4 §6 Agent contracts — survives-but-remaps; Predict output REPLACED

- Roster (Filter, Research, Predict, Execute, PostMortem) → fixed Steward roster (§4.4, no runtime invention).
- `enforce_writes` decorator → survives unchanged; it *is* per-agent write authorization, and becomes the enforcement point for the membrane (ledger-write prohibition is a new entry in the same machinery). → DT-6.4
- **Core finding:** the contract table declares I/O scope, not behavior. Behavioral constraints lived in §6.2 prose, unevenly explicit (Execute crisp; Filter's "sufficient daily volume" declared nothing checkable). The officer can only flag divergence from *declared* constraints — vague skills produce no evidence (spec §4.1 note). Remap is two-layered: (a) contract table survives as write-auth + gains the version pin; (b) §6.2 prose promoted to explicit declared constraints per agent. → DT-6.2 (resolved G6/G7)
- **Predict:** thesis-level **replacement**. Dead LLM-as-forecaster (T02–T04 FAIL: +0.1pp vs +3pp required; momentum 47 vs LLM 36 head-to-head) → live LLM-as-method-selector, status UNVALIDATED. Predict is the template: same rules-first-then-LLM shape inside the agent that the orchestrator has at cycle level. Output dataclass replaced. → DT-6.1 (resolved G6)
- **Momentum dual role:** selectable method inside the selector AND independent baseline shadow. Must remain separate computations — the selector cannot contaminate its own measuring stick. → DT-6.5 (became Predict constraint C4)
- **PostMortem ≠ officer (ARCH_002 §0.4), held and confirmed.** PostMortem survives as fast-loop domain scorer (app db); officer is net-new, built alongside. PostMortem never gains ledger-write auth.
- **Forward-flag raised here, resolved at G1:** risk thresholds in `risk_gates.toml` are behavioral → skill content, not config.

### 2.5 §7 Data layer — survives-unchanged

Protocols, live clients, semaphores, fakes: pure domain infrastructure; Steward never touches them. Hunted for a hidden governance dependency; none exists.

**Useful observation:** the seam-plus-injection discipline *pre-pays* for reconstructive replay — injectable Clock makes `now()` freezable; providers are the source of non-determinism that DT-4.3's input-freezing captures. Retry-with-backoff lives at the data-client layer, exactly where Predict's transient-failure/routing-uncertainty distinction wants it.

**Self-correction (recorded at G5):** DT-7.1 (frozen-value Protocol impls) was over-scoped here as "replay substrate." v1 replay is a pure reader and does not consume it. Re-scoped: deferred alongside the deterministic-verification diagnostic (§7 of this doc).

### 2.6 §8 Persistence — survives-but-remaps; corrects §0.3

**The correction:** §0.3 filed persistence as "two-DB separation, essentially unchanged." False. Paper-trader's two DBs (app + checkpointer) and Steward's two stores (A trace + B ledger) are different cuts. The union is **four logical stores**:

1. **checkpointer.sqlite** — crash recovery, mutable, LangGraph-managed. Neither A nor B. Survives unchanged.
2. **app db (`paper_trader.sqlite`)** — domain history. Survives as domain history, explicitly NOT Store A.
3. **Store A (execution trace)** — NET-NEW. Cycle headers + agent invocations; immutable; version-pinned; frozen inputs/decisions/tags.
4. **Store B (ledger)** — NET-NEW. Officer evidence; append-only; no action field; physically separate file (spec §5.4).

**Decisive reason app db ≠ Store A: mutability.** `paper_trades` is UPDATEd at settlement (exit fields). A table that mutates over a trade's life cannot also be the frozen record of cycle-time decisions — contradictory contracts on the same row. Append-only-ness of some domain tables is necessary-not-sufficient (they lack frozen decision context and skill pins).

**Sharp distinctions:**
- `cycle_runs` (ops telemetry) ≠ Store A cycle header (frozen audit context). Both keyed by `cycle_id`; cross-reference, never merge. → DT-8.4
- `predictions` table carries the `[v2-FLAG]` (`direction IN ('UP','DOWN','HOLD')`); reconciled with the G6 output union; `skill_version_id` canonical in Store A, mirrored into domain tables only as query convenience. → DT-8.3
- Membrane at the storage layer = Store B physical separation + officer-only write-auth. Oracle-agents lesson generalizes: four stores, four connection paths, never co-mingled. → DT-8.5

---

## 3. Governance pass — gate decisions G1–G7

### G1 — Skill/config boundary (signed off)

**Separating test:** *is this a rule the agent applies to make a decision, or a value the agent operates over?* Rules → skill; inputs → config.

- **Skill content** (versioned, gated, officer-observable): all of `risk_gates.toml` (position sizing, exposure limits, loss limits, execution gates); Filter's criteria thresholds; Predict's routing rules. The TOML file **dissolves into Execute's skill**.
- **Config** (ungoverned, frozen into trace for replay): API keys, paths, log level; `watchlist`, `CYCLE_TIME_HORIZON_HOURS`, `CYCLE_TOKEN_BUDGET`; Research's semaphore bounds. DT-4.2's freeze captures in-effect values; no new mechanism.
- **The hard case, ruled:** a threshold inside a rule (e.g. `max_daily_loss = 2%`) travels **with the rule as skill content** — otherwise the governance hole reopens through the number. Contrast `CYCLE_TOKEN_BUDGET`: a resource ceiling, not a domain-decision rule → config.
- **Trade-off accepted:** risk tuning becomes a gated fork instead of a TOML edit. The friction is the feature; complexity tagging keeps small threshold changes lightweight at the gate.

→ DT-9.1, DT-9.2

### G2 — Skill-version record (signed off)

One row per version of one agent's skill; anchor for the Store A pin (§5.2), the proposal fork chain (§8.2), and the officer's comparison baseline (§4.3).

- **Identity:** `{application}/{agent}/{skill_name}@v{N}` + `content_hash`. Ordinal = legible orderable handle; hash = tamper-evidence (hand-edits become detectable; replay verifies before trusting). The application prefix is DC-1 at the identity level.
- **Content lives IN the row** (serialized whole), not referenced on disk: files are hand-editable (§4.1 violation), drift from rows, and `@v3` must replay forever after `@v7` ships. Loader materializes read-only working copies. (Cost accepted: less grep-friendly; hand-editability is the attack surface, not a convenience.)
- **Lineage:** `parent_version_id` (null only for `@v1`) + `created_by_proposal_id` (null only for `@v1`, `origin: initial-authoring`). A `@v2+` row with a null proposal ref is illegal by construction — the anti-floating rule applied to versions.
- **DC-2 fields:** `origin` (initial-authoring | slow-loop-fork | human-seeded), `grounding_refs` (evidence chain denormalized from the proposal so harvest-review reads one row), validation status flag (`UNVALIDATED`/`VALIDATED`/`FAILED` + timestamp + evidence refs — the Predict thesis flag generalized into a standard slot).
- **Immutability + currency:** version rows are INSERT-only; "which version is live" is NOT a property of version rows but a separate tiny pointer table (`application/agent/skill → current_version_id`) — the one mutable cell in the subsystem.
- **Content purity:** skill content embeds NO version number and NO provenance (would pollute hashes on trivial forks); the record carries the biography, the content carries only behavior.

→ DT-10.1, DT-10.2, DT-10.3 (folded into DT-15.3)

### G3 — Correction officer (signed off)

**Framing:** the officer is **framework machinery, not a sixth agent** — no roster entry, no skill file of its own; its check-set derives from the domain agents' skills. (Who observes the observer: the human, via the ledger. Out of scope by design.)

**Observer half — two instantiation decisions (ours, spec-permitted):**
1. **Post-hoc from Store A** (last node of the cycle graph), not inline interception. Rationale: evidence derived from frozen records is re-derivable by a human (auditable by construction); failure isolation (a broken camera never breaks what it films); neutrality structural, not behavioral; zero governance cost to cycle-end detection since the observer never intervenes anyway.
2. **Deterministic predicates, no LLM.** The narrow criterion (§4.3) makes divergence checking mechanical once constraints are declared. An LLM observer reintroduces opinion at the exact point the spec excludes it. Uncheckable constraint → pressure to declare it more checkably, never license for a smarter observer.

**v1 check-set (what paper-trader feeds the officer):**
- Execute: no executed trade breaching pinned risk thresholds (highest-value check); every skip carries `risk_reason`.
- Predict: escalation observability (rule-covered → rule-routed; uncovered → LLM selection recorded); NoView carries reason; view emitted only ≥ threshold T.
- Filter: declared eligibility thresholds honored. Conduct, not performance — a bad forecast is PostMortem's outcome data, not a divergence.
- Research: call budget ≤ declared per-asset counts.
- PostMortem: scoring completeness (every settlement scored).
- Orchestrator: any LLM-made tag → `escalation-observed` entry (doubly notable in v1 where the slot is dormant).
- **Outcome-mismatch convention:** settlements land in later cycles; the entry cites the settling cycle's PostMortem invocation and references the original prediction invocation in `evidence`. Schema already accommodates (nullable `invocation_id`). → DT-11.5

**Proposer half:** separate entry point (`run_proposer.py`), slow cadence (manual/weekly — matches "weeks, not cycles"); reads only Store B + current skill versions (§7.2); LLM-articulated is appropriate here (everything faces the human gate; cite-never-assert enforced by non-empty `evidence_refs`).

**Write-auth:** officer-observer identity only for Store B INSERTs; no UPDATE/DELETE for anyone; DC-1 via application-scoped `subject`.

→ DT-11.1 … DT-11.5

### G4 — Proposal lifecycle + slow-loop operations (signed off)

Spec §8 record adopted as-is; DC-1 inherited through the G2 ID format in `target_skill`/`base_version_id`; `decided_by` kept (DC-2 provenance).

**Solo-gate ritual (anti-rubber-stamp, structural not aspirational):**
1. Proposals render as **markdown review docs with every cited ledger entry inlined in full** — evidence is read, not trusted-by-reference. → DT-12.2
2. **`decision_note` mandatory and non-empty, even for approvals** — converts reflex into recorded judgment; feeds convergence analysis.
3. **Complexity tag sets ritual weight** (§8.4): low → read, note, ack; high (touches Execute risk gates or rewrites routing) → mandatory cooling-off, gated in a *different session* than first read. The calendar substitutes for the second person.

**Fork execution is framework code, never hands — one atomic transaction:** APPROVED + note → new version row (parent, proposal FK, origin=slow-loop-fork, grounding_refs copied) → currency pointer flip → window timestamps. Any step fails, none happened. Implemented as a small gate CLI (`gate list/show/approve/reject`). HumanLayer re-evaluation trigger = this build. → DT-12.1

**One-proposal-at-a-time guard:** proposer declines to open against a skill with a proposal in PROPOSED/APPROVED/IN_WINDOW; SUPERSEDED transition exists but nothing in v1 can trigger it. → DT-12.4

**Stabilization window (v1 stub, honest):** nominal 14 days OR 20 settled trades, whichever later; both recorded at approval; `evaluation` stays null; proposals rest at IN_WINDOW. An unresolved window is a true statement about evidence volume. → DT-12.3

**DT-5.2 elevated to the Phase 4 governance acceptance test:** the conservative-cap path (PostMortem misses → outcome-mismatch entries → proposal citing them → review doc → gate → Predict `@v1→@v2` fork → pointer flip → next cycle pins `@v2`) exercises every governance component once. The governance half is not "built" until this walk completes against real records. → DT-12.5

### G5 — Reconstructive replay (signed off)

**Replay is a reader, not a runner.** Never executes agent code, never calls an LLM, never touches a provider. Read-only walk over frozen records, rendered for a human.

`replay <cycle_id>` produces a markdown reconstruction from four sources joined on `cycle_id`: (1) cycle header — trigger, frozen situation snapshot incl. frozen config values, decision + tag, rationale; (2) invocation records in order — pin, input, output, timing, status; (3) **the skill content itself** per pin (G2's content-in-row paying rent: March's cycle shows March's rules verbatim); (4) Store B entries for the cycle — including meaningful silence. Optional app-db cross-references labeled as *mutable domain context*, never frozen fact.

**Hash verification runs first** (first consumer of G2's hashes): mismatch → loud top-of-document flag, content rendered but marked UNTRUSTED, reconstruction continues — a corrupted row is evidence to see, not an exception to hide behind.

**Read-only by construction:** connections opened read-only at the connection level. `replay --range` for proposal evidence windows — composes with the G4 ritual (evidence in the doc, context one command away).

**Deferred (tempting adjacent feature):** deterministic-verification diagnostic (re-run rule logic against frozen inputs to detect code drift). No demonstrated need; DT-7.1's frozen-value impls re-scoped into this deferral.

→ DT-13.1 … DT-13.3

### G6 — EvoMap dive + skill-file shape + output union + Predict `@v1` (signed off)

**EvoMap deep-dive (register 2.1a trigger fired at DT-6.3; run against the register per standing instruction, not live research):**
- (a) Genes/Capsules vs `proposed_change`+`evidence_refs`: structured-typed-changes affirmation already in spec (§8) — nothing to amend. Gene-style reusable pattern library fails the n=1 test → deferred. Capsule-style bundled changes conflict with one-proposal-at-a-time → rejected (our constraint is deliberate).
- (b) Events log vs ledger: register cannot establish one-way-ness; ours is stricter by invariant; nothing to borrow.
- (c) Optional-gate leak vector: change assets with self-applying semantics. Inoculated — G4 made the fork executable only by the gate CLI transaction.
- (d) Spec amendment warranted: **NO.** Dive closed with zero amendments. Register 2.1a → done.

**Skill-file shape (DT-6.3, resolved):** YAML, serialized whole into the version row, materialized read-only. Governing principle: **skills declare parameters; predicates live in code** — typed constraint declarations key into a registered predicate; a constraint type with no registered predicate is a build error (vagueness caught by the test suite). Five sections: `mandate` (prose, the bounded job) / `rules` (ordered `{id, condition, action}`, thresholds inline per G1) / `constraints` (`{id, type, params, description}` → predicate registry; rules are the agent's instructions, constraints the auditable claims — same threshold may appear in both) / `terminal_outputs` (all valid outputs incl. honest failures) / `escalation` (what runs where no rule covers + what must be recorded; may be `none` by declaration).

**DT-6.1 resolved — the method-selector output union.** The dead thesis killed *who forecasts*, not *what a forecast looks like*; direction/magnitude/confidence survive as payload with new provenance:
- `View`: symbol, `method_selected` (momentum | mean_reversion | arima), `selection_mode` (rule | llm), `selection_rationale` (required iff llm), direction, magnitude_pct, horizon, confidence, method-inputs summary for the freeze.
- `NoView`: symbol, reason, `methods_considered`.
- `selection_mode` is load-bearing: the agent-level twin of the orchestrator's decision tag; what makes Predict's internal escalations officer-observable.
- Unblocks: DT-4.5 (working memory type), DT-5.5 (Decision E = any View with direction ≠ HOLD), DT-8.3 (predictions table gains `method_selected`/`selection_mode`).

**Predict `@v1`:** see Appendix A.1. Honest starting posture: rules section deliberately thin (eligibility mechanics only); nearly every real selection escalates — the UNVALIDATED thesis being exercised, every `selection_mode: llm` record is evidence, rules accrete via the convergence path. Thesis flag: `UNVALIDATED, 2026-07-04, evidence: T02–T04 FAIL of predecessor (+0.1pp vs +3pp; momentum 47 / LLM 36)`.

### G7 — Filter, Research, Execute, PostMortem `@v1` (signed off; two threshold rulings pending)

Template note: for these four, `escalation: none` **by declaration** — itself checkable (LLM-call counters give the observer a predicate; a nonzero count where zero is declared is a divergence). Full definitions in Appendix A.2–A.5. Highlights:
- **Filter:** the naked volume criterion gets numbers (PENDING DT-15.1); freshness already had one (60 min). Completeness constraint: every watchlist entry → exactly one of tradeable/skip.
- **Research:** semaphore bounds deliberately stay config (G1 test: politeness limits, not decision rules). Declared honest degradation: failed summary → sentiment-only, never fabrication.
- **Execute:** `risk_gates.toml` dissolves into the skill whole; idempotency (no double-write per prediction_id) promoted from folklore to declared rule. Shadowed confidence gate flagged (PENDING DT-15.2; rec: keep both, annotated).
- **PostMortem:** bias_tags declared nullable (a null tag is compliant; an invented one is not); mandate textually restates the §0.4 line — measures, never reacts; app db only, never Store B.

---

## 4. Binding design constraints

**DC-1 — Framework/application data-scoping boundary.** Three layers: framework (engine code + record shapes, reusable verbatim), application (domain agents, skill *content*, app db, config, seams), instance data (framework-shaped, application-scoped). Every governance record — Store A, Store B, skill-version, proposal — is framework-defined shape + application-scoped contents, carrying an explicit application/instance identifier. Framework tables never co-mingle two applications' data. (Enforced at the identity level by the G2 ID format.)

**DC-2 — Provenance-for-harvest.** Skill-version and ledger records capture sufficient origin, grounding-evidence, and gate-history for a human to later assess a skill's generality and perform deliberate framework harvesting. Learnings do not transfer across applications automatically; humans harvest techniques from running applications and improve the framework as development work. The legitimate seeding path: human-authored, gated, provenance-tagged (`origin: human-seeded`), starting UNVALIDATED in the new context.

---

## 5. Corrections this pass made to ARCH_002 §0.3

1. **§5 / Decision B:** not "seed of the LLM-fallback slot." It is an always-on LLM routing node performing in-cycle adaptation — demoted, split, adaptation re-homed to the slow loop (§3/G-none; see §2.3). The slot stays dormant.
2. **§8 / persistence:** not "two-DB separation, essentially unchanged." Four logical stores; mutability is why the app db cannot absorb Store A (see §2.6).
3. **§4 / CycleState:** placement correct but under-specified — one-to-two emission, not a rename (see §2.2).
4. **Self-correction:** DT-7.1 was over-scoped at the §7 verdict; re-scoped at G5 (v1 replay is a reader; frozen-value impls deferred with the verification diagnostic).

---

## 6. Instantiation-decisions register (ours — spec-permitted, not spec-mandated)

Legitimate future re-litigation targets, unlike spec invariants. Each recorded with its rationale in §3; listed here for auditability:

| # | Decision | Gate |
|---|---|---|
| I-1 | Observer runs post-hoc from Store A (not inline interception) | G3 |
| I-2 | Observer is deterministic predicates only — no LLM | G3 |
| I-3 | Proposer is a separate entry point on manual/weekly cadence | G3 |
| I-4 | Review docs inline full evidence text; `decision_note` mandatory; cooling-off for high-complexity | G4 |
| I-5 | Stabilization window parameters: 14 days OR 20 settled trades, whichever later | G4 |
| I-6 | One-proposal-per-skill guard in the proposer | G4 |
| I-7 | Replay ships as a read-only CLI producing markdown reconstructions | G5 |
| I-8 | Hash mismatch → UNTRUSTED flag + continue (never silent halt) | G5 |
| I-9 | Skill files are YAML; predicate-registry principle (parameters in skills, checks in code) | G6 |
| I-10 | Predict confidence threshold T = 0.60 (calibration source: T02–T04 data) | G6 |
| I-11 | Filter volume thresholds $10M / $50M | G7 — **RATIFIED** (2026-07-04, as written) |
| I-12 | Keep Execute's shadowed confidence gate, annotated | G7 — **RULED** (2026-07-04; annotation frozen, §11) |

---

## 7. Deferrals log (each with its named absent-need — the un-deferral test, spec §9.4)

| Deferral | Absent need | Conditions when pursued |
|---|---|---|
| Framework-level technique promotion / meta-learning | One application; nothing to generalize from | Preserve both invariants (no behavior change without a gate; provenance tagged at ingest); revisit with EvoMap prior art |
| Framework variance for incompatible application classes | No second application; no observed invariant collision | Escalation order FIXED NOW: expressiveness → recorded spec amendment → extension seam → governed variant fork (versioned fork from named spec version with recorded rationale — never a copy). Precondition: DC-1 boundary holding, DC-2 provenance intact |
| Gene-style reusable improvement-pattern library | n=1: zero earned skill changes to generalize | Revisit with the meta-learning item |
| Deterministic-verification diagnostic (+ DT-7.1 frozen-value Protocol impls) | No code-drift incident has asked for it | When built: reads frozen inputs only; record remains truth; non-deterministic steps never re-executed |
| (Reaffirmed from spec §9.3) agent performance memory / orchestrator decision memory | Unchanged | Named as the §5 trap: never serve the Decision-B adaptation by fast-loop self-reads |

---

## 8. Alternatives register updates

- **2.1a EvoMap/GEP deep-dive:** trigger fired (DT-6.3); dive executed at G6 against the register per standing instruction; **closed** — zero spec amendments; Gene-library deferral added; Capsule-bundling rejected as conflicting with a deliberate constraint.
- **2.4 HumanLayer:** re-evaluation trigger bound to DT-12.1 (gate CLI build). v1 default: hand-rolled CLI; adopt only if it reduces effort without constraining the proposal schema.
- (Unchanged: 2.2 governed-capability-evolution paper — trigger remains stabilization-stub activation; 2.3 CHANGE/drift — trigger remains officer build, relevant to DT-11.1/11.2; 2.5 Merkle chaining — trigger remains Store B build, evaluate against solo-operator threat model at DT-8.2/11.4.)

---

## 9. Consolidated DT punch-list

Deduplication applied: DT-14.1 ≡ DT-11.2 (predicate registry — kept as DT-11.2); DT-10.3 folded into DT-15.3 (authoring the five `@v1` skills); DT-4.5/DT-5.5/DT-6.1/DT-6.2/DT-6.3/DT-6.5/DT-14.3 **resolved during Phase 3** (design complete; build items reference their outputs).

### 9.1 Resolved in Phase 3 (design done; no build ambiguity remains)

| ID | Was | Resolution |
|---|---|---|
| DT-4.5 | Dead-thesis working-memory type | Typed to the View/NoView union (G6) |
| DT-5.5 | Decision E "any UP" gate | "Any View with direction ≠ HOLD" (G6) |
| DT-6.1 | Method-selector output dataclass | View/NoView union (G6) |
| DT-6.2 | Per-agent constraint audit | All five skills' constraints declared (G6/G7) |
| DT-6.3 | Skill-file artifact shape | YAML five-section shape + predicate-registry principle (G6) |
| DT-6.5 | Momentum method/baseline separation | Predict constraint C4 (G6) |
| DT-14.3 | Remaining four skills | Authored (G7) |

### 9.2 Build items, dependency-ordered

**Wave 1 — storage + versioning substrate (no dependencies):**
- DT-8.1 Store A DDL (cycle_headers + agent_invocations; own file; immutable; app-layer append-only)
- DT-8.2 Store B DDL (ledger per spec §5.3; own file; no-mutation trigger) — evaluate Merkle chaining here per register 2.5
- DT-10.1 skill-version table + currency pointer DDL
- DT-8.5 four stores, four connection paths, never co-mingled

**Wave 2 — versioned skills live (needs Wave 1):**
- DT-10.2 skill loader: materialize pinned content read-only, verify hash
- DT-15.3 author the five `@v1` YAML files verbatim from Appendix A; insert as `@v1` rows, `origin: initial-authoring`, hash-stamped (**blocked on DT-15.1/15.2 rulings**)
- DT-9.1 delete `risk_gates.toml` + Filter inline thresholds (content now lives in skills)
- DT-9.2 verify watchlist/horizon/budget freeze coverage via DT-4.2

**Wave 3 — fast-loop emission (needs Waves 1–2):**
- DT-4.1 `cycle_id` uuid4 → ULID
- DT-4.2 cycle-header emission point; frozen `orchestrator_input` subset; rationale capture; config-value freezing
- DT-4.3 agent-invocation emission at each boundary with the version pin
- DT-4.4 rule|LLM decision tag on every orchestrator decision
- DT-5.1 Decision B routing half → deterministic rule
- DT-5.3 dormant intersection cell (rule-miss ∧ budget-exhausted → safe default + ledger evidence)
- DT-5.4 LLM-fallback slot + escalation seam, dormant, tag-wired
- DT-8.3 predictions table reconciled to the union (add `method_selected`, `selection_mode`); pin canonical in Store A
- DT-8.4 keep `cycle_runs` distinct from the cycle header
- DT-6.4 write-auth extension: no domain agent writes Store B

**Wave 4 — officer (needs Wave 3 records flowing):**
- DT-11.2 predicate registry keyed by constraint type (a declared type with no registered predicate = build error)
- DT-11.1 observer node: end-of-cycle, Store A reader, predicate runner, Store B writer
- DT-11.4 ledger write-auth: officer-only INSERT + rejection trigger
- DT-11.5 outcome-mismatch later-cycle citation convention (doc + predicate support)
- DT-14.2 confirm T = 0.60 against T02–T04 calibration data at authoring

**Wave 5 — slow loop (needs Wave 4 evidence existing):**
- DT-11.3 proposer entry point (`run_proposer.py`): ledger reader → LLM-articulated, evidence-anchored proposals
- DT-12.4 one-proposal-per-skill guard
- DT-12.2 review-doc renderer (markdown, evidence inlined)
- DT-12.1 gate CLI with the atomic approve→fork→pointer→window transaction (HumanLayer evaluation here)
- DT-12.3 window parameters + stub behavior recorded at approval

**Wave 6 — replay + acceptance (needs everything):**
- DT-13.1 `replay` CLI (read-only, four-source join, markdown out)
- DT-13.2 hash-verification pass with UNTRUSTED flagging
- DT-12.5 **run the governance acceptance test**: the conservative-cap path end-to-end against real records (see §10)

**Administrative:**
- DT-13.3 record the DT-7.1 re-scope (done — this document)
- DT-15.1 / DT-15.2 human rulings (**gate for Wave 2**)

---

## 10. Phase 4 handoff

**Entry conditions:** DT-15.1 and DT-15.2 ruled; this document accepted as the frozen Phase 3 artifact.

**Build order:** Waves 1–6 above. Fast loop keeps running throughout — governance components attach alongside, never block trading cycles.

**Governance acceptance test (DT-12.5) — Phase 4 is not done until this passes:**
PostMortem scores a run of misses → observer writes outcome-mismatch entries (later-cycle citation convention) → proposer articulates the conservative-cap proposal citing those entries → review doc renders with evidence inlined → human gates with a decision note → atomic fork Predict `@v1 → @v2` → currency pointer flips → next cycle's invocation records pin `@v2` → `replay` reconstructs both a pre-fork and post-fork cycle, each showing its own skill text, hashes verified.
One walk, every governance component exercised once.

**Discipline carried forward:** comprehension before construction; no framework feature without a paper-trader need; phases don't overlap; any framework gap is a recorded spec amendment; bounded Claude Code prompts with human gates between tasks.

---

## Appendix A — the five `@v1` skill definitions (Phase 4 authors YAML verbatim from these)

Common to all: content contains no version number and no provenance (G2); identity and biography live in the version record; every threshold below is skill content (G1) — changing any of them is a gated fork.

### A.1 Predict `@v1` — application: paper_trader

- **mandate:** Produce per-symbol views by selecting among the declared forecasting methods. Bounded: returns views to the invoker; never invokes sibling agents. Selection is rules-first; LLM judgment only where no rule covers.
- **methods (declared roster):** momentum, mean_reversion, arima — each with its declared minimum input history (set at authoring from each method's mathematical requirement).
- **rules:**
  - R1: a method lacking its minimum input history for the symbol is ineligible this invocation.
  - R2: zero eligible methods → NoView (reason: no_eligible_method).
  - R3: exactly one eligible method → select it; `selection_mode: rule`.
  - R4: multiple eligible methods → escalate to LLM selection; `selection_mode: llm`.
- **constraints:**
  - C1: a View requires selected-method confidence ≥ 0.60; below → NoView (reason: below_confidence_threshold).
  - C2: every NoView carries a non-empty reason.
  - C3: `selection_rationale` present if and only if `selection_mode: llm`.
  - C4: the momentum baseline shadow is computed every cycle for every researched symbol, independent of selection, tagged `is_baseline` — the selector never contaminates its own measuring stick.
- **terminal_outputs:** View {symbol, method_selected, selection_mode, selection_rationale?, direction, magnitude_pct, horizon, confidence, method_inputs_summary} | NoView {symbol, reason, methods_considered}. NoView is a valid terminal answer, never retried — routing-uncertainty is not a transient failure; retry policy lives at the data-client layer.
- **escalation:** LLM selects among eligible methods only; must output rationale; selection recorded in the invocation record.
- **Companion artifact (application-level, lives beside the agent definition):** thesis-status flag — `UNVALIDATED, 2026-07-04, evidence: T02–T04 FAIL of predecessor thesis (+0.1pp vs +3pp required; momentum 47 / LLM 36 head-to-head)`.

### A.2 Filter `@v1` — application: paper_trader

- **mandate:** Validate each watchlist entry for tradeability this cycle. Pure rule-based; survivors → tradeable_assets, rejects → skip_reasons.
- **rules:**
  - R1: market currently open for the asset type.
  - R2: liquidity — 20-day average daily dollar volume ≥ $10M (stocks); 24h volume ≥ $50M (crypto). **[RATIFIED DT-15.1, 2026-07-04 — as written; v1 floor, slow-loop-tunable]**
  - R3: symbol not already in an open paper position.
  - R4: last quote fresher than 60 minutes.
- **constraints:**
  - C1: completeness — every watchlist entry lands in exactly one of tradeable_assets / skip_reasons.
  - C2: every skip carries the specific failed criterion.
  - C3: zero LLM calls.
- **terminal_outputs:** possibly-empty tradeable set + skip_reasons. An empty tradeable set is valid (cycle ends gracefully at Decision C).
- **escalation:** none.

### A.3 Research `@v1` — application: paper_trader

- **mandate:** Build a research bundle per tradeable asset: news, OHLCV, locally computed indicators (RSI, SMA crossover, volume trend), one keyword-extraction call (Groq), one narrative-summary call (Gemini).
- **rules:**
  - R1: per-asset fan-out; a single source failure contributes nothing, others continue.
  - R2: any per-asset failure → empty bundle + skip_reason; never a cycle abort.
  - R3: budget exhaustion mid-fan-out → remaining assets skipped with reason "budget exhausted".
  - R4: failed narrative summary → degrade to sentiment-only bundle (declared honest degradation; never fabricate).
- **constraints:**
  - C1: call budget — at most 1 Groq + 1 Gemini call per asset (checkable against invocation counters).
  - C2: completeness — every tradeable asset ends with a bundle or a skip_reason.
  - C3: bundles with no narrative are marked sentiment-only, never synthesized.
- **terminal_outputs:** research_bundles (some possibly empty/degraded) + skip_reasons.
- **escalation:** none (LLM calls here are content generation, not uncovered-case decisions).
- **Deliberately config, not skill:** semaphore bounds (yfinance 2; Finnhub/CoinGecko 4) — politeness limits, not decision rules (G1 test); frozen into the trace for replay.

### A.4 Execute `@v1` — application: paper_trader

- **mandate:** Convert actionable Views into simulated trades under the declared risk rules; symmetric logging of every decision. Zero LLM calls.
- **rules (the dissolved risk_gates.toml — every value is skill content):**
  - Sizing: fractional Kelly 0.25; max position 5% of portfolio; min notional $100.
  - Exposure: max total exposure 60% of portfolio; max 3 same-sector positions; max 10 open positions.
  - Loss halt: no new trades if daily simulated loss > 5%.
  - Execution gates: require confidence ≥ 0.55 **[RULED DT-15.2, 2026-07-04 — KEEP; two independently-ownable floors (higher binds), NOT redundancy. Annotation frozen into Execute @v1, see §11. Firing is officer-observable: upstream threshold dropped below 0.55]**; require expected magnitude ≥ 0.5%.
  - Idempotency: before writing a trade, check trade_decisions for this prediction_id (crash-recovery double-write guard).
- **constraints:**
  - C1: no executed trade in breach of any declared cap (the officer's highest-value predicate).
  - C2: symmetric logging — every View receives exactly one trade_decision; every skip carries risk_reason.
  - C3: zero LLM calls.
  - C4: writes only through the declared write-set.
- **terminal_outputs:** trade_decisions (executed=false with risk_reason is a fully valid outcome) + new_paper_trades.
- **escalation:** none.

### A.5 PostMortem `@v1` — application: paper_trader

- **mandate:** Score settled trades and update the portfolio. Measures outcomes; **never reacts to them** — behavioral consequences of outcomes flow exclusively through the ledger-and-gate path (this sentence is the standing §0.4 line).
- **rules:**
  - R1: per settlement — score hit/miss against the View's direction; compute P&L and magnitude error.
  - R2: update portfolio (cash + open positions) on close.
  - R3: bias tags via batched Groq call (~1 call per 4 settlements).
- **constraints:**
  - C1: completeness — every settled trade gets a post-mortem row.
  - C2: required fields always present (hit/miss, P&L, magnitude error).
  - C3: bias_tags nullable — a failed tagging call yields null (compliant); an invented tag is a divergence.
  - C4: write-set is the app db only — never Store B.
- **terminal_outputs:** new_post_mortems (empty when nothing settled — valid) + portfolio update.
- **escalation:** none (bias tagging is content generation, not an uncovered-case decision).

---

## 11. Ruling record — DT-15.1 / DT-15.2 (Gate 7)

**Ruled 2026-07-04.** Both items move from PENDING to ratified. These become frozen
`@v1` skill content in DT-15.3; changing either later is a gated fork, not an edit.
Numbers are a **defensible floor**, not an optimum — the slow loop tunes them on evidence.

### DT-15.1 (I-11) — Filter R2 liquidity floor — RATIFIED AS WRITTEN
- **Ruling:** 20-day average daily dollar volume ≥ $10M (stocks); 24h volume ≥ $50M
  (crypto). v1 floor, slow-loop-tunable.
- **Basis:** At paper-trade sizes (max 5% position, $100 min notional) this is not a
  fill/slippage gate — it is a **data-meaningfulness** screen: exclude thin, noisy,
  manipulation-prone names so Predict forecasts on real signal. $10M ADV is a
  conservative-to-generous floor; $50M/24h is a low bar (crypto 24h volume is
  wash-inflated) that screens obvious micro-tokens only.
- **Ratified against actual watchlist:** the sole defined universe is the 50-name set
  in `paper_trader/backtest/universe.py` — 40 large-caps + 10 mid-caps
  (ROKU/SNAP/PINS/ETSY/BYND/PTON/RBLX/SOFI/AFRM/OPEN); **no live crypto** (pycoingecko
  is a dependency; no client/universe exists). R2 is dormant across the large-caps and
  the crypto branch; it can only ever bite the thinnest mid-caps (BYND, PTON, OPEN,
  ETSY, AFRM) in quiet periods. Specified-but-mostly-dormant — the intended posture.

### DT-15.2 (I-12) — Execute's shadowed confidence gate — KEEP (two independent floors)
- **Ruling:** Keep the ≥ 0.55 gate. It is NOT redundancy with Predict's ≥ 0.60 (I-10):
  Predict's 0.60 is an **epistemic** threshold ("is the forecast good enough to be a
  View at all"); Execute's 0.55 is a **risk** threshold ("confident enough to risk
  capital"). Two distinct decisions the membrane keeps separately ownable; collapsing
  them would fuse "should I forecast" with "should I trade" so a later fork lowering
  Predict's threshold would silently move the trading threshold with it. The higher
  floor binds; each is re-tunable via its own gated fork. Execute's gate firing is an
  officer-observable signal (Wave 4 predicate) that the upstream threshold dropped
  below 0.55.
- **Annotation frozen into Execute `@v1` (VERBATIM — DT-15.3 authors this exactly):**

  > confidence ≥ 0.55 — Execute's independent risk-to-act floor. Currently shadowed by
  > Predict's forecast-quality threshold of 0.60 (I-10): every View reaching Execute
  > already clears 0.60, so this gate does not bind under @v1. Retained deliberately,
  > not as redundancy — Predict's 0.60 answers "is the forecast good enough to be a
  > View at all," Execute's 0.55 answers "is it confident enough to risk capital on,"
  > two decisions the membrane keeps separately ownable. The higher of the two floors
  > binds; either is re-tunable via its own gated fork. Execute's gate firing is an
  > officer-observable signal that the upstream threshold has dropped below 0.55.

### Wave 2 preconditions & carry-forwards (recorded, NOT yet built)
1. **Pin the canonical content-hash function BEFORE DT-15.3 writes any row.** One
   algorithm + one serialization, in the framework; the skill-version writer must
   **compute-and-store** the hash itself rather than trust a caller-supplied value
   (closes the Wave-1 deviation-4 window where stored hash and stored content could
   disagree). Hashing a serialized blob is content-agnostic — no storage-neutrality
   violation. Replay (DT-13.2) is the first consumer of hash *verification*; hash
   *computation* belongs at insert. This is Wave 2's opening move.
2. **Wire the three governance-store paths into config** (Store A / Store B / skill
   registry) — none are in `.env` yet (only PAPER_TRADER_DB_PATH / CHECKPOINTER_DB_PATH).
   First thing Wave 3 emission needs before anything can open Store A. App-layer.
3. **Branch-review spot-check:** confirm Store B `ledger_entries` present columns
   (entry_id, cycle_id, invocation_id, observed_at, author, subject, observation_type,
   evidence) against spec §5.3, not just the defining absences.

**Wave 2 batch order (once this branch is reviewed/merged):** pin canonical content-hash
→ DT-10.2 loader (materialize pinned content read-only, verify hash) → DT-15.3 (author
five `@v1` YAMLs verbatim from Appendix A; insert as hash-stamped `@v1` rows,
`origin: initial-authoring`) → DT-9.1 (delete `risk_gates.toml` + Filter inline
thresholds) → DT-9.2 (verify freeze coverage).

---

**End of `STEWARD_PAPER_TRADER_RECONCILE_001`.**
