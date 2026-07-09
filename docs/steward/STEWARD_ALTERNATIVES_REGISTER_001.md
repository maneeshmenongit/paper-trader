# STEWARD_ALTERNATIVES_REGISTER_001

**Status:** Living register (not frozen — this document is meant to be appended to)
**Purpose:** Record external technologies evaluated against Steward / paper-trader, with a verdict and a concrete re-evaluation trigger for each. This is the project's "evaluate alternatives and keep improving" practice made durable: instead of re-litigating "should we use X?" from memory in each thread, an option is assessed once, the verdict and its trigger are written down, and the option is only reopened when its trigger fires.
**How to use:** Each entry has the same shape — what it is, which Steward component it touches, the verdict, and the trigger that would reopen it. Verdicts are one of: **DEFER** (good fit, no current need), **ADOPT-CANDIDATE** (evaluate as a component implementation at build time), **STUDY** (prior art worth reading, not adopting), **REJECT** (philosophically or practically incompatible).
**Date opened:** June 2026

---

## 0. The evaluation discipline (why this register exists)

The project's core gate applies to external tools exactly as it applies to internal features: **no adoption without a concrete paper-trader need that the current stack can't serve.** "It's impressive" / "the market is moving to it" / "it would feel more modern" are not needs. An option earns adoption only when a named, demonstrated need pulls it in. This register exists so that judgment is recorded once and held, rather than re-argued under the pull of novelty.

A second principle, learned from the governance-tooling survey: **adopting a framework means inheriting its philosophy.** A tool whose default behavior contradicts a Steward invariant is not neutral infrastructure — using it means continuously suppressing its natural behavior to preserve the invariant. That cost is real and counts against adoption even when the feature list looks attractive.

---

## 1. Execution substrate

### 1.1 Google ADK (Agent Development Kit) — VERDICT: DEFER (phase 4+ substrate candidate)

**What it is (as of mid-2026).** ADK 2.0 is a GA, production-grade agent execution framework from Google. Its Workflow Runtime is a graph-based engine with routing, fan-out/fan-in, loops, retry, state management, dynamic nodes, human-in-the-loop, and nested workflows. It has OpenTelemetry-native tracing, partner integrations for session replay, built-in evaluation (groundedness/factuality/safety/trajectory), a SkillToolset using the agentskills.io `SKILL.md` spec (the same format as Claude Code), and deploy-anywhere with strong gravitational pull toward Google Cloud / Vertex. Multi-language (Python, TS, Go, Java, Kotlin).

**Steward component it touches.** Execution substrate (§4.5 of the framework spec) — i.e. the role LangGraph + SQLite currently plays. Also adjacent to the orchestrator (Workflow Runtime), skill files (SkillToolset), and reconstructive replay (OTel tracing).

**Why DEFER, not adopt.**
- **No current need.** The substrate (LangGraph + SQLite, router, seams, two-DB, write-auth) is already validated from oracle-agents. ADK offers more primitives (first-class retry, HITL, nested workflows) but paper-trader v1 does not yet need them. Swapping a validated substrate for unneeded primitives violates conservative-sequencing (validated-before-novel).
- **It does not solve the governance problem.** ADK's entire governance contribution is the *acting* layer done well. The membrane, the one-way ledger, the officer, the proposal lifecycle, the enforced human gate — all net-new in ADK too. ADK is strong exactly where Steward is already designed, and silent exactly where Steward's unsolved work lives.
- **Its flagship skill feature contradicts a core invariant.** ADK's SkillToolset lets agents *generate new skills at runtime*, with human review framed as a recommended *best practice*. In Steward the human gate is a structural invariant, not a recommendation. Adopting ADK's skill machinery would mean fighting its default to preserve the membrane.
- **Coupling and churn costs.** Google Cloud/Vertex pull; heavier dependency surface; ADK 2.0 already shipped breaking changes to the agent API, event model, and session schema. The deploy-anywhere story is real but value concentrates on GCP.

**What would make it genuinely useful (the re-evaluation trigger).** Reopen ADK evaluation **at the phase-4 build-handoff stage IF AND ONLY IF** LangGraph proves insufficient for a concrete, demonstrated need — specifically one of: (a) hand-rolled orchestration retry/HITL/nested-workflow logic becomes a maintenance burden that ADK's first-class primitives would remove; (b) the reconstructive-replay recording layer needs a standards-based backing and OpenTelemetry spans are the chosen mechanism; or (c) `SKILL.md` interop across Claude Code and the runtime becomes valuable enough to justify the format. Even then, ADK enters as a **substrate Steward runs on**, never as a governance layer — it cannot displace Steward's reason to exist. Judge it then, against the named need, like any other deferred item.

