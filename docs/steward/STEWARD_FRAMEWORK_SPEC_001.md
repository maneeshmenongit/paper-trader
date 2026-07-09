# STEWARD_FRAMEWORK_SPEC_001

**Status:** Phase 2 — Framework Specification (v1)
**Scope:** The Steward framework only. Application-agnostic. No paper-trader domain detail (that is Phase 3).
**Purpose of this document:** To be the authoritative reference Claude Code and future-you build from, *and* to hold the v1 scope line. Every component states the invariant it must never violate; every deferral names the concrete need that is currently absent. The spec is a decision record as much as a design — when momentum later says "add this," the recorded rationale is what says no.

---

## 0. How to read this document

Each component section has three parts: **what it is**, **its fields/states**, and **its invariant** — the property that, if violated, breaks the framework. The invariants are the load-bearing content. If an implementation choice satisfies the fields but violates the invariant, the implementation is wrong.

The v1/v2 line in §9 is not a feature table. Each deferred item names *the specific need that does not yet exist*. That is the falsifiable test for un-deferring it: the item returns to scope when, and only when, that named need appears.

---

## 1. The thesis (the whole design in one sentence)

Steward is a multi-agent system where **acting** and **changing how you act** are two separate loops running at two different speeds, connected by an append-only record that the fast loop can write to but can never read-and-react-to automatically.

Everything below is mechanism for keeping those two things separate. The moment an agent observes a correction and immediately rewrites its own behavior, governance is lost and the system is an unauditable black box. The entire framework exists to prevent that fusion.

---

## 2. The spine — two loops and a one-way membrane

### 2.1 The fast loop (execution)
Runs every cycle. The orchestrator decides the cycle's shape; agents act by reading their skill files; the correction officer (observer half) writes evidence to the ledger. **Nothing in this loop modifies any skill.** The fast loop produces behavior and produces evidence — nothing else.

### 2.2 The slow loop (evolution)
Runs on a slow cadence (weeks, not cycles). The correction officer (proposer half) reads accumulated ledger evidence and authors a proposal to change a skill. A human gates it. If approved, a new skill version is forked. (The validation half — stabilization window + outcome evaluation — is schema-complete but verdict-stubbed in v1; see §6 and §9.)

### 2.3 The membrane (the correction ledger)
The single most important structural element. The ledger is a **one-way valve** between the loops:
- The fast loop **writes** evidence to it.
- The slow loop **reads** evidence from it.
- The fast loop **never reads it to decide what to do next.**
- The ledger **never triggers an action on its own.**

**INVARIANT (membrane):** No ledger entry carries an action, recommendation, or trigger. Evidence flows inward and is acted on only through the human-gated slow loop. Any feature that makes the fast loop react to the ledger collapses the membrane and is forbidden in v1 regardless of how useful it seems.

### 2.4 What makes this *governance-aware* rather than merely *adaptive*
The speed gap. Adaptive systems collapse observation and change into one beat. Steward forces every behavioral change through a slow, human-gated, audited channel. The gap between "evidence exists" and "behavior changes" is where governance lives.

---

## 3. Replay model (settled first because it dictates the record schemas)

Replay in Steward is **reconstructive, not deterministic.**

- **Deterministic replay** (re-run, get identical output) is **impossible** here, because the orchestrator and agents involve non-deterministic LLM steps. Do not build storage or tests that expect bit-for-bit reproduction.
- **Reconstructive replay** (read a faithful record of what happened and why) is what Steward provides. For any past cycle, reconstruct what the orchestrator saw, what it decided, which agents ran, which skill *versions* they read, what they produced, and what the officer observed.

**INVARIANT (replay):** Every non-deterministic decision is **frozen as an immutable fact at the moment it occurs.** It is never re-derived. Non-determinism is allowed to happen in the fast loop; the *record* of what happened is immutable. If the system ever tries to reproduce or re-derive a past decision, the membrane is breaking.

