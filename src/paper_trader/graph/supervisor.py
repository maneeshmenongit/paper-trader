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
from paper_trader.graph import decisions
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

    async def run_cycle(self, state: CycleState) -> CycleState:
        # Decision A (deterministic): settle-before-scan.
        node = decisions.decide_after_start(state)
        state.next_agent = node

        while node != "end":
            agent = self.agents[node]
            state = await run_with_write_enforcement(agent, state)
            node = self._router[node](state)
            state.next_agent = node

        return state
