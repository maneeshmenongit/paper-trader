"""Correction officer — observer half (DT-11.1, Steward Wave 4).

FRAMEWORK machinery (not a sixth agent; no roster entry, no skill file). Runs
POST-HOC over a completed cycle's Store A records (I-1: last graph node), purely
DETERMINISTIC predicates (I-2, no LLM). For each agent_invocation it:

  1. loads the invocation's PINNED skill via the Wave 2 loader — judged against
     the skill_version_id in ITS Store A record, NEVER the current currency
     pointer (a cycle that ran under @v1 is judged by @v1);
  2. runs the registered predicate for each declared constraint (build error if a
     declared constraint has no predicate);
  3. emits ONE Store B entry per divergence, via the observer-only write identity.

CONDUCT not PERFORMANCE: a violated declared rule/constraint is a divergence; a
bad forecast is not (that is PostMortem outcome data).

NON-BLOCKING: the observer runs after all trades are committed. A failure is
logged at ERROR and recorded (untraced detectable) — it NEVER aborts a cycle and
never touches the trade path (structural neutrality: read-only on Store A / app).

WRITE-AUTH (DT-6.4): Store B INSERTs go only through ObserverLedgerWriter, which
stamps the observer identity. No agent, no PostMortem, holds this writer. Store B
is append-only (Wave 1 no-mutation trigger) — no UPDATE/DELETE for anyone.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from steward.officer.predicates import Divergence, InvocationView, PredicateRegistry
from steward.storage.skill_loader import load_skill

logger = logging.getLogger("steward.officer.observer")

OBSERVER_IDENTITY = "correction-officer"


class ObserverLedgerWriter:
    """The ONLY permitted Store B write path — stamps the observer identity.

    DT-6.4: Store B INSERT is permitted only to the observer identity. This writer
    refuses to write under any other author, and exposes INSERT only (no update or
    delete method exists — append-only, backed by the Wave 1 no-mutation trigger).
    """

    def __init__(self, store_b: Any, *, application_id: str):
        self._store_b = store_b
        self.application_id = application_id

    def insert(
        self,
        *,
        entry_id: str,
        cycle_id: str,
        invocation_id: str | None,
        observed_at: str,
        subject: str,
        observation_type: str,
        evidence: dict[str, Any],
    ) -> None:
        # author is fixed to the observer identity — not a caller-supplied value.
        self._store_b.insert_ledger_entry(
            entry_id=entry_id,
            cycle_id=cycle_id,
            invocation_id=invocation_id,
            observed_at=observed_at,
            author=OBSERVER_IDENTITY,
            subject=subject,
            observation_type=observation_type,
            evidence=json.dumps(evidence, sort_keys=True, default=str),
        )


class Observer:
    """Deterministic predicate runner over a completed cycle's Store A records."""

    def __init__(
        self,
        *,
        store_a: Any,
        registry_conn: Any,
        ledger_writer: ObserverLedgerWriter,
        predicates: PredicateRegistry,
        clock: Any,
        outcome_mismatch_detector: Any | None = None,
    ):
        self.store_a = store_a
        self.registry_conn = registry_conn  # skill-version registry (read-only)
        self.ledger = ledger_writer
        self.predicates = predicates
        self.clock = clock
        # DT-11.5: an app-supplied detector (views) -> [Divergence] for
        # outcome-mismatches. Its Divergences cite the settling PostMortem
        # invocation and reference the original prediction invocation in evidence.
        self.outcome_mismatch_detector = outcome_mismatch_detector
        self.failed: list[str] = []  # durable detection of un-observed cycles

    def observe_cycle(self, cycle_id: str) -> list[Divergence]:
        """Run all predicates for one completed cycle. Non-blocking; returns the
        divergences emitted (also written to Store B)."""
        try:
            return self._observe(cycle_id)
        except Exception:
            self.failed.append(f"observe:{cycle_id}")
            logger.error(
                "Observer FAILED for cycle=%s — cycle already completed; trades "
                "stand; this cycle is un-observed (recorded)",
                cycle_id, exc_info=True,
            )
            return []

    def _observe(self, cycle_id: str) -> list[Divergence]:
        invocations = self._load_invocations(cycle_id)
        views = [self._build_view(inv) for inv in invocations]
        found: list[Divergence] = []
        seq = 0

        for view in views:
            constraints = view.skill.get("constraints", []) if view.skill else []
            for constraint in constraints:
                cid = constraint["id"]
                # build error if a declared constraint has no registered predicate
                predicate = self.predicates.get(view.agent_name, cid)
                for div in predicate(dict(constraint), view):
                    self._emit(cycle_id, div, seq)
                    found.append(div)
                    seq += 1

        # DT-11.5 outcome-mismatch pass (settlements land in later cycles): the
        # detector cites the settling PostMortem invocation; the original
        # prediction invocation is referenced in evidence.
        if self.outcome_mismatch_detector is not None:
            for div in self.outcome_mismatch_detector(views):
                self._emit(cycle_id, div, seq)
                found.append(div)
                seq += 1
        return found

    def _build_view(self, inv: dict[str, Any]) -> InvocationView:
        # Load the PINNED skill (hash-verified) — judged against its own version.
        skill = load_skill(self.registry_conn, inv["skill_version_id"])
        return InvocationView(
            invocation_id=inv["invocation_id"],
            cycle_id=inv["cycle_id"],
            agent_name=inv["agent_name"],
            skill_version_id=inv["skill_version_id"],
            agent_input=json.loads(inv["agent_input"]),
            agent_output=json.loads(inv["agent_output"]),
            skill=skill,
        )

    def _emit(self, cycle_id: str, div: Divergence, seq: int) -> None:
        entry_id = f"{cycle_id}:obs:{seq:03d}"
        # subject carries the agent + skill_version_id (DC-1 scoping via subject).
        self.ledger.insert(
            entry_id=entry_id,
            cycle_id=cycle_id,
            invocation_id=div.invocation_id,
            observed_at=self.clock.now().isoformat(),
            subject=self._subject(div),
            observation_type=div.observation_type,
            evidence=div.detail,
        )

    @staticmethod
    def _subject(div: Divergence) -> str:
        d = div.detail
        return f"{d.get('agent_name', '?')}/{d.get('skill_version_id', '?')}"

    def _load_invocations(self, cycle_id: str) -> list[dict[str, Any]]:
        with self.store_a.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_invocations WHERE cycle_id=? ORDER BY invocation_id",
                (cycle_id,),
            ).fetchall()
        return [dict(r) for r in rows]