**Sourcing caveat.** Several capability claims come from vendor and enthusiast write-ups; treat exact feature boundaries as "verify at evaluation time." The governance-philosophy gap is structural and well-sourced.

---

## 2. Governance tooling — the alternatives survey

**Framing finding.** The "agent governance" market splits into two distinct problems:
- **Action governance** (mature, well-served): should this agent perform *this action right now*? Policy-before-action, tool-access control, approval-for-destructive-ops, tamper-evident audit. Steward already has the relevant piece of this (per-agent write authorization); the rest is largely orthogonal to Steward's purpose.
- **Evolution governance** (emerging, thin): how does agent *behavior change over time*, through versioned, human-gated, audited skill changes? **This is Steward's actual problem.** It is less served, but not empty — there are now direct conceptual cousins.

**Strategic conclusion.** Steward is not unprecedented; the market is converging on evolution governance, which validates the problem. But Steward's specific bet — a **one-way membrane** (evidence never drives automatic action) plus a **structurally non-optional human gate** — is differentiated. The self-evolving camp removes governance; the closest product makes it optional; Steward makes it structural. The niche is real and currently under-occupied.

### 2.1 EvoMap Evolver / Genome Evolution Protocol (GEP) — VERDICT: STUDY (closest cousin; do not adopt)

**What it is.** "Version control, but for agent evolution." Constrains every behavioral change through structured assets (reusable improvement patterns, bundled changes, an Events audit-trail log). Scans agent logs for patterns, generates a structured evolution proposal, and offers three involvement levels: fully autonomous / review-mode (approve each change) / strategy presets.

**Steward component it touches.** The entire slow loop — officer (log scanning → pattern detection), proposal generation, human gate (review-mode), versioned change with audit trail.

**Why STUDY, not adopt.** It is the closest existing analog to Steward's slow loop and is worth reading carefully for how it structures changes (Genes/Capsules) and its audit model. **But its governance is a configurable mode** — it supports a fully-autonomous loop with no human gate, i.e. the membrane can be switched off. Adopting it would mean inheriting "governance is optional," which is the exact inversion of Steward's thesis. Steward's differentiation *is* that the gate is structural. Study its mechanics; do not inherit its philosophy.

**Re-evaluation trigger.** If EvoMap ever ships a mode where the human gate and one-way evidence channel are structurally enforced (not optional), re-evaluate as a possible reference implementation. Until then it is prior art only.

### 2.1a EvoMap / GEP deep-dive — VERDICT: DEFERRED STUDY (scheduled, not yet due)

**What this is.** A focused study of EvoMap's Genome Evolution Protocol mechanics, distinct from the survey-level entry in §2.1. Scope: (a) how Genes and Capsules actually structure a single behavioral change, compared with Steward's `proposed_change` + `evidence_refs`; (b) how EvoMap's Events log compares to Steward's append-only ledger — specifically whether Events is a true one-way membrane or a read-and-react channel; (c) where EvoMap's optional-gate design would leak if its patterns were borrowed into Steward, so any borrowed pattern is imported without its philosophy; (d) whether any GEP sub-pattern is worth proposing as a recorded Steward spec amendment.

**Steward component it touches.** The concrete design of paper-trader's skill files and the slow-loop mechanics (proposal structure, evidence channel, audit trail).

**Why DEFERRED, not done now.** Studying EvoMap in the abstract — before Phase 3 reconciliation has surfaced what paper-trader's skill files and slow loop concretely need — is researching ahead of the need, the same anti-pattern as building ahead of comprehension. The study is far more useful once there are real, specific questions to test EvoMap's patterns against. Phase 3 generates those questions; this study answers them.

**Re-evaluation trigger (when to actually do it).** After Phase 3 reconciliation produces concrete skill-evolution questions — i.e. once the paper-trader skill-file design and the slow-loop schema are specified enough to ask "would EvoMap's Gene/Capsule structure improve this specific thing?" At that point, run the deep-dive against those named questions and record any genuine improvement as a Steward spec amendment (never a silent bend). Tentatively "Phase 3.5," but trigger is the questions existing, not a calendar point.

### 2.2 "Governed Capability Evolution" (academic, arXiv 2604.08059) — VERDICT: STUDY (prior art for v2 rollback/stabilization)

