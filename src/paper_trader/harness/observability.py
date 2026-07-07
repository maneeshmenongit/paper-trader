"""Per-cycle observability artifacts (Live-Operation T5).

For each cycle the harness writes, to a run directory:
- ``<cycle_id>.replay.md`` — the read-only reconstructive replay (four-source
  join, per-pin hash trust) rendered as markdown;
- ``<cycle_id>.findings.json`` — the observer's Store B entries for the cycle;
- a one-line run-summary appended to ``run.log`` (trades / settlements / findings).

Replay is READ-ONLY by construction (opens every store ``mode=ro``); it never
re-executes agents or writes. Observer findings are READ from Store B (the
observer already wrote them as the terminal node) — this module never writes
Store A/B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from steward.officer.replay import Replay, render_markdown


@dataclass
class CycleObservability:
    cycle_id: str
    replay_path: Path
    findings_path: Path
    finding_count: int
    all_pins_verified: bool


def write_cycle_artifacts(
    *,
    cycle_id: str,
    run_dir: Path,
    store_a_path: Path,
    store_b_path: Path,
    registry_path: Path,
) -> CycleObservability:
    """Render replay markdown + dump observer findings for one cycle.

    The observer's Store B findings come from the reconstruction's own
    ``ledger_entries`` (source (4) of the four-source join) — a single read-only
    replay pass, no extra DB connection.
    """
    run_dir.mkdir(parents=True, exist_ok=True)

    replay = Replay(
        store_a_path=store_a_path,
        store_b_path=store_b_path,
        registry_path=registry_path,
    )
    reconstruction = replay.reconstruct(cycle_id)

    markdown = render_markdown(reconstruction)
    replay_path = run_dir / f"{cycle_id}.replay.md"
    replay_path.write_text(markdown)

    findings = reconstruction.ledger_entries
    findings_path = run_dir / f"{cycle_id}.findings.json"
    findings_path.write_text(json.dumps(findings, indent=2, default=str))

    return CycleObservability(
        cycle_id=cycle_id,
        replay_path=replay_path,
        findings_path=findings_path,
        finding_count=len(findings),
        all_pins_verified=reconstruction.all_verified,
    )
