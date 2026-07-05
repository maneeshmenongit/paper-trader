"""Agent-boundary emission wrapper (Wave 3, DT-4.3).

Orchestrator-level: runs an agent under write-enforcement AND emits one
agent_invocation capturing frozen input/output + the skill_version_id pin. The
agent is untouched — it gets no Store A seam; this wrapper sits around it.

Behavior-neutral: the wrapped run returns exactly what run_with_write_enforcement
returns; emission is a side-write that never alters the returned state's trade
decisions. Emission failure is swallowed by the Emitter (non-blocking).

Frozen facts captured per invocation:
- agent_input: snapshot of the agent's write-set fields BEFORE it ran (the
  starting context it transformed) + the completed_agents-so-far ordering.
- agent_output: snapshot of the agent's write-set fields AFTER it ran (what it
  produced). "no output" is serialized explicitly (empty dict), never null.
"""

from __future__ import annotations

from typing import Any

from paper_trader.agents.enforce import run_with_write_enforcement
from paper_trader.emission import Emitter
from paper_trader.graph.state import CycleState


def _snapshot(state: CycleState, fields: list[str]) -> dict[str, Any]:
    dump = state.model_dump()
    return {f: dump.get(f) for f in fields}


async def run_agent_with_emission(
    agent: Any,
    state: CycleState,
    *,
    emitter: Emitter,
    clock: Any,
    skill_version_id: str,
    invocation_seq: int,
) -> CycleState:
    """Run one agent (write-enforced) and emit its invocation. Non-blocking."""
    started_at = clock.now().isoformat()
    agent_input = _snapshot(state, agent.writes)

    new_state = await run_with_write_enforcement(agent, state)

    # An agent may expose extra frozen facts for its Store A input (e.g. Execute
    # freezes the equity its cap check used — Wave 5 Task 1). Read AFTER the run
    # so the agent has computed them; behavior-neutral (read-only side-write).
    frozen_facts = getattr(agent, "frozen_facts", None)
    if callable(frozen_facts):
        extra = frozen_facts()
        if extra:
            agent_input = {**agent_input, **extra}

    agent_output = _snapshot(new_state, agent.writes) or {}
    ended_at = clock.now().isoformat()

    # invocation_id: stable, unique, ordered per cycle — "{cycle_id}:{seq}".
    # Store A's invocation_id is TEXT PRIMARY KEY with no format requirement; a
    # zero-padded sequence keeps within-cycle ordering lexicographic for replay.
    invocation_id = f"{new_state.cycle_id}:{invocation_seq:03d}"

    emitter.emit_invocation(
        invocation_id=invocation_id,
        cycle_id=new_state.cycle_id,
        agent_name=agent.name,
        skill_version_id=skill_version_id,
        agent_input=agent_input,
        agent_output=agent_output,
        started_at=started_at,
        ended_at=ended_at,
        status="completed",
    )
    return new_state
