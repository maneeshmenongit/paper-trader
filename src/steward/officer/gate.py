"""Gate CLI — the human review/approval gate (DT-12.1, Steward Wave 5).

FRAMEWORK machinery. A small LOCAL gate (ruling: build a local CLI; do NOT adopt
HumanLayer). It is the ONLY path through which a proposal is approved and the
ONLY place the atomic fork is invoked — the optional-gate-leak inoculation.

Wave 5 read side (Task 3): `list` (open proposals) and `show` (render the review
doc with evidence inlined, and stamp a first-viewed session+timestamp for the
cooling-off ritual). The read side mutates nothing except the first-view stamp,
which is idempotent (a later view never overwrites the first).

The reject path (Task 4), the atomic-fork approve path (Task 5), and startup
reconciliation (Task 6) build on this class.
"""

from __future__ import annotations

from typing import Any

from steward.officer.review_doc import render_review_doc


class GateError(Exception):
    """A gate operation was refused (bad state, missing note, ritual, etc.)."""


class Gate:
    def __init__(
        self,
        *,
        proposal_store: Any,
        store_b: Any,
        registry: Any,
        clock: Any,
        session: str,
    ):
        self.proposals = proposal_store
        self.store_b = store_b
        self.registry = registry
        self.clock = clock
        # A gate "session" — the cooling-off ritual compares approve-session to
        # the first-viewed session. The caller supplies a per-invocation id.
        self.session = session

    # ─── read side (Task 3) ──────────────────────────────────────────────

    def list(self) -> list[dict[str, Any]]:
        """Return open proposals (PROPOSED/APPROVED/IN_WINDOW) — a summary view."""
        return [
            {
                "proposal_id": p["proposal_id"],
                "status": p["status"],
                "target_skill": p["target_skill"],
                "base_version_id": p["base_version_id"],
                "complexity_tag": p["complexity_tag"],
                "created_at": p["created_at"],
                "first_viewed_at": p["first_viewed_at"],
            }
            for p in self.proposals.list_open()
        ]

    def show(self, proposal_id: str) -> str:
        """Render the full review doc for a proposal and stamp first-view.

        Stamping is idempotent (records only the FIRST view's session+timestamp),
        so the cooling-off check compares a later approve session against it.
        """
        proposal = self._require(proposal_id)
        # stamp first-view BEFORE rendering (a show is a view).
        self.proposals.record_first_view(
            proposal_id, session=self.session, viewed_at=self.clock.now().isoformat()
        )
        # re-read so the rendered doc reflects the stamp if it was the first view.
        proposal = self._require(proposal_id)
        return render_review_doc(proposal, store_b=self.store_b)

    # ─── helpers ─────────────────────────────────────────────────────────

    def _require(self, proposal_id: str) -> dict[str, Any]:
        proposal: dict[str, Any] | None = self.proposals.get(proposal_id)
        if proposal is None:
            raise GateError(f"no proposal {proposal_id!r}")
        return proposal
