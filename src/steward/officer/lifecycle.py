"""Proposal lifecycle state machine (spec §8.1, Steward Wave 4 Task 6).

FRAMEWORK layer. Encodes the legal transitions; rejects illegal ones. The full
lifecycle:

    PROPOSED ──approve──▶ APPROVED ──window opens──▶ IN_WINDOW ──┐
       │                                                        ├─▶ SUCCEEDED
       └──reject──▶ REJECTED (terminal)                         ├─▶ FAILED
                                                                └─▶ INCONCLUSIVE
    SUPERSEDED — terminal, OUTSIDE the flow above (reachable from any non-terminal
    state; nothing in v1 triggers it — DT-12.4).

WAVE 4 SCOPE: only creation of PROPOSED is exercised. The APPROVE executor (the
atomic fork: new version row + currency-pointer flip + window timestamps) is
Wave 5 — `advance()` validates the transition but performing the APPROVED side
effects is left as a seam (see execute_transition, which raises NotImplemented for
the fork path). No proposal is advanced in Wave 4.
"""

from __future__ import annotations

# Terminal states have no outgoing transitions (except SUPERSEDED overlay).
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"APPROVED", "REJECTED", "SUPERSEDED"},
    "APPROVED": {"IN_WINDOW", "SUPERSEDED"},
    "IN_WINDOW": {"SUCCEEDED", "FAILED", "INCONCLUSIVE", "SUPERSEDED"},
    "REJECTED": set(),
    "SUCCEEDED": set(),
    "FAILED": set(),
    "INCONCLUSIVE": set(),
    "SUPERSEDED": set(),
}

TERMINAL_STATES = {"REJECTED", "SUCCEEDED", "FAILED", "INCONCLUSIVE", "SUPERSEDED"}


class IllegalTransitionError(ValueError):
    """An attempted proposal state transition is not legal (§8.1)."""


def is_legal(from_state: str, to_state: str) -> bool:
    return to_state in LEGAL_TRANSITIONS.get(from_state, set())


def validate_transition(from_state: str, to_state: str) -> None:
    """Raise IllegalTransitionError unless from_state -> to_state is legal."""
    if from_state not in LEGAL_TRANSITIONS:
        raise IllegalTransitionError(f"unknown state {from_state!r}")
    if not is_legal(from_state, to_state):
        raise IllegalTransitionError(
            f"illegal transition {from_state} -> {to_state} "
            f"(legal next: {sorted(LEGAL_TRANSITIONS[from_state]) or 'terminal'})"
        )


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def execute_transition(from_state: str, to_state: str) -> None:
    """Validate + perform a transition's side effects.

    Wave 4: validation only. The APPROVED transition's side effects (the atomic
    fork — new version row + currency-pointer flip + window timestamps) are Wave 5.
    This function is the SEAM: it validates now and raises NotImplementedError for
    the side-effecting fork path so Wave 5 slots in without changing callers.
    """
    validate_transition(from_state, to_state)
    if to_state == "APPROVED":
        raise NotImplementedError(
            "APPROVE executor (fork + currency-pointer flip + window) is Wave 5"
        )
    # Non-approval transitions have no fork side effects; Wave 5 wires the rest.
    raise NotImplementedError(
        f"transition executor for -> {to_state} is Wave 5 (validation only in Wave 4)"
    )
