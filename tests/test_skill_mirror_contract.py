"""Mirror-contract for the @v1 skills (DT-9.1).

Two layers:
1. FORWARD contract (Wave 2 origin): the ratified @v1 values are locked as skill
   content; a change is a gated fork, so a failure means a bad skill edit or an
   ungated fork — never silent drift.
2. VALUE-EQUALITY upgrade (Wave 2.5 Task 9, bottom of file): now that the live
   agents exist and parse their effective values FROM the loaded skill, the
   contract is upgraded to assert the LIVE agents' effective values equal the
   ratified skill values. This is the real DT-9.1 assertion — achievable now by
   construction because the agents carry no inline thresholds. No risk_gates.toml
   is fabricated (the earlier hard-stop: there is no such baseline; the agents
   ARE the baseline, driven by the skills).
"""

from __future__ import annotations

import pytest

from steward.storage.seed_skills import seed_v1_skills, version_id_for
from steward.storage.skill_loader import load_skill
from steward.storage.skill_version import SkillVersionRegistry

CREATED_AT = "2026-07-04T00:00:00Z"


@pytest.fixture
def loaded(tmp_path):
    """Seed the five @v1 skills and return a dict agent -> loaded skill."""
    reg = SkillVersionRegistry(tmp_path / "skills.sqlite")
    seed_v1_skills(reg, created_at=CREATED_AT)
    out = {}
    with reg.connection() as conn:
        for agent in ("predict", "filter", "research", "execute", "postmortem"):
            out[agent] = load_skill(conn, version_id_for(agent))
    return out


def _rule(skill, rule_id: str) -> str:
    return next(r["text"] for r in skill["rules"] if r["id"] == rule_id)


def _constraint(skill, cid: str) -> str:
    return next(c["text"] for c in skill["constraints"] if c["id"] == cid)


# ─── Filter — DT-15.1 ratified liquidity floor ───────────────────────────

def test_filter_liquidity_floor(loaded):
    r2 = _rule(loaded["filter"], "R2")
    assert "20-day average daily dollar volume ≥ $10M (stocks)" in r2
    assert "24h volume ≥ $50M (crypto)" in r2


def test_filter_quote_freshness(loaded):
    assert "fresher than 60 minutes" in _rule(loaded["filter"], "R4")


# ─── Execute — the dissolved risk_gates.toml values ──────────────────────

def test_execute_sizing_values(loaded):
    sizing = _rule(loaded["execute"], "sizing")
    assert "fractional Kelly 0.25" in sizing
    assert "max position 5% of portfolio" in sizing
    assert "min notional $100" in sizing


def test_execute_exposure_values(loaded):
    exposure = _rule(loaded["execute"], "exposure")
    assert "max total exposure 60% of portfolio" in exposure
    assert "max 3 same-sector positions" in exposure
    assert "max 10 open positions" in exposure


def test_execute_loss_halt(loaded):
    assert "daily simulated loss > 5%" in _rule(loaded["execute"], "loss_halt")


def test_execute_confidence_and_magnitude_gates(loaded):
    gate = _rule(loaded["execute"], "execution_gates")
    # DT-15.2 ruling: gate kept at 0.55 (not removed, not changed).
    assert "require confidence ≥ 0.55" in gate
    assert "require expected magnitude ≥ 0.5%" in gate


# ─── Predict — I-10 confidence threshold ─────────────────────────────────

def test_predict_confidence_threshold(loaded):
    assert "confidence ≥ 0.60" in _constraint(loaded["predict"], "C1")


# ─── Research — call budget (the value; the semaphore bounds are config) ──

def test_research_call_budget(loaded):
    assert "at most 1 Groq + 1 Gemini call per asset" in _constraint(loaded["research"], "C1")


# ─── PostMortem — bias-tag batch ratio ───────────────────────────────────

def test_postmortem_bias_batch(loaded):
    assert "~1 call per 4 settlements" in _rule(loaded["postmortem"], "R3")


# ─── The two ratified edits are locked; PENDING markers stay gone ────────

def test_no_pending_markers_leaked(loaded):
    import yaml

    reg_paths = {}
    for agent, skill in loaded.items():
        # re-serialize the loaded structure and confirm no doc-tracking markers
        text = yaml.safe_dump({k: _plain(v) for k, v in skill.items()},
                              allow_unicode=True)
        assert "PENDING" not in text, agent
        assert "DT-15.1" not in text, agent
        assert "DT-15.2" not in text, agent
        reg_paths[agent] = text
    assert set(reg_paths) == {"predict", "filter", "research", "execute", "postmortem"}


def _plain(value):
    """Recursively convert MappingProxyType/tuple back to dict/list for dump."""
    from types import MappingProxyType

    if isinstance(value, MappingProxyType):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    return value


# ─────────────────────────────────────────────────────────────────────────
# DT-9.1 VALUE-EQUALITY UPGRADE (Wave 2.5 Task 9).
#
# Now that the live agents parse their effective risk/threshold values FROM the
# loaded skill, the forward contract above is upgraded to the real DT-9.1 assert:
# the LIVE agents' effective values equal the ratified skill values. Achievable
# by construction — the agents have no inline thresholds, so equality here proves
# the running loop is driven by exactly the ratified numbers. A future gated fork
# of any value flips both the skill and this assertion together.
# ─────────────────────────────────────────────────────────────────────────

def test_live_filter_agent_floors_equal_skill(loaded):
    from paper_trader.agents.filter import FilterAgent
    from tests.fixtures.fakes import FakeMarketData, FakeTradingClient, FrozenClock

    agent = FilterAgent(
        loaded["filter"],
        clock=FrozenClock(),
        market_data=FakeMarketData(),
        trading_client=FakeTradingClient(),
    )
    assert agent.stock_floor == 10_000_000.0    # $10M
    assert agent.crypto_floor == 50_000_000.0   # $50M
    assert agent.freshness_minutes == 60


def test_live_execute_params_equal_skill(loaded):
    from paper_trader.agents.skill_params import ExecuteParams

    p = ExecuteParams(loaded["execute"])
    assert p.kelly_fraction == 0.25
    assert p.max_position_pct == 0.05
    assert p.min_notional == 100.0
    assert p.max_total_exposure_pct == 0.60
    assert p.max_same_sector == 3
    assert p.max_open_positions == 10
    assert p.daily_loss_halt_pct == 0.05
    assert p.min_confidence == 0.55           # DT-15.2 floor, kept
    assert p.min_magnitude_pct == 0.005       # 0.5%


def test_live_predict_agent_threshold_equals_skill(loaded):
    from paper_trader.agents.predict import PredictAgent

    agent = PredictAgent(loaded["predict"])
    assert agent.confidence_threshold == 0.60  # I-10
    # provisional roster is reported honestly against the declared roster
    assert agent.declared_roster == ["momentum", "mean_reversion", "arima"]
    assert agent.implemented == ["momentum"]