**What it is.** Formalizes governed capability evolution: every new capability version is a *governed deployment candidate*, not an immediately executable replacement, with compatibility checking and runtime rollback.

**Steward component it touches.** The proposal lifecycle's approved→version-fork→stabilization-window path (§8 of the spec), and specifically the rollback/stabilization machinery that is currently schema-stubbed in v1.

**Why STUDY.** This is the academic formalization of exactly Steward's "approved proposal forks a new version that enters a stabilization window." It addresses sub-problems Steward has deferred — compatibility checking between versions, runtime rollback guarantees. Read it before designing the v2 validation half (stabilization window + three-signal evaluation), as it may have solved problems that will otherwise be discovered the hard way.

**Re-evaluation trigger.** When the v1 stabilization-window stub is switched on (i.e. when paper-trader generates sufficient settled-trade volume), revisit this paper for its rollback and compatibility-checking patterns.

### 2.3 CHANGE framework / behavioral-drift research (academic, arXiv 2601.06456) — VERDICT: STUDY (informs officer + drift detection)

**What it is.** Argues architectures must include mechanisms to evaluate alignment between an agent's evolving behavior and system objectives, measuring behavioral drift over time (with named capabilities: Harmonize, Anticipate, Negotiate).

**Steward component it touches.** The correction officer's divergence-detection role, and the long-term "silent drift" concern (a correction that succeeded in one regime quietly becoming wrong later).

**Why STUDY.** Directly relevant to the officer's narrow skill-divergence criterion and to the drift problem discussed in the framework walkthrough (the system won't self-flag drift; it relies on the officer re-observing and the human re-evaluating). This research may offer concrete drift-detection signals worth considering when the officer's observation logic is built.

**Re-evaluation trigger.** When the officer's observation/divergence logic moves from spec to build, review for drift-detection techniques.

### 2.4 HumanLayer — VERDICT: ADOPT-CANDIDATE (human gate implementation)

**What it is.** An SDK for human-in-the-loop workflows: wraps actions with approval gates, audit trails, and escalation paths.

**Steward component it touches.** The human gate in the proposal lifecycle (PROPOSED → APPROVED/REJECTED) and the complexity-weighted deliberation (light ack vs. heavy explicit ruling).

**Why ADOPT-CANDIDATE.** It is a near-exact fit for the human-gate mechanics that Steward would otherwise hand-roll: approval, escalation, and an audit trail of decisions. It does not impose an evolution philosophy (it is action/approval plumbing), so adopting it does not threaten the membrane.

**Re-evaluation trigger.** At phase-4 build, when implementing the proposal human gate: evaluate HumanLayer against a hand-rolled gate. Adopt if it reduces build effort without constraining the proposal-record schema.

### 2.5 Cryptographic / Merkle-chained audit (Microsoft AGT Merkle chains; signature-chain tools) — VERDICT: ADOPT-CANDIDATE (ledger integrity upgrade)

**What it is.** Tamper-evident audit trails where each entry is cryptographically chained to the previous one (Merkle chains in Microsoft AGT; post-quantum signature chains in other tools).

**Steward component it touches.** The append-only ledger (Store B). Currently the spec enforces append-only at the *app layer* (INSERT-only, optional trigger). Cryptographic chaining would make the ledger genuinely tamper-evident, not merely convention-enforced.

**Why ADOPT-CANDIDATE.** This is a real improvement over the specced approach. For a governance ledger whose entire value is being a trustworthy evidence record, tamper-evidence is a meaningful upgrade. It is additive — it strengthens an invariant rather than altering behavior.

**Re-evaluation trigger.** When the ledger (Store B) is built: evaluate cryptographic chaining as the integrity mechanism. Decide based on whether the threat model (who could tamper, and why it matters for paper-trader specifically) justifies the added complexity. For a single-operator paper-trader, app-layer enforcement may suffice; note the option exists for when/if the trust model widens.

### 2.6 OPA / Cedar (policy-as-code) — VERDICT: ADOPT-CANDIDATE (invariant enforcement)

**What it is.** Mature policy-as-code engines (Open Policy Agent; Cedar). Declarative rules evaluated against actions/state.

**Steward component it touches.** Membrane invariant enforcement and per-agent write authorization (§4.2). Could express invariants like "no ledger entry carries an action field" or "agent X may only write fields Y" as declarative, testable policy rather than imperative app-layer checks.

**Why ADOPT-CANDIDATE.** Turns app-layer conventions into enforced, auditable policy. Mature and framework-agnostic. Worth evaluating if the write-authorization and membrane invariants grow complex enough that declarative policy is cleaner than scattered imperative checks.