**Consequence to accept:** Steward can answer "what *did* it do, with what inputs, reading which skill versions, to what outcome." It cannot answer "what *would* it have done differently." For audit and accountability, the former is exactly enough; the latter is out of scope by design.

---

## 4. Components — fast loop

### 4.1 Skill files (procedural memory per agent)
**What:** The "how I do my job" document each agent reads to act. Versioned (see §6).
**Invariant:** An agent's behavior is governed only by its skill file version pinned at invocation time. Skills are changed only through the slow loop's proposal → human-gate → version-fork path — never hand-edited in place without a versioned record.
**Note (emergent property):** Because the officer can only flag *divergence from a skill* (see §4.3), anything you want caught must be *stated explicitly in a skill*. Vague skills produce no evidence. The framework therefore pressures skills toward explicit, declared constraints — which is what a procedural-memory system wants anyway.

### 4.2 Agents (bounded units of capability)
**What:** Each agent is a narrow capability that acts by reading its skill file. Agents are composed by the orchestrator from a fixed roster.
**Invariant:** An agent does one bounded thing and reads exactly one pinned skill version per invocation. Agents cannot modify skills, cannot write to the ledger (only the officer does), and cannot be invented at runtime (see §9 deferral).

### 4.3 Correction officer — observer half (fast loop)
**What:** During a cycle, watches agent behavior against what the agent's own skill specifies, and writes evidence to the ledger when behavior diverges.
**Write criterion (v1, NARROW):** The observer writes an entry only on **divergence from the agent's own skill specification** — a constraint the skill states that the agent did not honor, or an outcome that contradicts what the skill predicts. It does **not** write on a general "anything notable" basis. Narrow is chosen because it is skill-anchored, auditable, and free of officer opinion; it can be widened later *with evidence* (the misses become the case for widening), whereas a broad criterion can only be walked back after the ledger is already polluted.
**Invariant:** The observer's sole output is neutral ledger evidence. It writes as if no proposer exists — observation is never shaped by a proposal the officer is planning. Contaminating observation with proposal intent poisons the evidence at its source. (Structural enforcement: see §7.)

### 4.4 Orchestrator (rules-first with LLM fallback)
**What:** Each cycle, decides the cycle's shape — which agents run, in what arrangement — choosing from the **fixed agent roster.**
**Design (v1):** **Rules-first.** A rule-based sequencer handles every cycle its rules cover (conditional shape: "if open positions, run exit-evaluation"; "if market closed, skip construction" — all writable as `if`). An **LLM fallback slot** exists for situations no rule covers (genuine judgment: a holistic read of the whole situation with no single writable trigger). In v1, build the slot and the escalation seam; the LLM fallback **activates only when a real "no rule covered this" case appears.**
**Decision tagging:** Every orchestrator decision is recorded as **rule-made vs. LLM-made.** This makes the split auditable and — critically — makes LLM escalations *observable by the officer*.
**Convergence path (LLM decisions hardening into rules):** Runs the long way around, never via self-observation. Officer observes the escalation → ledger records it as evidence → proposer spots the recurring pattern → human gate approves a new rule → it ships versioned and replayable. Next time the situation occurs, the rule handles it.
**Invariant:** The orchestrator composes only from the fixed roster, decides only from the current situation snapshot (it is stateless across cycles in v1 — no decision memory; see §9), and **never observes or modifies its own past decisions to self-codify rules.** Self-codification is the membrane breach; rule-creation flows only through the human-gated slow loop.

### 4.5 Execution substrate
**What:** LangGraph + SQLite. Two physically separate SQLite stores (see §5.4).
**Invariant:** The execution-trace store and the ledger store are separate files. The fast-loop writer and slow-loop reader touch different physical stores, reinforcing the membrane.

---

## 5. The membrane — record schemas (fast loop writes)

Two physical stores. **Store A: execution trace** (§5.1–5.2). **Store B: ledger** (§5.3).

