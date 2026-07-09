"""Fast/reasoning model-tier routing (framework capability)."""

from __future__ import annotations

import pytest

from paper_trader.live.config import LiveConfig
from paper_trader.live.providers import build_tiered_router
from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.model_tiers import (
    REASONING_PURPOSES,
    build_client,
    tier_of,
)


def _config(**over) -> LiveConfig:
    base = dict(
        live_mode=True, llm_provider="ollama",
        ollama_endpoint="http://localhost:11434", ollama_model="llama3.1:8b",
        openrouter_model="x",
    )
    base.update(over)
    return LiveConfig(**base)


# ─── tier classification ─────────────────────────────────────────────────

def test_predict_selection_is_reasoning():
    assert tier_of("predict_selection") == "reasoning"


def test_mechanical_purposes_are_fast():
    for p in ("classification", "summarization", "bias_tagging"):
        assert tier_of(p) == "fast"


def test_reasoning_purposes_frozenset():
    assert "predict_selection" in REASONING_PURPOSES


# ─── build_client ────────────────────────────────────────────────────────

def test_build_client_groq_requires_key():
    with pytest.raises(ValueError, match="groq"):
        build_client("groq", config=_config(groq_api_key=""))


def test_build_client_groq_ok():
    c = build_client("groq", model="llama-3.3-70b-versatile", config=_config(groq_api_key="k"))
    assert c.name == "groq"


def test_build_client_ollama_no_key_needed():
    c = build_client("ollama", config=_config())
    assert c.name == "ollama"


def test_build_client_unknown_provider():
    with pytest.raises(ValueError, match="unknown LLM provider"):
        build_client("mistral", config=_config())


def test_build_client_claude_requires_key():
    with pytest.raises(ValueError, match="claude"):
        build_client("claude", config=_config(anthropic_api_key=""))


def test_build_client_claude_ok():
    c = build_client("claude", model="claude-sonnet-5", config=_config(anthropic_api_key="k"))
    assert c.name == "claude"


def test_build_client_anthropic_alias():
    c = build_client("anthropic", config=_config(anthropic_api_key="k"))
    assert c.name == "claude"


# ─── build_tiered_router: separate fast vs reasoning chains ──────────────

def test_reasoning_routed_to_its_own_provider():
    cfg = _config(reasoning_provider="groq", groq_api_key="k")
    router = build_tiered_router(cfg, TokenBudget(per_cycle_limit=1000))
    fast_chain = router.routes["classification"]
    reasoning_chain = router.routes["predict_selection"]  # type: ignore[index]
    # Reasoning leads with a DIFFERENT (groq) client than the fast primary (ollama).
    assert reasoning_chain[0].name == "groq"
    assert fast_chain[0].name == "ollama"
    # And degrades to the fast chain after the reasoning lead.
    assert reasoning_chain[1:] == fast_chain


def test_reasoning_falls_back_to_fast_when_unset():
    cfg = _config(reasoning_provider="")  # no separate reasoning tier
    router = build_tiered_router(cfg, TokenBudget(per_cycle_limit=1000))
    # Reasoning purposes reuse the fast chain (single-tier behavior).
    assert router.routes["predict_selection"] == router.routes["classification"]  # type: ignore[index]


def test_fast_purposes_never_hit_reasoning_provider():
    cfg = _config(reasoning_provider="groq", groq_api_key="k")
    router = build_tiered_router(cfg, TokenBudget(per_cycle_limit=1000))
    # classification (fast) must lead with the fast primary, not groq.
    assert router.routes["classification"][0].name == "ollama"