**Re-evaluation trigger.** If/when invariant-enforcement logic becomes complex enough that hand-coded checks are hard to audit, evaluate OPA/Cedar. For v1's small invariant set, hand-coded may be simpler; reopen if the invariant set grows.

### 2.7 Langfuse (open-source LLM observability) — VERDICT: ADOPT-CANDIDATE (reconstructive-replay trace backing)

**What it is.** Open-source LLM engineering/observability platform (tracing, session capture).

**Steward component it touches.** The execution trace (Store A) and reconstructive replay (§3, §5) — capturing the frozen `orchestrator_input` / `orchestrator_decision` / `agent_output` facts.

**Why ADOPT-CANDIDATE.** Reconstructive replay requires faithfully recording every non-deterministic decision as an immutable fact. A mature observability/tracing layer is a candidate backing for that, versus hand-rolling trace storage. (ADK's OTel tracing is the in-substrate alternative if ADK is ever adopted.)

**Re-evaluation trigger.** When Store A and the replay layer are built: evaluate Langfuse (or OTel-based tracing) against hand-rolled SQLite trace storage. Adopt if it provides faithful frozen-fact capture without imposing schema constraints that conflict with the cycle-record fields.

### 2.8 Self-evolving agent frameworks (DGM-Hyperagents, OpenSpace, autoresearch) — VERDICT: REJECT (anti-pattern; useful only as contrast)

**What they are.** Frameworks that maximize autonomous self-improvement. DGM-Hyperagents make the meta-modification procedure itself editable (recursive self-modification). OpenSpace auto-captures and reuses skills from completed tasks via local SQLite.

**Steward component it touches.** The slow loop — but as its negation.

**Why REJECT.** These are the direct inversion of Steward's thesis: they remove the membrane and the human gate to maximize autonomy, including recursive self-modification — the single thing Steward most forbids. They are valuable only as the contrast that defines Steward's edges ("this is what we refuse to be"). Not adoptable without abandoning the project's reason to exist.

**Re-evaluation trigger.** None. Permanent reject on philosophical grounds. (Listed so the rejection is recorded and not re-debated.)

---

## 3. Summary table

| Option | Layer | Verdict | Trigger to reopen |
|---|---|---|---|
| Google ADK | Execution substrate | DEFER | Phase-4 build, only if LangGraph proves insufficient for a named need |
| EvoMap / GEP | Evolution governance | STUDY | If it ships a structurally-enforced (non-optional) gate mode |
| EvoMap / GEP deep-dive | Skill-file + slow-loop design | DEFERRED STUDY | After Phase 3 surfaces concrete skill-evolution questions ("Phase 3.5") |
| Governed Capability Evolution (paper) | Stabilization/rollback | STUDY | When the v1 stabilization-window stub is switched on |
| CHANGE / drift research | Officer / drift | STUDY | When officer observation logic moves to build |
| HumanLayer | Human gate | ADOPT-CANDIDATE | Phase-4, when building the proposal gate |
| Merkle/crypto audit | Ledger integrity | ADOPT-CANDIDATE | When Store B is built, if threat model justifies |
| OPA / Cedar | Invariant enforcement | ADOPT-CANDIDATE | If invariant set grows beyond simple hand-coded checks |
| Langfuse / OTel | Replay trace (Store A) | ADOPT-CANDIDATE | When Store A / replay layer is built |
| Self-evolving frameworks | Slow loop (negation) | REJECT | None — permanent, philosophical |

---

## 4. The meta-point (how this register keeps the product improving)

Steward's governance *core* is build-our-own, because the membrane (one-way evidence) plus the structurally-non-optional human gate is the novel, differentiating bet — and the closest market option (EvoMap) inverts exactly that bet by making governance optional. But "build the core" does not mean "hand-roll every component." Several individual Steward components have mature external implementations (human gate → HumanLayer; ledger integrity → crypto-chaining; trace → Langfuse/OTel; invariant enforcement → OPA/Cedar) that should be evaluated at build time, each against a named need. And the academic prior art (governed capability evolution; behavioral drift) likely solves v2 sub-problems before they are hit.

The practice this register encodes: survey the market when a relevant decision approaches, record the verdict and its trigger once, hold the line against novelty-pull, and reopen only when a named need fires the trigger. That is how the project evaluates alternatives without either ossifying (never reconsidering) or thrashing (re-litigating every thread).
