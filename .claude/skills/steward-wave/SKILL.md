---
name: steward-wave
description: >-
  Execute a bounded Steward + paper_trader build wave (or post-v1 register item)
  with the project's established discipline: read authority docs first, work on a
  fresh branch, one task at a time with brief gate reports and human pauses,
  honor the hard-stops, keep tests green, and write a completion report. Invoke
  when the user asks to "start wave N", "continue the build", "do the next wave",
  or work a deferred register item (full Predict, live data clients, window
  evaluation).
---

# Steward build-wave executor

You are continuing a disciplined, gated build. Waves 1–6 (§9.2) are DONE and
merged. This skill runs a NEW bounded unit of work the same way.

## Before writing any code

1. **Read the current state.** Read the latest gate report in
   `docs/gate_reports/` (WAVE6 is newest) and the root `CLAUDE.md` "Build status"
   section. Know what exists and what is deferred.
2. **Read the build authority for THIS task, from the docs, not memory.**
   - **The CURRENT phase is LIVE OPERATION.** Its authority doc is
     `docs_to_claude/application_testing/STEWARD_PAPER_TRADER_LIVE_OPERATION_001.md`
     — READ IT FIRST for any live-operation task. ⚠ It is under gitignored
     `docs_to_claude/`, so it is NOT in the repo; if it is missing (a fresh clone,
     a teammate's machine, CI), STOP and ask the user for it — do not proceed from
     memory or guess the plan.
   - Background authority (tracked): `docs/steward/STEWARD_PAPER_TRADER_RECONCILE_001.md`
     (waves, gates G1–G7, DT-*, DC-1/DC-2, Appendix A skill YAMLs) and
     `docs/steward/STEWARD_FRAMEWORK_SPEC_001.md` (record shapes).
   Quote the exact section that governs the task. If the task touches an agent's
   skill content, author it VERBATIM from Appendix A — never paraphrase.
3. **Confirm the branch.** Waves are stacked feature branches merged after review.
   Create a NEW branch `wave<N>-<slug>` (or `postv1-<slug>`) off `main`. Never
   work on `main`.

## Working discipline (per the project's standing rules)

- **One task per step.** After each task: a BRIEF gate report (files changed,
  test pass/fail counts before→after, deviations) and PAUSE for the user's
  in-terminal sign-off. Do NOT skip the pause unless the user says to run through.
- **Keep it green.** Run `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check`,
  and `.venv/bin/mypy <changed files>` before every commit. Fix lint/type before
  committing (the linter has caught real issues every wave).
- **DC-1 one-way import rule:** `steward/` (framework) must NEVER import
  `paper_trader/` (application). Only the reverse. `tests/test_dc1_boundary.py`
  enforces it — keep it green.
- **Commit per task** with a message ending in the project's Co-Authored-By line
  (see git log). Do not push or merge unless asked.
- **Frozen files:** `agents/base.py`, `llm/*.py`, `persistence/db.py` carry an
  oracle-agents provenance header — extend alongside, don't edit in place. The
  Wave-1 store schemas (Store A/B) are frozen DDL; additive registry methods are
  allowed (Wave 5 did this) but no DDL changes to Store A/B.

## Hard stops — halt and write a milestone report instead of proceeding if:

- a spec/reconcile GAP the documents do not define (do not invent — surface it);
- a decision the reconcile marks PENDING or deferred;
- any change that would alter running fast-loop trade behavior when the task said
  it must be behavior-neutral (re-run the emission off-vs-on byte-identical proof);
- the governance membrane would be breached (an agent writing Store B; the fork
  reachable outside the gate approve path; replay re-executing or writing);
- the wave's declared end condition / boundary.

## Invariants that always hold (verify, don't assume)

- Store A / Store B / skill-version rows are append-only; NEVER emit UPDATE/DELETE
  on them (proposals table is the one legitimately-mutable lifecycle record).
- Agents load their pinned skill from the registry; NO inline risk/decision
  thresholds — parse them from the loaded skill.
- Predict emits the View/NoView union, never UP/DOWN/HOLD as the whole story.
- Observer judges each invocation against the skill_version_id PINNED IN ITS
  STORE A RECORD, never the current pointer.
- Clock is injected everywhere; never `datetime.now()` in agents/emission.
- Tests use fakes only; no network.

## Finishing a wave

Write `docs/gate_reports/WAVE<N>_COMPLETION_REPORT.md` (follow the existing
reports' shape): what was built, test counts, any neutrality/acceptance proof
result, deviations, and what remains deferred. Then STOP and leave the branch for
human review + merge.

## The current phase — LIVE OPERATION (do this next)

Authority: `docs_to_claude/application_testing/STEWARD_PAPER_TRADER_LIVE_OPERATION_001.md`
(gitignored — read it in full first; ask the user if absent). Goal: take the
momentum skeleton LIVE on real market data with a self-hosted open-source LLM and
accumulate REAL governance records. NOT the LLM-selector thesis (Predict stays
momentum-only; thesis stays UNVALIDATED). Six dependency-ordered tasks, one per
prompt, human gate between:

- **T1 live data clients** — real yfinance/Finnhub/CoinGecko behind the existing
  `data/interfaces.py` protocols; agents unchanged; tests on recorded fixtures,
  never live network in CI; honor the semaphore politeness bounds.
- **T2 Ollama LLM client** — behind the router seam, config-selectable; route
  Research + PostMortem bias-tagging through it; Groq/Gemini stay as fallback; do
  NOT touch Predict; faked Ollama endpoint in tests.
- **T3 live config + watchlist** — a live-mode flag that swaps fakes → live;
  confirm the watchlist (determines whether the $10M/$50M R2 floors bind); keep
  secrets/endpoints OUT of the frozen trace.
- **T4 settlement + baseline scoring** — close positions at horizon; thread the
  settling View so PostMortem scores hit/miss + the momentum baseline shadow;
  app-db only, NEVER Store B.
- **T5 scheduled run harness** — local runner; trigger_kind='schedule'; settle
  between cycles; per-cycle logs + replay markdown + observer findings; no VPS.
- **T6 first live run + observation** — the milestone gate: a bounded live run +
  a run report (trades executed/settled/scored on real prices; governance records
  produced; replay clean). No thesis claim.

## Later, separate phases (only if the user explicitly asks — NOT the live phase)

- Full method-selector Predict (mean_reversion + ARIMA + LLM selection; R4). The
  actual thesis experiment. Authority: Appendix A.1, G6.
- IN_WINDOW → three-signal verdict (currently `evaluation` null; DT-12.3 stub).
- DT-7.1 frozen-value re-execution / deterministic-verification diagnostic (G5-deferred).

Confirm with the user WHICH task/phase this covers, then execute with the
discipline above.
