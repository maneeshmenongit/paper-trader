"""DT-12.5 — the governance acceptance test (Wave 6 Task 4).

The Phase 4 definition of done: ONE walk of the conservative-cap path through the
REAL machinery (emission, observer, proposer, gate, fork, replay), every
governance component exercised once. Only market inputs are controlled by
deterministic fakes; the @v2 content is human-authored and supplied at approve.

    (a) pre-fork cycle under predict@v1 -> actionable View, emitted to Store A
    (b) settle as a controlled MISS -> real observer emits an outcome-mismatch
        entry to Store B citing the settling PostMortem invocation
    (c) real proposer reads Store B -> drafts a PROPOSED proposal citing it
    (d) real gate approves (note + human @v2 content) -> atomic fork @v1->@v2 +
        pointer flip + window + IN_WINDOW
    (e) post-fork cycle -> its Predict invocation pins predict@v2
    (f) replay both cycles: both reconstruct, all pins VERIFIED, the Predict pin
        differs across the fork (@v1 pre, @v2 post)
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from paper_trader.agents.execute import ExecuteAgent
from paper_trader.agents.filter import FilterAgent
from paper_trader.agents.postmortem import PostMortemAgent
from paper_trader.agents.predict import PredictAgent
from paper_trader.agents.research import ResearchAgent
from paper_trader.domain import Asset, PaperPortfolio, PaperTrade
from paper_trader.emission import Emitter
from paper_trader.graph.state import CycleState
from paper_trader.graph.supervisor import Supervisor
from paper_trader.officer_predicates import build_v1_registry, outcome_mismatch_detector
from steward.officer.gate import Gate
from steward.officer.observer import Observer, ObserverLedgerWriter
from steward.officer.proposer import Proposer
from steward.officer.replay import VERIFIED, Replay
from steward.storage.proposals import ProposalStore
from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA
from steward.storage.store_b import StoreB
from tests.fixtures.fakes import (
    FakeCompanyNews,
    FakeLLMRouter,
    FakeMarketData,
    FakeTradingClient,
    FrozenClock,
    make_ohlcv,
)

NOW = datetime(2026, 7, 6, 15, 0, tzinfo=UTC)
PRE_CID = "01DT125PREFORKCYCLE0000AA"
POST_CID = "01DT125POSTFORKCYCLE000AA"
PREDICT_V1 = version_id_for("predict")
PREDICT_V2 = "paper-trader/predict/predict@v2"
V2_CONTENT = (
    "mandate: predict (conservative cap)\n"
    "constraints:\n"
    "  - id: C1\n"
    "    text: a View requires confidence >= 0.65\n"  # human-authored fork
)


def _load(reg, agent):
    with reg.connection() as conn:
        return load_skill(conn, version_id_for(agent))


def _fresh_bars(close_last=130.0):
    bars = make_ohlcv([100.0] * 24 + [close_last])
    for i, b in enumerate(reversed(bars)):
        b.timestamp = NOW - timedelta(minutes=5) - timedelta(hours=i)
    return bars


def _observer(store_a, store_b, reg_conn, clock):
    return Observer(
        store_a=store_a, registry_conn=reg_conn,
        ledger_writer=ObserverLedgerWriter(store_b, application_id="paper-trader"),
        predicates=build_v1_registry(), clock=clock,
        outcome_mismatch_detector=outcome_mismatch_detector,
    )


def _supervisor(reg, store_a, store_b, *, clock, quotes, pins, observer=None, cfg=None):
    md = FakeMarketData(quotes=quotes, ohlcv={"AAPL": _fresh_bars()})
    router = FakeLLMRouter(responses={"classification": "ai", "summarization": "s"})
    trading = FakeTradingClient()
    return Supervisor(
        filter_agent=FilterAgent(_load(reg, "filter"), clock=clock,
                                 market_data=md, trading_client=trading),
        research_agent=ResearchAgent(
            _load(reg, "research"), clock=clock, market_data=md,
            company_news=FakeCompanyNews(news={"AAPL": []}), llm_router=router),
        predict_agent=PredictAgent(_load(reg, "predict")),
        execute_agent=ExecuteAgent(_load(reg, "execute"), clock=clock, trading_client=trading),
        postmortem_agent=PostMortemAgent(_load(reg, "postmortem"),
                                         market_data=md, llm_router=router),
        emitter=Emitter(store_a, application_id="paper-trader"),
        clock=clock, skill_pins=pins, observer=observer,
        cycle_config=cfg or {"cycle_time_horizon_hours": 24, "cycle_token_budget": 15000,
                             "log_level": "INFO"},
    )


def _pins(predict_version):
    pins = {a: version_id_for(a) for a in
            ("filter", "research", "execute", "postmortem")}
    pins["predict"] = predict_version   # the version Predict actually ran under
    return pins


def _reg_conn(reg):
    conn = sqlite3.connect(reg.path)
    conn.row_factory = sqlite3.Row
    return conn


async def test_dt125_governance_acceptance_walk(tmp_path):
    store_a = StoreA(tmp_path / "store_a.sqlite")
    store_b = StoreB(tmp_path / "store_b.sqlite")
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    proposals = ProposalStore(tmp_path / "proposals.sqlite")
    seed_v1_skills(reg, created_at="2026-07-05T00:00:00Z")
    reg.set_current_version(application_id="paper-trader", agent_name="predict",
                            skill_name="predict", current_version_id=PREDICT_V1,
                            updated_at=NOW.isoformat())
    clock = FrozenClock(now=NOW, market_open=True)

    # ── (a) PRE-FORK cycle under predict@v1 -> actionable View, emitted ──
    obs_a = _observer(store_a, store_b, _reg_conn(reg), clock)
    sup_a = _supervisor(reg, store_a, store_b, clock=clock, quotes={"AAPL": 130.0},
                        pins=_pins(PREDICT_V1), observer=obs_a)
    state_a = CycleState(
        cycle_id=PRE_CID, started_at=NOW, portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1")
    state_a = await sup_a.run_cycle(state_a)
    assert state_a.trade_decisions["AAPL"].executed is True   # actionable View traded
    with store_a.connection() as c:
        pre_predict = c.execute(
            "SELECT skill_version_id FROM agent_invocations "
            "WHERE cycle_id=? AND agent_name='predict'", (PRE_CID,)).fetchone()
    assert pre_predict["skill_version_id"] == PREDICT_V1   # pinned @v1

    # ── (b) settle as a controlled MISS -> observer emits outcome-mismatch ──
    settling_clock = FrozenClock(now=NOW + timedelta(hours=25), market_open=True)
    obs_b = _observer(store_a, store_b, _reg_conn(reg), settling_clock)
    settle_cid = "01DT125SETTLECYCLE00000AA"
    # a losing trade to settle: exit (90) < entry (100) -> a MISS
    losing = PaperTrade(prediction_id="AAPL", symbol="AAPL", entry_price=100.0,
                        quantity=10, notional_value=1000.0, entry_time=NOW,
                        expected_exit_time=NOW + timedelta(hours=24))
    sup_b = _supervisor(reg, store_a, store_b, clock=settling_clock,
                        quotes={"AAPL": 90.0}, pins=_pins(PREDICT_V1), observer=obs_b)
    state_b = CycleState(
        cycle_id=settle_cid, started_at=settling_clock.now(),
        portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        pending_settlements=[losing], calibration_version="identity-v1")
    state_b = await sup_b.run_cycle(state_b)
    # PostMortem scored a miss
    assert any(pm.direction_correct is False for pm in state_b.new_post_mortems)
    # the REAL observer wrote an outcome-mismatch entry citing the PM invocation
    with store_b.connection() as c:
        entries = c.execute(
            "SELECT * FROM ledger_entries WHERE observation_type='outcome-mismatch'"
        ).fetchall()
    assert entries, "observer must emit an outcome-mismatch entry"
    mismatch = entries[0]
    assert mismatch["cycle_id"] == settle_cid
    assert mismatch["invocation_id"] is not None       # cites the settling PM invocation

    # ── (c) REAL proposer reads Store B -> PROPOSED citing that evidence ──
    proposer = Proposer(store_b=store_b, proposal_store=proposals,
                        application_id="paper-trader", clock=clock)
    pid = proposer.propose(
        proposal_id="prop-1", target_skill="paper-trader/predict/predict",
        base_version_id=PREDICT_V1,
        proposed_change={"raise_threshold": "0.60 -> 0.65"}, complexity_tag="high")
    rec = proposals.get(pid)
    assert rec["status"] == "PROPOSED"
    assert mismatch["entry_id"] in rec["evidence_refs"]   # cites the real evidence

    # ── (d) REAL gate approves -> atomic fork @v1->@v2 + flip + IN_WINDOW ──
    gate_show = Gate(proposal_store=proposals, store_b=store_b, registry=reg,
                     clock=clock, session="review-session")
    gate_show.show(pid)   # first view (high complexity -> cooling-off requires it)
    gate_approve = Gate(proposal_store=proposals, store_b=store_b, registry=reg,
                        clock=clock, session="approve-session")   # different session
    new_vid = gate_approve.approve(
        proposal_id=pid, decided_by="alice",
        decision_note="the miss run justifies a conservative cap", new_version_id=PREDICT_V2,
        new_content=V2_CONTENT)
    assert new_vid == PREDICT_V2
    with reg.connection() as c:
        v2 = c.execute("SELECT * FROM skill_versions WHERE version_id=?", (PREDICT_V2,)).fetchone()
    assert v2["parent_version_id"] == PREDICT_V1 and v2["origin"] == "slow-loop-fork"
    assert v2["validation_status"] == "UNVALIDATED"
    assert reg.get_current_version_id(application_id="paper-trader", agent_name="predict",
                                      skill_name="predict") == PREDICT_V2   # pointer flipped
    assert proposals.get(pid)["status"] == "IN_WINDOW"

    # ── (e) POST-FORK cycle -> its Predict invocation pins predict@v2 ──
    obs_e = _observer(store_a, store_b, _reg_conn(reg), clock)
    sup_e = _supervisor(reg, store_a, store_b, clock=clock, quotes={"AAPL": 130.0},
                        pins=_pins(PREDICT_V2), observer=obs_e)   # now loads @v2
    state_e = CycleState(
        cycle_id=POST_CID, started_at=NOW, portfolio=PaperPortfolio(cash_balance=10_000.0),
        watchlist=[Asset(symbol="AAPL", kind="stock", sector="tech")],
        calibration_version="identity-v1")
    await sup_e.run_cycle(state_e)
    with store_a.connection() as c:
        post_predict = c.execute(
            "SELECT skill_version_id FROM agent_invocations "
            "WHERE cycle_id=? AND agent_name='predict'", (POST_CID,)).fetchone()
    assert post_predict["skill_version_id"] == PREDICT_V2   # pinned @v2

    # ── (f) REPLAY both cycles: reconstruct, all VERIFIED, pins differ ──
    replay = Replay(store_a_path=store_a.path, store_b_path=store_b.path,
                    registry_path=reg.path)
    pre = replay.reconstruct(PRE_CID)
    post = replay.reconstruct(POST_CID)
    assert pre.header is not None and post.header is not None
    assert pre.all_verified and post.all_verified       # hashes verify both sides
    pre_pin = next(i.skill_version_id for i in pre.invocations if i.agent_name == "predict")
    post_pin = next(i.skill_version_id for i in post.invocations if i.agent_name == "predict")
    assert pre_pin == PREDICT_V1
    assert post_pin == PREDICT_V2
    assert pre_pin != post_pin                          # the fork is visible in replay
    # each cycle shows ITS OWN skill text
    pre_predict_inv = next(i for i in pre.invocations if i.agent_name == "predict")
    post_predict_inv = next(i for i in post.invocations if i.agent_name == "predict")
    assert "0.65" in post_predict_inv.skill_content     # @v2 conservative cap
    assert "0.65" not in (pre_predict_inv.skill_content or "").replace("0.60", "")
    assert all(i.trust == VERIFIED for i in pre.invocations + post.invocations)