### 5.1 Cycle header (one per cycle) — Store A
```
cycle_id               monotonic, ordered (ULID/sequence) — replay needs stable ordering
started_at             timestamp
ended_at               timestamp
trigger                what kicked off this cycle (schedule, event, manual)
orchestrator_input     the situation snapshot the orchestrator saw — FROZEN
orchestrator_decision  the cycle shape chosen (structured), + rule-made|LLM-made tag — FROZEN
orchestrator_rationale decision justification if captured (not raw chain-of-thought)
status                 completed | failed | partial
```
`orchestrator_input` must contain **everything the decision depended on and nothing it didn't**, or reconstructive replay cannot faithfully reconstruct why the shape was chosen.

### 5.2 Agent invocation (one per agent run within a cycle) — Store A
```
invocation_id     unique
cycle_id          FK -> cycle header
agent_name        which bounded unit ran
skill_version_id  THE pinned version (e.g. "trade-construction@v3", hash) — load-bearing
agent_input       what the agent received
agent_output      what it produced — FROZEN
started_at / ended_at
status
```
`skill_version_id` is the most important field in the membrane. It pins the exact version+hash, which is the only thing that lets a past cycle be reconstructed against the skill as it *then* read. This is why versioning (§6) and replay (§3) are the same concern.

### 5.3 Ledger entry (evidence) — Store B (append-only)
```
entry_id          append-only, monotonic
cycle_id          FK -> the cycle that produced the evidence
invocation_id     FK -> specific agent run (nullable)
observed_at       timestamp
author            who wrote it — correction officer (always, in v1)
subject           what it's about: which agent / which skill_version_id
observation_type  category (e.g. constraint-violation, outcome-mismatch)
evidence          the structured observation itself
```
**Absent by design:** no `action`, no `recommendation`, no `severity-that-triggers`. That absence *is* the membrane (§2.3).
`author` is trivial in v1 (always the officer) but load-bearing for provenance: every entry is tagged by authorship at ingest, so the field already carries weight when a second author (or human annotation) appears later.

### 5.4 Two-store separation
Execution trace in Store A, ledger in Store B — separate SQLite files. Append-only is **enforced at the app layer** (INSERT only; no UPDATE/DELETE on the ledger), optionally backed by a trigger that rejects updates. SQLite does not enforce append-only by column type.

---

## 6. Skill versioning, audit, replay

**What:** Every skill is append-only-versioned. A change **forks a new version from a named old one** (`@v3 -> @v4`); the old version is never overwritten.
**Invariant:** A past cycle is always reconstructable against the skill version it actually used. `@v3` remains replayable forever after `@v4` ships, because the agent-invocation pin (§5.2) and the version-fork chain (§8) are the two ends of one thread. Overwriting a skill version breaks replay and is forbidden.

---

## 7. Correction officer — structural separation of its two halves

The officer is the only component touching **both loops** (observer in fast, proposer in slow). It is therefore the single point where the membrane could be breached from inside. Design goal: give it exactly enough power to notice and articulate, and **not one capability more.** Its intelligence is in noticing and articulating — never in deciding.

The two halves must never touch each other within the officer. Three **structural** enforcements (not behavioral hopes):

1. **Time separation.** Observer runs inside cycles (fast loop); proposer runs between cycles (slow cadence). Never simultaneously. They are two invocations at two times.
2. **Ledger is the only channel between them.** Observer's sole output is ledger entries; proposer's sole input is ledger entries (+ current skill versions). No side-channel, no shared scratchpad, no carried officer state. If the proposer needs to know something, it must be a neutrally-written fact in the ledger.
3. **The proposer can only cite, never assert.** A proposal's `evidence_refs` (§8) cannot be empty. The proposer can only articulate patterns already in evidence; it cannot introduce new claims at proposal time.

