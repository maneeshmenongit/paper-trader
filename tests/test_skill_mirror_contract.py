"""Forward mirror-contract for the @v1 skills (DT-9.1, re-scoped — Wave 2).

WHY RE-SCOPED: DT-9.1 as written asserts each authored skill value equals the
value the live loop currently uses (from risk_gates.toml + Filter inline
thresholds). Neither exists yet — the domain agents and their config are unbuilt.
There is no current behavior to mirror.

So this is the forward half: lock the ratified @v1 values as an explicit contract
the FUTURE live loop must match. When Wave 3 builds the agents to read from the
registry, the SUPERSEDED banners and the value-equality (skill == live-config)
test attach at that point — this file is what they must satisfy. No risk_gates.toml
is fabricated here (that would invent the very baseline the mirror exists to
protect).

Every value below is transcribed from Appendix A and is skill content (G1): any
change is a gated fork, so this test failing means either a bad edit to a @v1
skill or an intended fork that must go through the gate — never a silent drift.
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
