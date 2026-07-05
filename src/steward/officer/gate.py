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

import json
from datetime import timedelta
from typing import Any

from steward.officer.lifecycle import validate_transition
from steward.officer.review_doc import render_review_doc

# DT-12.3 stabilization window: 14 days OR 20 settled trades, whichever later.
WINDOW_DAYS = 14
WINDOW_SETTLED_TRADES = 20


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

    def list_proposals(self) -> list[dict[str, Any]]:
        """`gate list`: open proposals (PROPOSED/APPROVED/IN_WINDOW) — summary view."""
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

    # ─── reject (Task 4) ─────────────────────────────────────────────────

    def reject(self, proposal_id: str, *, decided_by: str, decision_note: str) -> None:
        """Reject a proposal. decision_note is MANDATORY and non-empty."""
        proposal = self._require(proposal_id)
        self._require_note(decision_note)
        # lifecycle: only a PROPOSED (or APPROVED) proposal can be rejected.
        validate_transition(proposal["status"], "REJECTED")
        self.proposals.set_status_with_decision(
            proposal_id, status="REJECTED",
            decided_at=self.clock.now().isoformat(),
            decided_by=decided_by, decision_note=decision_note,
        )

    # ─── approve + atomic fork (Task 5) ──────────────────────────────────

    def approve(
        self,
        *,
        proposal_id: str,
        decided_by: str,
        decision_note: str,
        new_version_id: str,
        new_content: str,
    ) -> str:
        """Approve a proposal and execute the atomic fork. Returns new_version_id.

        Order (DT-12.1): (a) write approval; (b) SINGLE-FILE atomic registry
        transaction — new version row + currency-pointer flip, all-or-nothing;
        (c) window + IN_WINDOW. In-process rollback-on-error across (a)-(c): if the
        fork or bookkeeping fails, the approval is reverted so no half-applied fork
        persists (a crash mid-sequence is caught by startup reconciliation, Task 6).

        This is the ONLY place the fork is invoked. new_content is the forked skill
        text (human-provided at approval — the docs define proposed_change as the
        structured change but not a YAML-patch engine; the human authors @vN's
        content, consistent with human-gated approval).
        """
        proposal = self._require(proposal_id)
        self._require_note(decision_note)
        validate_transition(proposal["status"], "APPROVED")
        self._ensure_cooling_off(proposal)  # high-complexity cooling-off

        now = self.clock.now()
        prior_status = proposal["status"]

        # (a) write approval to the proposal.
        self.proposals.set_status_with_decision(
            proposal_id, status="APPROVED", decided_at=now.isoformat(),
            decided_by=decided_by, decision_note=decision_note,
        )
        try:
            # (b) ATOMIC registry fork (single-file transaction).
            self.registry.fork_version(
                base_version_id=proposal["base_version_id"],
                new_version_id=new_version_id,
                content=new_content,
                created_by_proposal_id=proposal_id,
                grounding_refs=proposal["evidence_refs"],  # copied from the proposal
                created_at=now.isoformat(),
            )
        except Exception:
            # fork failed -> revert (a); no version row, no pointer move happened.
            self._revert_to(proposal_id, prior_status)
            raise

        try:
            # (c) window + IN_WINDOW.
            closes = now + timedelta(days=WINDOW_DAYS)
            self.proposals.set_in_window(
                proposal_id, new_version_id=new_version_id,
                window_opened_at=now.isoformat(),
                window_closes_at=self._window_closes(closes.isoformat()),
            )
        except Exception:
            # bookkeeping failed AFTER the fork committed. The fork stands (never
            # roll back a committed pointer flip); mark the proposal APPROVED-not-
            # yet-windowed. Startup reconciliation (Task 6) completes step (c).
            raise
        return new_version_id

    @staticmethod
    def _window_closes(iso_time_bound: str) -> str:
        """Encode 'whichever later of 14 days / 20 settled trades'. The time bound
        is the concrete date; the trade-count condition rides alongside it."""
        return json.dumps({
            "time_bound": iso_time_bound,
            "min_settled_trades": WINDOW_SETTLED_TRADES,
            "rule": "whichever_later",
        }, sort_keys=True)

    def _revert_to(self, proposal_id: str, status: str) -> None:
        """Reset a proposal's decision fields back to a prior status (rollback)."""
        self.proposals.set_status_with_decision(
            proposal_id, status=status, decided_at=None, decided_by=None,
            decision_note=None,
        )

    # ─── startup reconciliation (Task 6, DT-12.3 crash-safety) ───────────

    def reconcile(self) -> list[dict[str, str]]:
        """Detect + resolve any APPROVED proposal whose fork state is incomplete.

        APPROVED is a transient status — a clean approve() passes through it to
        IN_WINDOW in one call. An APPROVED proposal at startup means a crash
        mid-sequence. Resolution per the ruling (never leave a half-applied fork):
          - fork committed (a version row exists for the proposal, crash between
            (b) and (c)) -> COMPLETE step (c): stamp window + move to IN_WINDOW,
            and repair the pointer if it did not flip.
          - fork NOT committed (no version row, crash between (a) and (b)) ->
            ROLL BACK the approval to PROPOSED (no half-applied fork; re-approve).

        Returns a list of {proposal_id, action} for what it did.
        """
        actions: list[dict[str, str]] = []
        for proposal in self.proposals.list_by_status("APPROVED"):
            pid = proposal["proposal_id"]
            forked = self.registry.version_by_proposal(pid)
            if forked is not None:
                # crash between (b) and (c): finish the bookkeeping.
                self._repair_pointer(forked)
                self._complete_window(proposal, forked["version_id"])
                actions.append({"proposal_id": pid, "action": "completed_window"})
            else:
                # crash between (a) and (b): roll the approval back.
                self._revert_to(pid, "PROPOSED")
                actions.append({"proposal_id": pid, "action": "rolled_back_to_proposed"})
        return actions

    def _repair_pointer(self, forked: dict[str, str]) -> None:
        """If the fork committed but the pointer somehow did not flip, flip it
        (the fork is atomic, so this is belt-and-braces; safe + idempotent)."""
        current = self.registry.get_current_version_id(
            application_id=forked["application_id"], agent_name=forked["agent_name"],
            skill_name=forked["skill_name"],
        )
        if current != forked["version_id"]:
            self.registry.set_current_version(
                application_id=forked["application_id"], agent_name=forked["agent_name"],
                skill_name=forked["skill_name"], current_version_id=forked["version_id"],
                updated_at=self.clock.now().isoformat(),
            )

    def _complete_window(self, proposal: dict[str, Any], new_version_id: str) -> None:
        now = self.clock.now()
        closes = now + timedelta(days=WINDOW_DAYS)
        self.proposals.set_in_window(
            proposal["proposal_id"], new_version_id=new_version_id,
            window_opened_at=now.isoformat(),
            window_closes_at=self._window_closes(closes.isoformat()),
        )

    # ─── ritual (Task 4) — cooling-off gate for approvals ────────────────

    def _ensure_cooling_off(self, proposal: dict[str, Any]) -> None:
        """High-complexity proposals must be decided in a DIFFERENT session than
        first shown (§8.4 structural cooling-off). Low complexity: no cooling-off.

        Raises GateError if a high-complexity proposal has not been shown yet, or
        is being decided in the same session it was first viewed.
        """
        if proposal["complexity_tag"] != "high":
            return  # low: same-session ack allowed
        first_session = proposal["first_viewed_session"]
        if first_session is None:
            raise GateError(
                "high-complexity proposal must be shown (gate show) before it can "
                "be approved — cooling-off requires a prior viewing session"
            )
        if first_session == self.session:
            raise GateError(
                "high-complexity approval is blocked in the same session it was "
                "first viewed — cool off and approve in a later session (§8.4)"
            )

    @staticmethod
    def _require_note(decision_note: str) -> None:
        if not decision_note or not decision_note.strip():
            raise GateError("decision_note is mandatory and non-empty on every decision")

    # ─── helpers ─────────────────────────────────────────────────────────

    def _require(self, proposal_id: str) -> dict[str, Any]:
        proposal: dict[str, Any] | None = self.proposals.get(proposal_id)
        if proposal is None:
            raise GateError(f"no proposal {proposal_id!r}")
        return proposal
