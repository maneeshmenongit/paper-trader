# Stage 1 — Frontier Confirmation · Completion Report

**Branch:** `postv1-stage1-frontier-confirm` (off main)
**Authority:** `STAGE1_FRONTIER_CONFIRM_PROMPT`; `ROUTING_DESIGN_AUDIT_001` Gap 2 (DT-17).
**Model under test:** `claude-sonnet-5` (strong reasoner) vs Stage 1's `qwen2.5:7b`.
**Result:** **INCONCLUSIVE — the 7B caveat is NOT closed, but for an informative reason.**
The frontier model did not *fail* the thesis; it **declined to play**, abstaining on
99.7% of points because it was honestly uncertain. Details below.

---

## The one-line result

Given only price features and three ~coin-flip methods, Claude Sonnet 5's selection
confidence **capped at the C1 floor (0.60) on 598 of 600 points**, so the fixed
enter-iff-confidence≥0.60 rule made it abstain almost everywhere → only **1 settled
point** → below the coverage floor → **INCONCLUSIVE**. This is not a bug and not a
model failure: a strong reasoner correctly refused to fake conviction it didn't have.

---

## The one-variable attestation (§4.1) — clean

- **Prompt hash `2bfae227d9790796` == Stage 1's** — the selection prompt was byte-identical,
  NOT re-tuned (§2.4 honored).
- Same 600 sampled points (same seed), same verdict rule, same effective floor
  (E=3.0%), same adapter, same five sanity checks (all passed). **Only the model changed.**
- Step 0 floor cross-check reconciled to $2,110.90 before any token was spent.

## Per-point model attestation (§4.2, DT-17) — clean

- The live run's `served_models` was exactly **`{claude/claude-sonnet-5}`** — zero silent
  fallbacks. The `AttestingRouter` has no fallback chain: a provider miss HALTS rather
  than downgrading, so this result can never be secretly 7B. This is the audit's DT-17
  guarantee, built and enforced for this run.

## The numbers (same 600 points as the 7B run)

| Strategy | 7B (Stage 1) | Sonnet 5 (this run) |
|---|---:|---:|
| always_momentum (floor) | $2,110.90 | $2,110.90 |
| null_selector (real bar) | $2,110.90 | $2,110.90 |
| **llm_selector** | **$255.58** (382 settled) | **$21.61** (1 settled) |
| oracle_best_method | $88,443.33 | $88,443.33 |

- **Abstention: 99.7%** (vs 2.0% for 7B). Only 1 point cleared the C1 confidence gate.
- Pick distribution *before* the gate (from cache): momentum 301, arima 224,
  mean_reversion 75 — sensible, well-parsed (0 unparseable). Sonnet 5 understood the task.
- **Confidence distribution: min 0.45, max 0.60.** 598/600 below the 0.60 floor.
- Tokens: 283,494 across 600 calls. Cost ≈ $0.60 (Sonnet 5 intro pricing). Served solely
  by Sonnet 5.

## What this means — read honestly, goalposts unmoved

The frontier run was designed to answer: *did Stage 1 fail because the thesis is wrong,
or because the model was a weak 7B?* The answer is **neither of the two clean outcomes** —
it's a third, informative one:

- The strong model **did not lose to the null selector on a body of trades** (7B's
  failure mode). It made almost **no** trades, because it was **not confident enough** to
  under the fixed C1 rule.
- That is arguably the *correct* epistemic behavior: on three coin-flip methods with
  price-features-only context, a well-calibrated reasoner reports low confidence rather
  than manufacturing a pick. The 7B model, by contrast, confidently over-committed (to
  mean_reversion) and lost.
- So the two runs together tell a coherent story: **price-features-only method selection
  lacks a confidently-exploitable signal.** The weak model exploited noise and lost; the
  strong model saw there was nothing to confidently exploit and abstained.

**This does NOT let us declare the NO final** — we don't have the settled-trade
comparison the verdict rule needs. And per §2.4/§5 the C1 threshold was **not** lowered to
force trades: doing so to "rescue a verdict" is the predecessor's failure mode.

## Options for the human (the gate)

1. **Accept the joint signal and stop the thesis phase.** 7B FAILED + frontier-abstains
   is a coherent "weak thesis" pattern. The framework built stays valid and reusable.
2. **Re-run with the C1 floor as a RECORDED, ratified parameter change** (e.g. accept the
   model's own confidence as the sizing signal, or lower the gate) — only as a *logged
   spec amendment*, never a silent tune — if you want the settled-trade head-to-head.
3. **Proceed to Stage 3** to test whether the **news/Research delta** changes the
   confidence picture — the model's abstention was on price features *alone*, which is
   exactly the §2.2 scoping limitation carried from Stage 1.

## Deviations / fixes this task

- **Report three-way-read bug fixed.** The first generated report wrongly printed "Also
  FAILED — the NO is now final" for an INCONCLUSIVE verdict (the `_three_way` logic lacked
  an INCONCLUSIVE branch and fell through to the negative-edge case). Fixed to state the
  honest abstention reading above; report regenerated. **The bug was in the narration, not
  the numbers** — the dollar table and verdict were always correct.
- **New framework capability:** `ClaudeClient` (the framework had no Anthropic client) +
  `anthropic_api_key` config + tier-routing wiring + the `AttestingRouter` (DT-17). All
  reusable for Stage 3.

## Tests / quality
- **555 tests pass.** Ruff + mypy clean on changed files. `anthropic==0.116.0` added.

## Gate
Stage 1 frontier confirmation = **INCONCLUSIVE (caveat not closed; informative abstention).**
Do not open Stage 2. The human decides among the three options above. Branch left for
review + merge.
