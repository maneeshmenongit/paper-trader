"""Store A emission adapter (Wave 3, DT-4.2/4.3/4.4).

APPLICATION-level adapter that reads frozen facts out of CycleState and calls the
generic FRAMEWORK writer (steward.storage.store_a). This is the one-to-two
emission (DT-4.5): CycleState stays mutable/ephemeral; emission writes immutable
Store A rows. One-way — the loop never reads Store A back.

INVARIANTS enforced here:
- ORCHESTRATOR/FRAMEWORK-level: domain agents never touch Store A. The emission
  wrapper runs AROUND an agent (after write-enforcement); the agent itself gets no
  Store A seam.
- NON-BLOCKING: a Store A write failure NEVER aborts a cycle. Failures are logged
  at ERROR and counted durably (failed_emissions) so untraced cycles are
  detectable — loud, never silent.
- Store B is NOT written here. Only insert_cycle_header / insert_agent_invocation.
- Emission is behavior-neutral: it reads state, never mutates trade decisions.

Store A itself provides immutability (INSERT-only writer + no-mutation triggers);
this adapter only ever inserts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("paper_trader.emission")


def _json(value: Any) -> str:
    """Serialize a frozen fact to a stable JSON string (sorted keys)."""
    return json.dumps(value, sort_keys=True, default=str)


class Emitter:
    """Non-blocking Store A emitter. Disabled when store_a is None (emission OFF)."""

    def __init__(self, store_a: Any | None, *, application_id: str):
        self.store_a = store_a
        self.application_id = application_id
        self.failed_emissions: list[str] = []  # durable detection of untraced writes
        # Invocations are BUFFERED during the cycle and flushed AFTER the header
        # lands at terminus: agent_invocations.cycle_id FKs to cycle_headers
        # (frozen Store A schema), so the header must exist first. This preserves
        # DT-4.2's "header INSERTed once at cycle terminus" while honoring the FK.
        self._buffer: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self.store_a is not None

    # ─── invocation emission (DT-4.3) — buffered until terminus ──────────

    def emit_invocation(
        self,
        *,
        invocation_id: str,
        cycle_id: str,
        agent_name: str,
        skill_version_id: str,
        agent_input: Any,
        agent_output: Any,
        started_at: str,
        ended_at: str,
        status: str,
    ) -> bool:
        """Buffer one agent_invocation (flushed after the header). NEVER raises."""
        if not self.enabled:
            return False
        self._buffer.append(
            dict(
                invocation_id=invocation_id,
                cycle_id=cycle_id,
                application_id=self.application_id,
                agent_name=agent_name,
                skill_version_id=skill_version_id,
                agent_input=_json(agent_input),
                agent_output=_json(agent_output),
                started_at=started_at,
                ended_at=ended_at,
                status=status,
            )
        )
        return True

    def _flush_invocations(self, cycle_id: str) -> None:
        """Write buffered invocations. Each failure is isolated + non-blocking."""
        assert self.store_a is not None  # only called after a successful header
        for payload in self._buffer:
            try:
                self.store_a.insert_agent_invocation(**payload)
            except Exception:
                self.failed_emissions.append(
                    f"invocation:{payload['agent_name']}:{payload['invocation_id']}"
                )
                logger.error(
                    "Store A invocation emission FAILED (cycle=%s agent=%s) — cycle "
                    "already completed in app db; trade stands",
                    cycle_id, payload["agent_name"], exc_info=True,
                )
        self._buffer.clear()

    # ─── header emission (DT-4.2 / DT-4.4) ───────────────────────────────

    def emit_cycle_header(
        self,
        *,
        cycle_id: str,
        started_at: str,
        ended_at: str,
        trigger_kind: str,
        orchestrator_input: Any,
        orchestrator_decision: Any,
        decision_mode: str,
        orchestrator_rationale: str | None,
        status: str,
    ) -> bool:
        """Emit the single cycle_header at terminus. Returns True on success.
        NEVER raises."""
        if self.store_a is None:
            return False
        header_ok = False
        try:
            self.store_a.insert_cycle_header(
                cycle_id=cycle_id,
                application_id=self.application_id,
                started_at=started_at,
                ended_at=ended_at,
                trigger_kind=trigger_kind,
                orchestrator_input=_json(orchestrator_input),
                orchestrator_decision=_json(orchestrator_decision),
                decision_mode=decision_mode,
                orchestrator_rationale=orchestrator_rationale,
                status=status,
            )
            header_ok = True
        except Exception:
            self.failed_emissions.append(f"header:{cycle_id}")
            logger.error(
                "Store A header emission FAILED (cycle=%s) — cycle already "
                "completed in app db; trace is incomplete (invocations dropped: "
                "they FK to the missing header)",
                cycle_id, exc_info=True,
            )

        # Flush buffered invocations only if the header landed (they FK to it).
        # If the header failed, record the buffered invocations as un-emittable.
        if header_ok:
            self._flush_invocations(cycle_id)
        else:
            for payload in self._buffer:
                self.failed_emissions.append(
                    f"invocation:{payload['agent_name']}:{payload['invocation_id']}"
                )
            self._buffer.clear()
        return header_ok
