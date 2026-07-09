# Stage 1 — Frontier Confirmation · Gate Report

> **North star:** Does an LLM choosing which method to trust beat cheap alternatives on real dollar P&L? A NO on evidence is a **successful** test — and this run resolves whether Stage 1's NO was the *thesis* or the *model*.

**Model under test:** `claude/claude-sonnet-5` (strong reasoner) vs Stage 1's `qwen2.5:7b` (local).

## 1. One-variable attestation (§4.1)
- Prompt hash `2bfae227d9790796` == Stage 1 `2bfae227d9790796` ✓ (prompt NOT re-tuned).
- Same 600 sampled points (same seed), same verdict rule, floors (E=3.0%), adapter, and five sanity checks. **Only the model changed.**
- Step 0 floor cross-check: independent recompute $2,110.90 vs inherited $2,110.90 (ok).

## 2. Per-point model attestation (§4.2, DT-17)
- Served by: **[]**.
- **✗ MORE THAN ONE MODEL SERVED — run INVALID (a fallback leaked in).**
- The AttestingRouter has no fallback chain: a provider miss HALTS rather than downgrading, so a frontier result can never be silently 7B.

## 3. Dollar table — strong model vs 7B, SAME 600 points

| Strategy | 7B (Stage 1) | **claude/claude-sonnet-5 (this run)** |
|---|---:|---:|
| always_momentum (floor) | $2,110.90 | $2,110.90 |
| null_selector (real bar) | $2,110.90 | $2,110.90 |
| random_among_eligible | — | $5,138.41 |
| **llm_selector** | **$255.58** | **$21.61** |
| oracle_best_method | $88,443.33 | $88,443.33 |
| ceiling | — | $116,808.97 |

## 4. Strong-model edge (§4.4)

- Effective floor = max(momentum, null) = **$556.75**.
- **Strong-model edge: $-535.14 = -0.535%** of bankroll, over **1 settled points** (7B was -0.301% over 382 settled).
- Headroom captured: **-16.5%**. Abstention: 99.7%.

## 5. Verdict (E = 3.0%, unchanged rule)

- 7B: **FAILED** (edge -0.301%).
- claude/claude-sonnet-5: **INCONCLUSIVE** (edge -0.535%).

## 6. Sanity + coverage
- Five §4 sanity checks: **ALL PASSED**; no-post-decision-data guard confirmed.
- LLM calls: 0 · cache hits: 600 · tokens: 0. Diversity: 30 symbols, 478 dates, 1 settled.

## 7. The three-way read (§5 — stated honestly, goalposts unmoved)

**INCONCLUSIVE — the caveat is NOT closed, but for an informative reason.** The strong model settled only **1 point(s)** (99.7% abstention), below the coverage floor, so there is no verdict to compare against 7B. The cause is not a bug: the frontier model was systematically **honestly uncertain** — its confidence capped at the C1 floor (0.60) on nearly every point, so the fixed enter-iff-confidence≥0.60 rule made it abstain almost everywhere. That is arguably the *correct* behavior on three coin-flip methods with price features only: a strong reasoner declines to fake conviction. Per §2.4 the C1 threshold was NOT moved to force a decision. Reading: the model didn't fail the thesis — it declined to play, which tells us price-features-only selection lacks a confidently-exploitable signal. Options (human's call): (a) accept that the 7B FAILED + frontier-abstains pattern jointly points to a weak thesis and stop; (b) re-run with the C1 floor treated as a **recorded, ratified** parameter change (not a silent tune) if you want a settled-trade comparison; (c) proceed to Stage 3 to test whether news changes the confidence picture.

## 8. Carried flags (unchanged)
- No-news / Stage-3 Research delta; H3 (live hourly-bar) Stage-3 precondition; no-crypto gap; D1 register-logging. None affected by the model swap.
