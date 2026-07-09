# Routing Design Audit — Findings (against the code)

**Audits:** `STEWARD_ROUTING_DESIGN_AUDIT_001` (the design map).
**Date:** 2026-07-09 · **Scope:** verify the audit's four-question map + three gaps against
the actual code; no fixes applied (this is the audit, not the change). Findings are the
basis for the DT-16/17/18 spec decisions the human owns.

**Headline:** the audit's *structure and its three proposed gaps are correct and confirmed
in code.* One diagnosis in the audit is wrong and I'm correcting it — and doing so makes
the underlying finding **stronger**, not weaker.

---

## Correction to the audit's trigger diagnosis (important)

The audit says the `max($2,110.90, $2,110.90) = $556.75` mislabel was "an LLM narrating
numbers Python already computed." **That is not what happened.** The reporting seam has
**zero LLM** — `stage1_gate_report.py` only formats pre-computed `Stage1Report` fields
(verified: no `router`/`.call`/`complete` anywhere in the report writers). No model touched
those numbers.

**The real cause is a deterministic Python bug I introduced** in `stage1_harness.py`: the
report **mixes two point-sets in one table.** When sampling:
- `floor_momentum_pnl` and `null_pnl` are stored as **full-universe** ($2,110.90 each),
- but `effective_floor_pnl` ($556.75) and `llm_pnl` ($255.58) are the **sampled-subset**
  (600 points) values.

So the gate line "Effective floor = max(momentum $2,110.90, null $2,110.90) = $556.75" is
arithmetically impossible on its face, and the dollar table invites a reader to compare a
**sampled** LLM ($255) against a **full-universe** floor ($2,110) — the exact
apples-to-oranges error the sampled-sums were built to prevent, applied to the verdict but
**not** to the display.

**Why this makes the audit's point stronger:** the fix the audit proposes (Gap 1 —
deterministic, self-consistent reporting) is *more* justified once you see the defect is
not "a model wandered into reporting" but "the deterministic reporting layer is internally
inconsistent about which population its numbers describe." The rule to adopt isn't only
"no LLM in reporting" (already true) — it's **"every number in a report is labeled with the
population it was computed over, and a single table never mixes populations."**

**The verdict itself is unaffected.** The FAILED verdict uses the sampled subset
consistently on both sides (`v_floor`, `v_null`, `llm_pnl` all over the same 600 points →
edge −0.30%). Only the *display* is inconsistent. So: real reporting bug, correct verdict.

---

## Q1–Q4: the map, verified against code

| # | Audit claim | Verified? | Note |
|---|---|---|---|
| Q1 | Tool routing solid/static; leak is the reporting seam | **Yes, with the correction above** | Reporting is deterministic (good) but population-inconsistent (the real leak). |
| Q2 | R1–R4 + C1 + deterministic PostMortem = the spine | **Confirmed** | `agents/predict.py` R1–R4 intact; `analytics/*` extraction made PostMortem deterministic (Stage 0). The spine is sound. |
| Q3 | Tiered router exists; purpose→tier map is ad-hoc | **Confirmed** | `REASONING_PURPOSES = {"predict_selection","reasoning"}` and `fast_purposes = [3 items]` are two hardcoded lists in two files — not one reviewed table. |
| Q4 | Reasoning tier wired but under-covered; silent downgrade | **Confirmed — both** | Only `predict_selection` is mapped; officer/proposer unmapped. And degrade is **silent** (below). |

**Q4 silent-downgrade — confirmed mechanism.** `build_tiered_router` builds
`reasoning_chain = [reasoning_lead, *fast_chain]`; `ConfigurableLLMRouter.call` fails over
on error to the next client and returns only `(text, tokens)` — it never reports *which*
client served the call. `LLMSelector` records the pick but not the serving model. So when
the reasoning tier dies (Stage 1: Groq quota → local 7B), **nothing in the record marks the
output as degraded.** The 7B caveat in the Stage 1 report exists only because I noticed it
by hand, not because the system flagged it. This is exactly Gap 2.

---

## The three gaps — all confirmed, all with demonstrated Stage-1 need

1. **DT-16 (candidate) — Reporting is deterministic AND population-labeled.** Numbers come
   from code (already true), and — the sharper rule this audit surfaces — every figure
   carries the population it was computed over; one table never mixes full-universe and
   sampled values. *Demonstrated by:* the $556.75 / $2,110-vs-$255 mislabel.
2. **DT-17 (candidate) — Tier-unavailability is a flagged degradation, not a silent
   downgrade.** When a purpose's desired tier is unavailable, the router degrades *and marks
   the output degraded* (or halts) — a verdict run on a weaker model can never read as if it
   ran on the intended one. *Demonstrated by:* the 7B silent-downgrade in Stage 1.
3. **DT-18 (candidate) — Complete + ratify the purpose→tier map before Stage 2/3.** One
   reviewed table of mechanical/fast vs judgment/reasoning purposes, including the
   **correction officer and proposer** (judgment-heavy, coming online at Stage 2/3), and
   ratify the mid-stage tier-router capability into the register. *Demonstrated by:* only
   one purpose mapped today; Stage 2/3 adds unmapped judgment-heavy work.

---

## What the audit correctly rules OUT (I concur)

- **No auto-learned routing** — routing is human-designed; skills are what the framework
  learns within gates. Keep the boxes separate. (The code honors this: tiers are config,
  not learned.)
- **No new routing subsystem** — R1–R4 + the tiered router already cover Q2–Q4; the gaps
  are consistency + coverage + honesty-on-degrade, not a missing brain.
- **No mid-experiment re-architecture** — the three gaps are seam-level rules, small, and
  due before Stage 2/3 regardless.

---

## Recommended sequencing (for the human gate)

- **DT-16 fold into cleanup now** — the reporting population-mix is a live correctness bug
  in `stage1_harness.py`'s report construction; fix it as a small bounded change (and add a
  test that a sampled run's table is self-consistent). Low risk, high clarity.
- **DT-17 + DT-18 before Stage 2/3** — both are small and the officer/proposer tier mapping
  is genuinely needed the moment Stage 2 brings judgment-heavy governance online. Ratify the
  tier-router capability (built mid-Stage-1 as a deviation) into the register at the same
  time.

**Bottom line:** the audit is right — small seam rules, not a subsystem. The one change is
that the trigger defect is a deterministic reporting inconsistency (not LLM narration),
which strengthens Gap 1 and gives it a concrete, testable fix. No code changed in this
audit task.
