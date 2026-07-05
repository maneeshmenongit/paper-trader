"""Review-doc renderer (DT-12.2, Steward Wave 4 Task 6).

FRAMEWORK layer. Renders a PROPOSED proposal as a markdown review doc with EVERY
cited Store B entry inlined IN FULL — evidence is read, not trusted-by-reference
(the anti-rubber-stamp ritual: G4). The human reads the actual observations, not
a promise that they exist.

Read-only: takes the proposal record + a Store B reader; writes nothing.
"""

from __future__ import annotations

import json
from typing import Any


def _load_cited_entries(store_b: Any, evidence_refs: list[str]) -> list[dict[str, Any]]:
    if not evidence_refs:
        return []
    placeholders = ",".join("?" for _ in evidence_refs)
    with store_b.connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM ledger_entries WHERE entry_id IN ({placeholders}) "
            f"ORDER BY entry_id",
            tuple(evidence_refs),
        ).fetchall()
    return [dict(r) for r in rows]


def render_review_doc(proposal: dict[str, Any], *, store_b: Any) -> str:
    """Return the markdown review doc for one proposal, cited entries inlined."""
    evidence_refs = json.loads(proposal["evidence_refs"])
    entries = _load_cited_entries(store_b, evidence_refs)

    lines: list[str] = []
    lines.append(f"# Proposal {proposal['proposal_id']} — {proposal['status']}")
    lines.append("")
    lines.append(f"- **target_skill:** `{proposal['target_skill']}`")
    lines.append(f"- **base_version_id:** `{proposal['base_version_id']}`")
    lines.append(f"- **author:** {proposal['author']}")
    lines.append(f"- **created_at:** {proposal['created_at']}")
    lines.append(f"- **complexity:** {proposal['complexity_tag']}")
    lines.append("")
    lines.append("## Proposed change")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(json.loads(proposal["proposed_change"]), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Rationale")
    lines.append("")
    lines.append(proposal["rationale"])
    lines.append("")
    lines.append(f"## Cited evidence ({len(entries)} entr{'y' if len(entries) == 1 else 'ies'})")
    lines.append("")
    lines.append(
        "> Every cited ledger entry is inlined IN FULL below — read the evidence, "
        "do not trust it by reference."
    )
    lines.append("")

    # Complexity ritual weight (§8.4): a high-complexity proposal (touches Execute
    # risk gates or rewrites routing) gets the cooling-off banner.
    if proposal["complexity_tag"] == "high":
        lines.append("**⚠ HIGH complexity** — mandatory cooling-off; gate in a "
                     "different session than first read.")
        lines.append("")

    for entry in entries:
        lines.append(f"### Ledger entry `{entry['entry_id']}`")
        lines.append("")
        lines.append(f"- **observation_type:** {entry['observation_type']}")
        lines.append(f"- **subject:** {entry['subject']}")
        lines.append(f"- **author:** {entry['author']}")
        lines.append(f"- **observed_at:** {entry['observed_at']}")
        lines.append(f"- **cycle_id:** {entry['cycle_id']}")
        lines.append(f"- **invocation_id:** {entry['invocation_id']}")
        lines.append("")
        lines.append("**evidence:**")
        lines.append("")
        lines.append("```json")
        # inline the full frozen evidence payload
        try:
            payload = json.loads(entry["evidence"])
            lines.append(json.dumps(payload, indent=2, sort_keys=True))
        except (json.JSONDecodeError, TypeError):
            lines.append(str(entry["evidence"]))
        lines.append("```")
        lines.append("")

    # Note any cited ref that could not be resolved (loud, never silent).
    resolved = {e["entry_id"] for e in entries}
    missing = [r for r in evidence_refs if r not in resolved]
    if missing:
        lines.append("## ⚠ Unresolved evidence refs")
        lines.append("")
        for m in missing:
            lines.append(f"- `{m}` — cited but NOT found in Store B")
        lines.append("")

    lines.append("## Decision")
    lines.append("")
    lines.append("_decision_note is mandatory and non-empty, even for approvals "
                 "(recorded judgment, not reflex). The gate/fork is Wave 5._")
    lines.append("")
    return "\n".join(lines)
