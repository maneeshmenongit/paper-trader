"""Async-aware write-authorization enforcement (Wave 2.5 Task 3).

The frozen `agents/base.py` (oracle-agents provenance — do not edit) provides the
synchronous `enforce_writes`. The paper-trader domain agents are async (the data
seams are async; ARCH_002 §7.3 confirms async is a real requirement), so this
module provides the same enforcement for an async `agent.run(state)` coroutine,
reusing base.py's ALWAYS_WRITABLE set and WriteAuthorizationError verbatim so the
contract is identical.

An agent declares `name` and `writes`; any change to a CycleState field outside
`writes ∪ ALWAYS_WRITABLE` raises WriteAuthorizationError.
"""

from __future__ import annotations

from typing import Protocol

from paper_trader.agents.base import ALWAYS_WRITABLE, WriteAuthorizationError
from paper_trader.graph.state import CycleState


class AsyncAgent(Protocol):
    name: str
    writes: list[str]

    async def run(self, state: CycleState) -> CycleState: ...


async def run_with_write_enforcement(agent: AsyncAgent, state: CycleState) -> CycleState:
    """Run an async agent and enforce its declared write-set (mirrors enforce_writes)."""
    before = state.model_dump()
    new_state = await agent.run(state)
    after = new_state.model_dump()

    allowed = set(agent.writes) | ALWAYS_WRITABLE
    changed_fields = {k for k in after if before.get(k) != after.get(k)}
    forbidden_changes = changed_fields - allowed
    if forbidden_changes:
        raise WriteAuthorizationError(
            f"Agent {agent.name} modified forbidden fields: {forbidden_changes}"
        )

    if agent.name not in new_state.completed_agents:
        new_state.completed_agents = new_state.completed_agents + [agent.name]
    return new_state
