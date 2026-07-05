"""Supervisor decisions — the rules-first sequencer (Wave 2.5 Task 8).

Decisions A, C, D, E are deterministic if/elif (spec §4.4 rules-first sequencer;
ARCH_002 §5.2). Decision B is the RECONCILED (demoted) form per the reconcile
doc §2.3 + DT-5.1/5.3/5.4:
  - routing half = a DETERMINISTIC proceed-vs-skip rule (DT-5.1);
  - adaptation half = NOT built — Predict must NOT read recent_post_mortems to
    self-adjust in-cycle (the named trap);
  - the LLM-fallback slot is BUILT but DORMANT + tag-wired (DT-5.4): it exists as
    a seam that cannot fire in v1 (no live LLM routing at all).

Decision E's v1 "[v2-FLAG] any UP" becomes "any actionable View (direction ≠ HOLD)"
per DT-5.5 / the G6 output union.
"""

from __future__ import annotations

from typing import Literal

from paper_trader.domain import View
from paper_trader.graph.state import CycleState

Node = Literal["filter", "research", "predict", "execute", "postmortem", "end"]


def decide_after_start(state: CycleState) -> Node:
    """Decision A (deterministic): settle-before-scan."""
    if state.pending_settlements:
        return "postmortem"
    return "filter"


def decide_after_postmortem(state: CycleState) -> Node:
    """Decision B (RECONCILED, demoted): deterministic proceed-vs-skip.

    The always-on LLM routing node of ARCH_002 is NOT built. Routing is a plain
    rule: proceed to filter. The LLM-fallback slot below is dormant and tag-wired
    — it is a seam that cannot fire in v1 (no rule is ever uncovered here).
    """
    # LLM-fallback slot: built, DORMANT, tag-wired. In v1 there is no uncovered
    # case, so this branch never activates and no LLM call is ever made.
    if _llm_fallback_active(state):  # always False in v1 (dormant slot, DT-5.4)
        return _dormant_llm_route(state)
    return "filter"


def decide_after_filter(state: CycleState) -> Node:
    """Decision C (deterministic): proceed only if something is tradeable."""
    return "research" if state.tradeable_assets else "end"


def decide_after_research(state: CycleState) -> Node:
    """Decision D (deterministic): budget downgrade → end, else predict."""
    return "end" if state.budget_exhausted else "predict"


def decide_after_predict(state: CycleState) -> Node:
    """Decision E (deterministic, reconciled): any actionable View → execute.

    DT-5.5: 'actionable' = a View with direction ≠ HOLD (the G6 union), replacing
    the dead-thesis 'any p.direction == UP'. NoView is never actionable.
    """
    actionable = any(
        isinstance(p, View) and not p.is_baseline and p.direction != "HOLD"
        for p in state.predictions.values()
    )
    return "execute" if actionable else "end"


def decide_after_execute(state: CycleState) -> Node:
    """After Execute the cycle ends (PostMortem ran at the top via Decision A)."""
    return "end"


# ─── dormant LLM-fallback slot (DT-5.4) ──────────────────────────────────

def _llm_fallback_active(state: CycleState) -> bool:
    """The negative-trigger fallback (rule-miss → LLM). DORMANT in v1: there is
    no uncovered case in these deterministic decisions, so this is always False.
    The seam exists so Wave 3 can tag-wire escalation observations."""
    return False


def _dormant_llm_route(state: CycleState) -> Node:  # pragma: no cover - dormant
    """Unreachable in v1 (the slot never activates). Present as the seam only."""
    return "filter"