**INVARIANT (officer):** The dual role is permitted only because these three separations hold. Observation is neutral (no proposal in view); proposal is grounded (cites specific entries); the two halves communicate only through the append-only membrane. Remove any of the three and the officer becomes the unauditable central brain the framework exists to prevent.

**Complexity tagging lives on the proposer, not the observer.** The proposer may tag a proposal's blast radius ("touches one constraint, low" vs. "rewrites sizing, high") as an **attention hint** for the human gate. The tag *watches*; the human's approval *drives*. It never routes around the human (see §8 lifecycle).

---

## 8. Proposal record (slow loop — officer creates, human gates)

This is the first place in Steward where state **moves.** Every transition is either a human gate or an evidence verdict; nothing advances on its own.

```
proposal_id        append-only, monotonic
created_at         timestamp
author             officer (v1)

evidence_refs      FK list -> ledger entry_ids this is built from   (CANNOT be empty)
target_skill       which skill
base_version_id    the EXACT version being changed (e.g. trade-construction@v3)
proposed_change    the additive change (structured, not prose)
rationale          why these evidence entries justify this change

status             lifecycle state (below)
decided_at         when the human ruled
decided_by         the human
decision_note      approve/reject reasoning

window_opened_at   stabilization window start (null until approved)   [v1: recorded, see §9]
window_closes_at   computed gate                                      [v1: recorded, see §9]
new_version_id     the skill version this created, if approved (e.g. @v4)

evaluation         three-signal verdict at window close (null until then) [v1: STUBBED, see §9]
```

### 8.1 Lifecycle
```
PROPOSED        officer created it, cites evidence, awaiting human
  | human approves                         | human rejects
APPROVED                                  REJECTED  (terminal; evidence stays)
  | window opens, new_version ships
IN_WINDOW       stabilization period running, behavior live
  | window closes, three signals evaluated  [v1: stubbed — no verdict claimed]
SUCCEEDED | FAILED | INCONCLUSIVE          (terminal verdicts)

SUPERSEDED      (terminal, OUTSIDE the flow above)
```

### 8.2 Three load-bearing fields
- **`evidence_refs` (anti-floating rule):** A proposal with no cited evidence is illegal by construction. The officer proposes because *these specific ledger facts* say so — never because it "feels" a skill is wrong. This is what stops the evolution loop from becoming the officer's opinion.
- **`base_version_id -> new_version_id` (the chain):** A proposal forks a new version from a named old one; it does not edit in place. This is what keeps March's cycles replayable against `@v3` after `@v4` ships.
- **`status` (gated lifecycle):** Every transition is a human gate or an evidence verdict. Nothing self-advances.

### 8.3 SUPERSEDED — semantics and v1 handling
SUPERSEDED means a proposal was **overtaken** — a *later* proposal changed the same skill region before the first reached a conclusion. It is **always a consequence of a human approving another proposal**, never an autonomous retirement.
- **Distinct from FAILED:** superseded = overtaken (never concluded); failed = evaluated and didn't work. Conflating them corrupts the long-term track record (convergence analysis depends on telling them apart).
- **v1 handling:** Implement the SUPERSEDED *transition* so no proposal ever dangles in an invalid state when two touch one skill close together. Do **not** build elaborate collision-detection machinery — one-proposal-at-a-time keeps it dormant early. Cheap insurance against an invalid state.

### 8.4 Complexity is a gate-weight dial, not a routing switch
Both small and complex proposals pass through the human gate. Complexity decides only *how heavy the deliberation is*:
- **Small/low-risk:** human approves with a lightweight ack. If approving B implicitly retires A, A goes SUPERSEDED as a recorded consequence of the human's approval of B.
- **Complex/high-risk:** the gate is heavier — the human explicitly rules on what happens to A (let it die SUPERSEDED, or let A finish its window before B). A second deliberate, recorded decision.
The officer may *tag* complexity (§7); the human always pulls the trigger. Nothing auto-retires behind the human's back.

---

## 9. The v1 / v2 line — with the absent-need named for each deferral

