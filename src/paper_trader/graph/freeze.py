"""Orchestrator-input freeze (DT-4.2, Wave 3 Task 4).

Builds the FROZEN orchestrator_input for the cycle header per
docs/steward/DT-4.2_freeze_checklist.md: "everything the decision depended on and
nothing it didn't" (spec §5.1). Honors the checklist's MUST-NOT-FREEZE list — NO
secrets/API keys and NO store paths ever enter the immutable trace.

MUST-FREEZE (captured here from the frozen facts available on CycleState + the
injected cycle config):
  watchlist, calibration_version, CYCLE_TIME_HORIZON_HOURS, CYCLE_TOKEN_BUDGET,
  Research semaphore bounds, log level.
Skill CONTENT is NOT duplicated here — it is frozen via the skill_version_id pin
on each invocation (§5.2). The situation snapshot (prices/news) is the substance
of the cycle, captured through invocation inputs, not re-frozen in the header.
"""

from __future__ import annotations

from typing import Any

from paper_trader.agents.research import FINNHUB_LIMIT, YFINANCE_LIMIT
from paper_trader.graph.state import CycleState


def build_orchestrator_input(state: CycleState, *, cycle_config: dict[str, Any]) -> dict[str, Any]:
    """Assemble the frozen orchestrator_input. Secrets/paths are never included.

    ``cycle_config`` carries the in-effect ungoverned config values (horizon,
    budget, log level) — the caller passes the values that were live at cycle
    start, per the freeze checklist. Anything absent is simply omitted (never
    guessed).
    """
    frozen: dict[str, Any] = {
        # config-driven watchlist that Filter validated (symbols + kind).
        "watchlist": [
            {"symbol": a.symbol, "kind": a.kind, "sector": a.sector}
            for a in state.watchlist
        ],
        "calibration_version": state.calibration_version,
        "cycle_kind": state.cycle_kind,
        # Research semaphore bounds — config, not skill; frozen for replay.
        "research_semaphores": {
            "yfinance": YFINANCE_LIMIT,
            "finnhub_coingecko": FINNHUB_LIMIT,
        },
    }
    # In-effect ungoverned config (horizon/budget/log level) — MUST-FREEZE.
    for key in ("cycle_time_horizon_hours", "cycle_token_budget", "log_level"):
        if key in cycle_config:
            frozen[key] = cycle_config[key]

    # DEFENSIVE: never let a secret/path leak in through cycle_config.
    for forbidden in ("api_key", "groq_api_key", "gemini_api_key", "finnhub_api_key",
                      "db_path", "store_a_path", "store_b_path", "checkpointer_path"):
        frozen.pop(forbidden, None)
    return frozen


def build_orchestrator_decision(state: CycleState) -> dict[str, Any]:
    """The cycle-shape decision (which agents ran, in order, terminal routing)."""
    return {
        "completed_agents": list(state.completed_agents),
        "final_next_agent": state.next_agent,
        "tradeable_count": len(state.tradeable_assets),
        "prediction_count": len(state.predictions),
        "trade_decision_count": len(state.trade_decisions),
        "budget_exhausted": state.budget_exhausted,
    }


def cycle_status(state: CycleState) -> str:
    """Map the cycle outcome to Store A's status enum (completed|failed|partial)."""
    if state.errors:
        # some work happened but errors were recorded -> partial (not a hard fail)
        return "partial"
    return "completed"
