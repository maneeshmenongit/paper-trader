"""Supervisor — composes the five agents into one trading cycle (Wave 2.5 Task 8).

Rules-first sequencer (spec §4.4): the deterministic decision functions
(graph/decisions.py) are the conditional edges between agent nodes. Each agent
runs under async write-enforcement (agents/enforce.py). The cycle:

    start ─(A)─ postmortem? ─(B, reconciled)─ filter ─(C)─ research ─(D)─
        predict ─(E)─ execute ─ end
    with graceful early-exit: empty tradeable set ends at Decision C; budget
    downgrade ends at Decision D; no actionable View ends at Decision E.

This is the fast loop. It writes ONLY the app db + checkpointer (via the agents /
repository); it does NOT emit to Store A/B this wave. No agent reads
recent_post_mortems to self-adjust in-cycle (the demoted Decision B trap).
"""

from __future__ import annotations

from typing import Any

from paper_trader.agents.enforce import run_with_write_enforcement
from paper_trader.emission import Emitter
from paper_trader.graph import decisions
from paper_trader.graph.emit_boundary import run_agent_with_emission
from paper_trader.graph.freeze import (
    build_orchestrator_decision,
    build_orchestrator_input,
    cycle_status,
)
from paper_trader.graph.state import CycleState


class Supervisor:
    def __init__(
        self,
        *,
        filter_agent: Any,
        research_agent: Any,
        predict_agent: Any,
        execute_agent: Any,
        postmortem_agent: Any,
        emitter: Emitter | None = None,
        clock: Any | None = None,
        skill_pins: dict[str, str] | None = None,
        cycle_config: dict[str, Any] | None = None,
        trigger_kind: str = "schedule",
    ):
        self.agents = {
            "filter": filter_agent,
            "research": research_agent,
            "predict": predict_agent,
            "execute": execute_agent,
            "postmortem": postmortem_agent,
        }
        # Which decision function routes AFTER each node completes.
        self._router = {
            "postmortem": decisions.decide_after_postmortem,
            "filter": decisions.decide_after_filter,
            "research": decisions.decide_after_research,
            "predict": decisions.decide_after_predict,
            "execute": decisions.decide_after_execute,
        }
        # Store A emission (Wave 3). When emitter is None (or disabled), the cycle
        # runs the plain write-enforcement path — byte-identical behavior.
        self.emitter = emitter
        self.clock = clock
        self.skill_pins = skill_pins or {}
        self.cycle_config = cycle_config or {}
        self.trigger_kind = trigger_kind

    def _emitting(self) -> bool:
        return self.emitter is not None and self.emitter.enabled and self.clock is not None

    async def run_cycle(self, state: CycleState) -> CycleState:
        # Decision A (deterministic): settle-before-scan.
        node = decisions.decide_after_start(state)
        state.next_agent = node
        seq = 0

        while node != "end":
            agent = self.agents[node]
            if self._emitting():
                assert self.emitter is not None
                state = await run_agent_with_emission(
                    agent, state,
                    emitter=self.emitter, clock=self.clock,
                    skill_version_id=self.skill_pins.get(agent.name, ""),
                    invocation_seq=seq,
                )
            else:
                state = await run_with_write_enforcement(agent, state)
            seq += 1
            node = self._router[node](state)
            state.next_agent = node

        # Cycle terminus: emit the single immutable cycle_header (DT-4.2/4.4),
        # which flushes the buffered invocations (they FK to the header). This is
        # the ONLY header write and happens once. Non-blocking.
        if self._emitting():
            assert self.emitter is not None and self.clock is not None
            if state.ended_at is None:
                state.ended_at = self.clock.now()
            self.emitter.emit_cycle_header(
                cycle_id=state.cycle_id,
                started_at=state.started_at.isoformat(),
                ended_at=state.ended_at.isoformat(),
                trigger_kind=self.trigger_kind,
                orchestrator_input=build_orchestrator_input(
                    state, cycle_config=self.cycle_config
                ),
                orchestrator_decision=build_orchestrator_decision(state),
                # DT-4.4: all v1 decisions are deterministic; the dormant LLM slot
                # never yields 'llm', so decision_mode is always 'rule'.
                decision_mode="rule",
                orchestrator_rationale=None,
                status=cycle_status(state),
            )

        return state
