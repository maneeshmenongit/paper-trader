# paper_trader @v1 skills — non-authoritative artifacts

These YAML files are **authoring artifacts only**. The authoritative copy of each
skill is the row in the `skill_versions` registry (G2: content lives in the row).
Agents never read skills from disk — they load from the registry via the loader
(`steward.storage.skill_loader.load_skill`), which hash-verifies before returning.

Seeded by `steward.storage.seed_skills.seed_v1_skills` (DT-15.3). All five are
`@v1`, `origin=initial-authoring`, `validation_status=UNVALIDATED`, with the
content hash computed by the writer via the canonical `compute_content_hash`.

## SUPERSEDED-banner intent (DT-9.1 — deferred to Wave 3)

DT-9.1 calls for a SUPERSEDED banner on `risk_gates.toml` and at Filter's inline
thresholds, pointing here. **Those files do not exist yet** — the domain agents
and their config are unbuilt (Wave 3 territory). There is nothing to annotate or
supersede today, so the banner placement is deferred to the point Wave 3 creates
those sources.

Recorded intent for Wave 3: when `risk_gates.toml` and Filter's inline thresholds
are built (or, more likely, when the agents are wired to read from the registry),
they must carry a SUPERSEDED banner naming the corresponding `@v1` skill as the
authority — and the mirror-match test must be upgraded from the forward contract
below to a value-equality assertion (skill value == live-config value).

## Forward mirror-contract (built now)

`tests/test_skill_mirror_contract.py` locks the ratified `@v1` values (Filter
$10M/$50M, Execute Kelly 0.25 / 5% / $100 / 60% / 3 / 10 / >5% / ≥0.55 / ≥0.5%,
Predict ≥0.60, Research 1 Groq + 1 Gemini, PostMortem ~1/4) as a contract the
future live loop must match. A failure means a bad edit to a `@v1` skill or an
intended fork that must go through the gate — never a silent drift. No
`risk_gates.toml` is fabricated to test against.
