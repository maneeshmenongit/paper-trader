# T01 Gate Report — Scaffolding

**Branch:** feat/T01-scaffolding
**Commits:** 52f1172 (T01: scaffold paper-trader repo)
**Started:** 2026-06-23
**Completed:** 2026-06-23

## What was built

- Repo skeleton matching `PAPER_TRADER_ARCH_001.md` §3: all package directories
  under `src/paper_trader/` with empty `__init__.py`, plus `scripts/`, `config/`,
  `tests/{unit,integration,fixtures}/`, `docs/{decisions,gate_reports}/`, and a
  gitignored `data/` tree.
- `pyproject.toml` per the T01 spec (hatchling, deps, dev extras, ruff/mypy/pytest config).
- `.env.example`, `.gitignore`, `README.md` (1–2 paragraph stub).
- `docs/PAPER_TRADER_ARCH_001.md` committed.
- 9 `[COPIED]` infrastructure files from oracle-agents, plus 1 required dependency
  (`llm/errors.py`) — see deviations.
- `tests/unit/test_smoke.py` (3 tests, all passing).
- Confirmation of understanding (per prompt §"Read First"):
  - **Why separate repo:** oracle-agents is a live system with open positions;
    coupling paper-trader to it risks regressing the live cycle on every commit.
    Copy-then-extract (ADR-PT-001) defers the shared `worldwise-core` abstraction
    until there's a sample size of two.
  - **Provenance header:** the `# ─── PROVENANCE ───` block marking a file as copied
    verbatim from oracle-agents @ a specific commit, so the deliberate duplication
    is greppable when extraction happens later.
  - **Out of scope for T01:** domain code, data clients, agents — confirmed; none built.

## Files copied from oracle-agents

oracle-agents HEAD at copy time: **b14b8f5cde141a35c6708b17cc3ebd95e5ad3967**

| Source (oracle-agents) | Destination (paper-trader) | Import change |
|---|---|---|
| `agents/base.py` | `agents/base.py` | `graph.state` import stubbed (see deviations) |
| `llm/interfaces.py` | `llm/interfaces.py` | none |
| `llm/groq_client.py` | `llm/groq_client.py` | none |
| `llm/gemini_client.py` | `llm/gemini_client.py` | `oracle_agents.llm.groq_client` → `paper_trader.llm.groq_client` |
| `llm/router.py` | `llm/router.py` | `oracle_agents.llm.*` → `paper_trader.llm.*` (budget, errors, interfaces) |
| `llm/budget.py` | `llm/budget.py` | none |
| `data/news.py` | `data/news.py` | `domain.NewsItem` import stubbed (see deviations) |
| `persistence/db.py` | `persistence/db.py` | none |
| `analytics/sentiment.py` | `analytics/sentiment.py` | none |
| `llm/errors.py` | `llm/errors.py` | none — **not in the copy table; copied as a dependency** |

## Tests

`pytest tests/unit/test_smoke.py -v`:

```
tests/unit/test_smoke.py::test_package_imports PASSED                    [ 33%]
tests/unit/test_smoke.py::test_llm_budget_imports PASSED                 [ 66%]
tests/unit/test_smoke.py::test_agents_base_imports PASSED                [100%]
============================== 3 passed in 0.01s ===============================
```

`pytest --collect-only`: 3 tests collected, no import errors.

`ruff check src/ tests/`: **All checks passed!**

`mypy src/paper_trader/` (strict): 8 errors, all in `[COPIED]` files — `no-any-return`
on the VADER/SDK wrappers and missing `dict` type args on the copied `kwargs`/`entry`
dicts. The T01 DoD explicitly accepts this: *"mypy --strict may flag the copied files
for `Any` returns — that's acceptable for T01; we tighten in later tasks."* The copy
rule forbids editing copied logic, so these were left verbatim. No mypy errors in any
non-copied code.

## Deviations from spec

1. **`llm/errors.py` copied although not in the copy table.** `llm/router.py` (which IS
   in the table) imports `BudgetExhaustedError` from `oracle_agents.llm.errors`. Without
   copying `errors.py`, `router.py` would not import. Copied verbatim with a provenance
   header that notes it is a dependency. This is the smallest change that keeps `router.py`
   importable; no logic invented.

2. **Stubs instead of bare commented-out imports.** The spec says: comment out
   unresolvable `oracle_agents.domain.*` / `graph.state` imports *"and leave a stub at the
   bottom of the file if needed for the test smoke test to pass."* Two files needed stubs:
   - `agents/base.py`: the `CycleState` type (from `graph.state`, arrives T15) — replaced
     with a minimal `CycleState` Protocol declaring only `completed_agents` and
     `model_dump()`. Logic unchanged.
   - `data/news.py`: `NewsItem` (from `domain`, arrives T05) is *constructed at runtime*,
     so a commented-out import alone would `NameError`. Added a minimal `NewsItem`
     dataclass mirroring the constructor kwargs used in the file. Logic unchanged.
   Both stubs carry `# TODO(T05)` / `# TODO(T15)` markers pointing to the task that
   replaces them.

3. **Extra dependencies in `pyproject.toml`.** Added `google-genai` (the copied
   `gemini_client.py` imports `google.genai`, the newer SDK oracle-agents migrated to;
   the spec's dep list only had the older `google-generativeai`), `httpx` (imported by
   the copied `data/news.py`), and `pyarrow` (Parquet engine for the T02 backtest cache).
   `google-generativeai` was kept as listed in the spec.

4. **`.gitignore` `data/` anchored to repo root (`/data/`).** An unanchored `data/`
   pattern also matched `src/paper_trader/data/`, which must be tracked. Anchored it so
   only the root `data/` cache dir is ignored.

5. **Test comment reflowed.** The spec's smoke-test line exceeded ruff's 100-char limit;
   the trailing comment was moved to its own line. Assertion logic is identical.

6. **`docs_to_claude/` gitignored.** The operator-provided handoff prompts (including a
   `.env` with live keys) live under `docs_to_claude/`; excluded from the repo so secrets
   are never committed.

## Confirmations

- [x] All `[COPIED]` files have provenance headers
- [x] All `[COPIED]` files' logic is unchanged (only imports adjusted / domain types stubbed)
- [x] `pip install -e ".[dev]"` succeeds in a fresh venv (Python 3.13.5)
- [x] `pytest --collect-only` passes
- [x] ruff is clean; mypy errors are confined to copied files (accepted by DoD)

## Open questions for the reviewer

1. `agents/base.py`'s `ALWAYS_WRITABLE` set lists `llm_tokens_used`, but the architecture's
   `CycleState` (§4.1) names the field `llm_tokens_consumed`. This is a pre-existing
   discrepancy in the oracle-agents source, copied verbatim. Flag for whoever builds T15 —
   it likely needs reconciling when the real `CycleState` lands, but fixing it now would
   violate the T01 copy rule.
2. The build venv uses Python 3.13.5 (system `python3`); pyproject requires `>=3.11`. No
   issue, but noting the actual interpreter used.
