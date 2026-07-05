"""Invocation emission tests (Wave 3 Task 3, DT-4.3). Fakes only; non-blocking.

Invocations are BUFFERED at each boundary and flushed after the cycle header
(agent_invocations.cycle_id FKs to cycle_headers — header must land first). Each
test that wants rows on disk emits a header to trigger the flush.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_trader.domain import Asset, PaperPortfolio
from paper_trader.emission import Emitter
from paper_trader.graph.emit_boundary import run_agent_with_emission
from paper_trader.graph.state import CycleState
from steward.storage.store_a import StoreA
from tests.fixtures.fakes import FrozenClock

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
CID = "01CYCLEIDULID00000000000000"


class _StubAgent:
    name = "filter"
    writes = ["tradeable_assets"]

    async def run(self, state: CycleState) -> CycleState:
        state.tradeable_assets = [Asset(symbol="AAPL", kind="stock")]
        return state


def _state():
    return CycleState(
        cycle_id=CID, started_at=NOW,
        portfolio=PaperPortfolio(cash_balance=1.0),
        watchlist=[Asset(symbol="AAPL", kind="stock")],
        calibration_version="identity-v1",
    )


def _emit_header(emitter):
    emitter.emit_cycle_header(
        cycle_id=CID, started_at=NOW.isoformat(), ended_at=NOW.isoformat(),
        trigger_kind="manual", orchestrator_input={}, orchestrator_decision={},
        decision_mode="rule", orchestrator_rationale=None, status="completed",
    )


@pytest.fixture
def store_a(tmp_path):
    return StoreA(tmp_path / "store_a.sqlite")


async def test_emits_one_invocation_with_pin(store_a):
    emitter = Emitter(store_a, application_id="paper-trader")
    state = await run_agent_with_emission(
        _StubAgent(), _state(), emitter=emitter, clock=FrozenClock(now=NOW),
        skill_version_id="paper-trader/filter/filter@v1", invocation_seq=0,
    )
    assert "filter" in state.completed_agents        # write-enforcement ran
    _emit_header(emitter)                             # flush the buffer
    with store_a.connection() as conn:
        rows = conn.execute("SELECT * FROM agent_invocations").fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["agent_name"] == "filter"
    assert r["skill_version_id"] == "paper-trader/filter/filter@v1"
    assert r["application_id"] == "paper-trader"
    assert r["cycle_id"] == CID
    assert r["status"] == "completed"
    assert r["agent_input"] is not None and r["agent_output"] is not None


async def test_output_captures_written_field(store_a):
    emitter = Emitter(store_a, application_id="paper-trader")
    await run_agent_with_emission(
        _StubAgent(), _state(), emitter=emitter, clock=FrozenClock(now=NOW),
        skill_version_id="pin", invocation_seq=1,
    )
    _emit_header(emitter)
    with store_a.connection() as conn:
        r = conn.execute("SELECT agent_output FROM agent_invocations").fetchone()
    assert "AAPL" in r["agent_output"]  # produced tradeable asset frozen in


async def test_disabled_emitter_writes_nothing(store_a):
    emitter = Emitter(None, application_id="paper-trader")  # emission OFF
    state = await run_agent_with_emission(
        _StubAgent(), _state(), emitter=emitter, clock=FrozenClock(now=NOW),
        skill_version_id="pin", invocation_seq=0,
    )
    assert "filter" in state.completed_agents  # agent still ran (behavior-neutral)
    with store_a.connection() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM agent_invocations").fetchone()["c"]
    assert n == 0


async def test_emission_failure_is_non_blocking(store_a):
    class _BoomStore:
        def insert_agent_invocation(self, **kw):
            raise RuntimeError("disk full")

        def insert_cycle_header(self, **kw):
            return None  # header ok, invocation flush blows up

    emitter = Emitter(_BoomStore(), application_id="paper-trader")
    state = await run_agent_with_emission(
        _StubAgent(), _state(), emitter=emitter, clock=FrozenClock(now=NOW),
        skill_version_id="pin", invocation_seq=0,
    )
    assert "filter" in state.completed_agents  # the agent completed regardless
    _emit_header(emitter)                       # flush attempts -> records failure
    assert emitter.failed_emissions == [f"invocation:filter:{CID}:000"]


async def test_invocation_id_is_ordered_within_cycle(store_a):
    emitter = Emitter(store_a, application_id="paper-trader")
    for seq in range(3):
        await run_agent_with_emission(
            _StubAgent(), _state(), emitter=emitter, clock=FrozenClock(now=NOW),
            skill_version_id="pin", invocation_seq=seq,
        )
    _emit_header(emitter)
    with store_a.connection() as conn:
        ids = [r["invocation_id"] for r in
               conn.execute("SELECT invocation_id FROM agent_invocations "
                            "ORDER BY invocation_id").fetchall()]
    assert ids == sorted(ids)
    assert ids[0].endswith(":000") and ids[2].endswith(":002")
