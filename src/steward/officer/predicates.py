"""Predicate registry (DT-11.2, Steward Wave 4).

FRAMEWORK layer (DC-1). The observer checks declared skill constraints by keying
each constraint into a registered predicate (G6: skills declare parameters;
predicates live in code). A declared constraint with NO registered predicate is a
BUILD ERROR — surfaced loudly, never silently skipped (I-9's "vagueness caught by
the test suite").

CONSTRAINT-KEY NOTE (deviation, recorded): G6 describes typed constraints
(`{id, type, params, description}`) keying by `type`. The ratified @v1 skills
(DT-15.3) carry `{id, text}` (prose, authored verbatim from Appendix A), and G3
frames the check-set per-agent (Execute C1, Predict …). So predicates are keyed on
the composite `"{agent_name}:{constraint_id}"` — the identity the authored skills
actually provide. The build-error-on-missing-predicate invariant is preserved:
every declared constraint on a checked agent must have a registered predicate.

A predicate is a pure, DETERMINISTIC function (no LLM, I-2) that inspects a
single agent invocation's frozen input/output plus the constraint's params, and
returns a Divergence when the agent's CONDUCT violated what the skill declared —
never on PERFORMANCE (a bad forecast is PostMortem's data, not a divergence).

The framework owns the registry mechanism; the application registers its concrete
predicates (its constraint types) into it. That keeps the check-set derived from
the app's own skills while the runner stays framework-reusable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class InvocationView:
    """The frozen facts a predicate inspects for one agent invocation."""

    invocation_id: str
    cycle_id: str
    agent_name: str
    skill_version_id: str
    agent_input: Any            # parsed frozen input (from Store A)
    agent_output: Any           # parsed frozen output (from Store A)
    skill: Any                  # the loaded, hash-verified pinned skill content


@dataclass(frozen=True)
class Divergence:
    """A single detected divergence — becomes one Store B entry."""

    observation_type: str       # e.g. 'constraint-violation', 'escalation-observed'
    detail: dict[str, Any]      # structured evidence (frozen JSON in the ledger)
    invocation_id: str | None = None  # nullable (outcome-mismatch cites elsewhere)


# A predicate: (constraint, InvocationView) -> list[Divergence] (0..n).
Predicate = Callable[[dict[str, Any], InvocationView], list["Divergence"]]


class UnregisteredPredicateError(Exception):
    """A declared constraint type has no registered predicate. Build error."""


class AgentPredicate(Protocol):
    def __call__(
        self, constraint: dict[str, Any], inv: InvocationView
    ) -> list[Divergence]: ...


def constraint_key(agent_name: str, constraint_id: str) -> str:
    """The composite key predicates register/resolve under."""
    return f"{agent_name}:{constraint_id}"


@dataclass
class PredicateRegistry:
    """Maps "{agent}:{constraint_id}" -> predicate. Missing key is a build error."""

    _by_key: dict[str, Predicate] = field(default_factory=dict)

    def register(self, agent_name: str, constraint_id: str, predicate: Predicate) -> None:
        self._by_key[constraint_key(agent_name, constraint_id)] = predicate

    def has(self, agent_name: str, constraint_id: str) -> bool:
        return constraint_key(agent_name, constraint_id) in self._by_key

    def get(self, agent_name: str, constraint_id: str) -> Predicate:
        key = constraint_key(agent_name, constraint_id)
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise UnregisteredPredicateError(
                f"no predicate registered for {key!r} — declare it more checkably "
                f"or register a predicate (build error)"
            ) from exc

    def keys(self) -> set[str]:
        return set(self._by_key)