### 9.1 In v1 (built and used)
- Skill files + agents reading pinned versions (§4.1–4.2)
- Orchestrator as **rules-first sequencer**, LLM-fallback **slot** built but dormant (§4.4)
- Officer **observer** (narrow, skill-divergence criterion) (§4.3)
- Officer **proposer** through `PROPOSED -> APPROVED -> version-fork` (§8)
- Membrane: cycle header, agent invocations with version pins, evidence ledger with no action field; two physical stores (§5)
- Skill versioning with reconstructive replay (§3, §6)
- Proposal lifecycle **schema-complete**, including SUPERSEDED transition (§8)

### 9.2 In v1 (schema-complete but verdict-stubbed)
- **Stabilization window + three-signal evaluation (validation half).**
  **Absent need:** three outcome signals require trade volume that early paper-trader will not produce; evaluating a correction on noise is worse than not evaluating it. The window timestamps are recorded and the lifecycle reaches IN_WINDOW, but `evaluation` claims no verdict until volume justifies it. Switches on when the application produces sufficient settled-trade volume.

### 9.3 Deferred to v2 (each with the need that does not yet exist)
- **LLM-driven dynamic orchestration (beyond the fallback slot).**
  **Absent need:** no demonstrated paper-trader cycle-shape decision that is genuine judgment rather than a writable `if`. Returns to scope when a concrete "no rule can express this" case appears. (The fallback slot already accommodates the *first* such case without promoting the whole component.)
- **Orchestrator decision memory as first-class.**
  **Absent need:** none yet — and it is membrane-adjacent. The moment the orchestrator reads its own decision history to adapt, it creates a fast-loop self-read resembling a membrane breach. Stays deferred until a need exists that cannot be served by the officer→ledger→proposer→gate path.
- **Agent performance memory as first-class.**
  **Absent need:** no paper-trader requirement that an agent adapt from its own tracked performance within the fast loop. Same membrane risk as above.
- **Auto-skill-changes (skill edits without a human gate).**
  **Absent need:** none — and it directly punches through the human gate. Permanently incompatible with the framework's thesis unless the thesis itself is revised. Hardest line to hold; the §2.3 and §8 invariants exist to hold it.
- **Multi-application support.**
  **Absent need:** only one application (paper-trader) exists. Returns to scope when a second real application does.
- **Runtime agent invention (orchestrator conjuring new agents mid-cycle).**
  **Absent need:** none; the fixed roster serves paper-trader. Also required for the orchestrator's decision space to stay bounded and replayable (§4.4).

### 9.4 The test for un-deferring anything
An item leaves v2 only when its named absent-need becomes a **concrete, demonstrated** need pulling from the application — not because the framework "feels incomplete" without it. "Feels incomplete" is precisely the signal this document exists to resist.

---

## 10. Coherence check (why this is one framework, not a pile of special cases)

The same one-way membrane and human gate govern **both** how agents act (skill evolution) and how cycles are shaped (orchestrator rule-creation). A skill divergence and an orchestrator escalation both become ledger evidence, both become proposals, both hit the human gate, both ship as versioned, replayable artifacts. There is no second governance mechanism. That single mechanism, applied uniformly, is what makes Steward a framework — and what makes any given application (paper-trader first) merely a use case sitting on top of it.

---

## 11. Phase handoff

- **Phase 1 (conceptual walkthrough):** complete.
- **Phase 2 (this document):** the framework, specified constraint-first.
- **Phase 3 (next):** paper-trader rewritten as a Steward *application* — domain agents, real data, concrete skill files with declared constraints. This is where the abstract components meet reality and the real implementation challenges surface.
- **Phase 4:** build handoff. (Committed discipline: build begins within three weeks of framework design starting.)

Phases do not overlap. Phase 3 designs the application against this frozen framework; if Phase 3 surfaces a genuine framework gap, that is a deliberate, recorded amendment to this document — not a silent redesign.
