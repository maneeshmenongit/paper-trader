"""Correction officer — proposer half (DT-11.3 / DT-12.4, Steward Wave 4).

FRAMEWORK machinery, SEPARATE from the observer (spec §7: the two halves never
touch; the ledger is the only channel between them). Slow cadence — a separate
entry point (run_proposer.py), not part of any cycle.

Reads ONLY Store B observations + current skill versions (§7.2). Never touches the
fast loop or the app db. MAY call the LLM seam to DRAFT the narrative, but every
claim is CITE-NEVER-ASSERT: a proposal MUST cite specific Store B entry_ids in
evidence_refs; empty evidence is illegal by construction (§8.2).

Wave 4 creates PROPOSED records only. It NEVER approves, forks, flips the currency
pointer, or writes a skill-version row — those are Wave 5.

One-proposal-at-a-time guard (DT-12.4): declines to open a proposal against a skill
that already has one in PROPOSED/APPROVED/IN_WINDOW.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

OFFICER_AUTHOR = "correction-officer"


class ProposerDeclinedError(Exception):
    """The proposer declined to open a proposal (e.g. guard, no evidence)."""


class Proposer:
    def __init__(
        self,
        *,
        store_b: Any,
        proposal_store: Any,
        application_id: str,
        clock: Any,
        narrator: Callable[[str, str], tuple[str, int]] | None = None,
    ):
        self.store_b = store_b
        self.proposals = proposal_store
        self.application_id = application_id
        self.clock = clock
        # Optional LLM seam for narrative articulation only (cite-never-assert
        # is enforced structurally, not by the narrator).
        self.narrator = narrator

    def read_observations(self, target_skill: str) -> list[dict[str, Any]]:
        """Read Store B entries whose subject is about the target skill."""
        with self.store_b.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ledger_entries WHERE subject LIKE ? ORDER BY entry_id",
                (f"%{target_skill}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def propose(
        self,
        *,
        proposal_id: str,
        target_skill: str,
        base_version_id: str,
        proposed_change: dict[str, Any],
        complexity_tag: str = "low",
    ) -> str:
        """Draft and write ONE PROPOSED record. Returns the proposal_id.

        Raises ProposerDeclinedError if the guard blocks it or there is no evidence.
        """
        # DT-12.4 guard: one proposal at a time per skill.
        existing = self.proposals.open_proposal_for(target_skill)
        if existing is not None:
            raise ProposerDeclinedError(
                f"a proposal is already open for {target_skill} "
                f"(status {existing['status']}) — one at a time (DT-12.4)"
            )

        # Cite-never-assert: gather the evidence FIRST; no evidence, no proposal.
        observations = self.read_observations(target_skill)
        evidence_refs = [o["entry_id"] for o in observations]
        if not evidence_refs:
            raise ProposerDeclinedError(
                f"no Store B evidence for {target_skill} — cite-never-assert (§8.2)"
            )

        rationale = self._articulate(target_skill, observations)

        self.proposals.insert_proposed(
            proposal_id=proposal_id,
            created_at=self.clock.now().isoformat(),
            author=OFFICER_AUTHOR,
            application_id=self.application_id,
            evidence_refs=evidence_refs,
            target_skill=target_skill,
            base_version_id=base_version_id,
            proposed_change=proposed_change,
            rationale=rationale,
            complexity_tag=complexity_tag,
        )
        return proposal_id

    def _articulate(self, target_skill: str, observations: list[dict[str, Any]]) -> str:
        """Draft the rationale narrative. If a narrator (LLM seam) is present it
        drafts prose; otherwise a deterministic summary. Either way the rationale
        is ANCHORED to the cited entries — the narrator articulates, never asserts
        new claims."""
        n = len(observations)
        summary = (
            f"{n} ledger observation(s) for {target_skill}: "
            + ", ".join(sorted({o["observation_type"] for o in observations}))
        )
        if self.narrator is None:
            return summary
        text, _tokens = self.narrator(
            "Articulate a proposal rationale strictly from these ledger entries; "
            "cite only what they state, invent nothing.",
            json.dumps(observations, sort_keys=True, default=str),
        )
        # Even with an LLM draft, prepend the deterministic evidence anchor so the
        # cite-never-assert grounding is present regardless of the model's output.
        return f"{summary}\n\n{text}".strip()
