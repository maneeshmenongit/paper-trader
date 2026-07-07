# Steward + paper_trader — build context

## Repo layout (DC-1 three-layer separation)
- `steward/` — FRAMEWORK. Engine code and record shapes (Store A/B DDL,
  skill-version table, correction officer, replay). Reusable verbatim across apps.
- `paper_trader/` — APPLICATION. Domain agents, skill *content*, app db, config,
  data-client seams. Imports `steward`.
- Instance data (`.sqlite` files) — framework-shaped, app-scoped. Lives in
  paper_trader's data directory. Framework opens connections by injected PATH;
  it never hardcodes where instance data lives.

## The one-way import rule (enforced by tests/test_dc1_boundary.py)
`steward/` MUST NOT import from `paper_trader/`. Only `paper_trader/` imports
`steward/`. A violation is a build error, not a style note.

## Authority documents (docs/steward/)
- STEWARD_FRAMEWORK_SPEC_001.md — the record-shape authority. Author table
  columns and record schemas from this.
- PAPER_TRADER_ARCH_002.md — the existing app (CycleState, tables, agents).
  Reconciliation target; do not break it.
- STEWARD_PAPER_TRADER_RECONCILE_001.md — the BUILD AUTHORITY. Waves 1–6,
  gates G1–G7, DC-1/DC-2, the DT punch-list, and Appendix A's five @v1 skill
  YAMLs. Wave 2 skill files are authored VERBATIM from Appendix A, never from
  memory.

## Execution discipline
- One bounded task per prompt; a human gate sits between tasks.
- Store A and Store B records are immutable / append-only. Never emit code that
  UPDATEs or DELETEs a governance row.
- The fast loop keeps trading throughout the build. Governance components attach
  alongside; they never block a trading cycle.
- No framework feature without a demonstrated paper_trader need.
- Any spec gap discovered during build is a RECORDED spec amendment, flagged
  loudly — never a silent bend.
- Gate reports are brief: what changed, test results, deviations. No architecture prose.

## Store map (six files, six connection paths, never co-mingled)
checkpointer.sqlite (crash recovery) · paper_trader.sqlite (domain history) ·
Store A (execution trace, immutable) · Store B (correction ledger, append-only) ·
skills.sqlite (skill-version registry + currency pointer) · proposals.sqlite
(proposal lifecycle — the one legitimately-mutable governance record).
Paths are injected via `paper_trader/config.py`; the framework never hardcodes
where instance data lives.

---

## BUILD STATUS (updated after Wave 6)

**Waves 1–6 (§9.2) are DONE and merged to `main`. 357 tests pass.** The governance
half is built and proven end-to-end by the DT-12.5 acceptance walk
(`tests/test_dt125_acceptance.py`). Per-wave detail lives in
`docs/gate_reports/WAVE*_COMPLETION_REPORT.md` (WAVE6 is newest — read it first).

**What exists and works:**
- Framework (`steward/`): five-store substrate; versioned skills + hash-verified
  loader; observer (deterministic predicate runner over Store A → Store B);
  proposer (cite-never-assert); gate CLI + atomic slow-loop fork + crash
  reconciliation; read-only reconstructive replay.
- Application (`paper_trader/`): five agents (Filter, Research, Predict, Execute,
  PostMortem) + rules-first supervisor; Store A emission (non-blocking,
  behavior-neutral); the observer wired as the terminal node.

**What is deliberately minimal / deferred:**
- **Predict is momentum-only** — the full method-selector (mean_reversion, ARIMA,
  LLM selection) is not built.
- **No live data clients** — protocols + fakes only (no live yfinance/Finnhub/CoinGecko).
- **IN_WINDOW → verdict** — window `evaluation` stays null (v1 stub).
- Interior placeholders: fractional-Kelly math, same-sector cap enforcement,
  baseline-P&L settlement comparison.
- DT-7.1 frozen-value re-execution / deterministic-verification diagnostic (G5-deferred).

## THE CURRENT BUILD AUTHORITY — the LIVE-OPERATION phase (next up)

The immediate next phase is **operational shakedown: take the momentum skeleton
LIVE on real market data with a self-hosted open-source LLM**, and accumulate REAL
governance records. This is NOT the LLM-as-selector thesis experiment (Predict
stays momentum-only; the thesis stays UNVALIDATED — that is a later, separate phase).

**Authority doc:** `docs_to_claude/application_testing/STEWARD_PAPER_TRADER_LIVE_OPERATION_001.md`
— READ IT FIRST. ⚠ It is under gitignored `docs_to_claude/` (the human's authoring
space), so it is NOT tracked in the repo and won't clone/pull — it only exists on
the operator's machine. It supersedes the generic "post-v1 register" as the plan
for the next thread.

Its six dependency-ordered tasks (one bounded prompt each, human gate between):
- **T1** live data clients (real yfinance/Finnhub/CoinGecko behind the existing
  protocols; agents unchanged; tests on recorded fixtures, never live network in CI)
- **T2** open-source LLM client (Ollama behind the router seam, config-selectable;
  route Research + PostMortem bias-tagging through it; Groq/Gemini stay as fallback;
  do NOT touch Predict)
- **T3** live config + watchlist + a live-mode flag (fakes → live); keep secrets/
  endpoints out of the frozen trace
- **T4** settlement + baseline scoring (close positions at horizon; score hit/miss
  + the momentum baseline shadow; app-db only, never Store B)
- **T5** local scheduled run harness (trigger_kind='schedule'; settle between
  cycles; per-cycle logs + replay markdown + observer findings; local-first, no VPS)
- **T6** first live run + observation (the milestone gate + run report)

## Continuing in a new thread
Invoke the **`steward-wave`** skill (say `/steward-wave` or "continue the build").
It reads the live-operation authority doc (path above) + the latest gate report,
creates a fresh branch off main, runs one task at a time with brief gate reports
and human pauses, honors the hard-stops, keeps tests/lint/mypy green, and writes a
completion report. Do NOT start building without it — the discipline (read
authority first, gated tasks, DC-1, append-only, behavior-neutrality) is what has
kept every wave clean.
