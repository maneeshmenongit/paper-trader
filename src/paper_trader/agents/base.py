"""Base agent contract with write-authorization enforcement.

Every domain agent implements the Agent Protocol and declares which CycleState
fields it may modify via the `writes` whitelist. The `enforce_writes` wrapper
ensures agents can't stomp on each other's state — the most common multi-agent bug.
"""

# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

# TODO(T15): import from paper_trader.graph.state once the CycleState model exists.
# from paper_trader.graph.state import CycleState


class CycleState(Protocol):
    """Stub stand-in for the real CycleState (arrives in T15).

    Only the surface this module touches is declared, so enforce_writes type-checks
    and imports cleanly during scaffolding. Replace the import above when graph/state.py
    lands.
    """

    completed_agents: list[str]

    def model_dump(self) -> dict: ...


class Agent(Protocol):
    name: str
    writes: list[str]  # whitelist of CycleState fields this agent may modify

    def __call__(self, state: CycleState) -> CycleState: ...


class WriteAuthorizationError(Exception):
    pass


# Fields any agent may modify without declaring them in `writes`.
ALWAYS_WRITABLE = {"completed_agents", "errors", "llm_calls_made", "llm_tokens_used"}


def enforce_writes(agent: Agent) -> Callable[[CycleState], CycleState]:
    """Wrap an agent so that unauthorized field modifications raise WriteAuthorizationError.

    Also appends the agent's name to `completed_agents` if not already present.
    """

    def wrapped(state: CycleState) -> CycleState:
        before = state.model_dump()
        new_state = agent(state)
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

    return wrapped
