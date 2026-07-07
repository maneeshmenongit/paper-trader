"""Compose a fully-wired, governed trading cycle (Live-Operation T5).

The single production assembly site for the full graph. It loads each agent from
the skill registry at its CURRENT pinned version (honoring the gate's currency
pointer — a fork moves the pointer and agents load the new version next cycle),
wires the emitter (Store A) and observer (Store B) so real governance records
accrue, and hands back everything the runner needs.

Agents receive protocol-typed seams from the provider bundle (fakes or live per
LiveConfig, T3). Skill content drives every threshold — no inline risk values.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.filter import FilterAgent
from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.agents.predict import PredictAgent
from paper_trader.agents.research import ResearchAgent
from paper_trader.config import APPLICATION_ID
from paper_trader.emission import Emitter
from paper_trader.graph.supervisor import Supervisor
from paper_trader.live.providers import DataProviders
from paper_trader.officer_predicates import build_v1_registry, outcome_mismatch_detector
from paper_trader.settlement.engine import SettlementContext
from steward.officer.observer import Observer, ObserverLedgerWriter
from steward.storage.seed_skills import version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry

_AGENTS = ("filter", "research", "predict", "execute", "postmortem")


@dataclass
class GovernedCycle:
    """A wired cycle plus the handles the runner needs to observe/replay it."""

    supervisor: Supervisor
    skill_pins: dict[str, str]
    horizon_hours: int


def resolve_skill_pins(registry: SkillVersionRegistry) -> dict[str, str]:
    """Each agent's CURRENT version_id (the gate's pointer), or the seeded @v1."""
    pins: dict[str, str] = {}
    for agent in _AGENTS:
        current = registry.get_current_version_id(
            application_id=APPLICATION_ID, agent_name=agent, skill_name=agent
        )
        pins[agent] = current or version_id_for(agent)
    return pins


def build_governed_cycle(
    *,
    providers: DataProviders,
    registry: SkillVersionRegistry,
    llm_router: Any,
    store_a: Any,
    store_b: Any,
    clock: Any,
    horizon_hours: int = 24,
    token_budget: int = 15000,
    settlement_contexts: dict[str, SettlementContext] | None = None,
    enable_observer: bool = True,
) -> GovernedCycle:
    """Assemble the Supervisor with emission + observation on.

    ``settlement_contexts`` (from the pre-cycle settlement pass) threads the
    baseline-shadow scoring into PostMortem. ``token_budget`` sizes the per-cycle
    LLM budget the router enforces.
    """
    pins = resolve_skill_pins(registry)

    def _skill(agent: str) -> Any:
        with registry.connection() as conn:
            return load_skill(conn, pins[agent])

    filter_agent = FilterAgent(
        _skill("filter"), clock=clock,
        market_data=providers.market_data, trading_client=providers.trading_client,
    )
    research_agent = ResearchAgent(
        _skill("research"), clock=clock, market_data=providers.market_data,
        company_news=providers.company_news, llm_router=llm_router,
    )
    predict_agent = PredictAgent(_skill("predict"))
    execute_agent = ExecuteAgent(
        _skill("execute"), clock=clock,
        trading_client=providers.trading_client, horizon_hours=horizon_hours,
    )
    postmortem_agent = PostMortemAgent(
        _skill("postmortem"), market_data=providers.market_data, llm_router=llm_router,
        settlement_contexts=settlement_contexts,
    )

    observer = None
    if enable_observer:
        observer = Observer(
            store_a=store_a, registry_conn=_registry_conn(registry),
            ledger_writer=ObserverLedgerWriter(store_b, application_id=APPLICATION_ID),
            predicates=build_v1_registry(), clock=clock,
            outcome_mismatch_detector=outcome_mismatch_detector,
        )

    supervisor = Supervisor(
        filter_agent=filter_agent, research_agent=research_agent,
        predict_agent=predict_agent, execute_agent=execute_agent,
        postmortem_agent=postmortem_agent,
        emitter=Emitter(store_a, application_id=APPLICATION_ID),
        clock=clock, skill_pins=pins, observer=observer,
        trigger_kind="schedule",
        cycle_config={
            "cycle_time_horizon_hours": horizon_hours,
            "cycle_token_budget": token_budget,
            "log_level": "INFO",
        },
    )
    return GovernedCycle(supervisor=supervisor, skill_pins=pins, horizon_hours=horizon_hours)


def _registry_conn(registry: SkillVersionRegistry) -> sqlite3.Connection:
    conn = sqlite3.connect(registry.path)
    conn.row_factory = sqlite3.Row
    return conn
