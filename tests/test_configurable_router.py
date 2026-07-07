"""ConfigurableLLMRouter tests (Live-Operation T2).

Proves the config-selectable routing the authority requires: per-purpose provider
selection, an ordered fallback chain (Ollama primary, Groq/Gemini fallback), the
same per-cycle budget contract as the frozen router, and that agents' existing
call surface is unchanged. No network — fake in-memory clients only.
"""

from __future__ import annotations

import pytest

from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.configurable_router import ConfigurableLLMRouter
from paper_trader.llm.errors import BudgetExhaustedError
from paper_trader.llm.groq_client import LLMError, LLMRateLimitError


class StubClient:
    """LLMClient stub: returns a fixed (text, tokens) or raises a scripted error."""

    def __init__(self, name: str, text: str = "", tokens: int = 5, *, raises=None):
        self.name = name
        self._text = text
        self._tokens = tokens
        self._raises = raises
        self.calls = 0

    def complete(self, system, user, max_tokens=1000, json_mode=False):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._text, self._tokens


def _budget(limit=10_000):
    return TokenBudget(per_cycle_limit=limit)


def test_routes_purpose_to_configured_provider():
    ollama = StubClient("ollama", "from-ollama", tokens=8)
    groq = StubClient("groq", "from-groq")
    router = ConfigurableLLMRouter(
        {"bias_tagging": [ollama]},
        default=[groq],
        budget=_budget(),
    )
    text, tokens = router.call("bias_tagging", "s", "u")
    assert text == "from-ollama"
    assert tokens == 8
    assert ollama.calls == 1 and groq.calls == 0


def test_unmapped_purpose_uses_default_chain():
    ollama = StubClient("ollama", "x")
    gemini = StubClient("gemini", "default-answer")
    router = ConfigurableLLMRouter(
        {"bias_tagging": [ollama]},
        default=[gemini],
        budget=_budget(),
    )
    text, _ = router.call("summarization", "s", "u")
    assert text == "default-answer"
    assert gemini.calls == 1 and ollama.calls == 0


def test_fallback_on_provider_failure():
    down = StubClient("ollama", raises=LLMRateLimitError("429"))
    up = StubClient("groq", "fallback-answer")
    router = ConfigurableLLMRouter(
        {"classification": [down, up]},
        default=[up],
        budget=_budget(),
    )
    text, _ = router.call("classification", "s", "u")
    assert text == "fallback-answer"
    assert down.calls == 1 and up.calls == 1  # tried primary, then fell back


def test_all_providers_failing_reraises_last_error():
    a = StubClient("ollama", raises=LLMError("a down"))
    b = StubClient("groq", raises=LLMRateLimitError("b down"))
    router = ConfigurableLLMRouter(
        {"classification": [a, b]},
        default=[a],
        budget=_budget(),
    )
    with pytest.raises(LLMRateLimitError, match="b down"):
        router.call("classification", "s", "u")


def test_non_failover_error_propagates_immediately():
    boom = StubClient("ollama", raises=ValueError("bad payload"))
    never = StubClient("groq", "should-not-run")
    router = ConfigurableLLMRouter(
        {"classification": [boom, never]},
        default=[never],
        budget=_budget(),
    )
    with pytest.raises(ValueError, match="bad payload"):
        router.call("classification", "s", "u")
    assert never.calls == 0  # ValueError is not a failover error


def test_budget_consumed_on_success():
    ollama = StubClient("ollama", "ok", tokens=30)
    budget = _budget(limit=10_000)
    router = ConfigurableLLMRouter({"bias_tagging": [ollama]}, default=[ollama], budget=budget)
    router.call("bias_tagging", "s", "u")
    assert budget.used == 30  # actual tokens returned, not the max_tokens estimate


def test_budget_not_consumed_on_total_failure():
    down = StubClient("ollama", raises=LLMError("down"))
    budget = _budget(limit=10_000)
    router = ConfigurableLLMRouter({"classification": [down]}, default=[down], budget=budget)
    with pytest.raises(LLMError):
        router.call("classification", "s", "u")
    assert budget.used == 0


def test_budget_exhaustion_blocks_before_call():
    ollama = StubClient("ollama", "x", tokens=5)
    budget = _budget(limit=10)
    budget.consume(8)  # only 2 left
    router = ConfigurableLLMRouter({"bias_tagging": [ollama]}, default=[ollama], budget=budget)
    with pytest.raises(BudgetExhaustedError):
        router.call("bias_tagging", "s", "u", max_tokens=5)
    assert ollama.calls == 0  # never reached a provider


def test_empty_default_chain_rejected():
    with pytest.raises(ValueError, match="default"):
        ConfigurableLLMRouter({}, default=[], budget=_budget())


def test_empty_route_chain_rejected():
    ok = StubClient("groq", "x")
    with pytest.raises(ValueError, match="bias_tagging"):
        ConfigurableLLMRouter({"bias_tagging": []}, default=[ok], budget=_budget())


def test_call_surface_matches_frozen_router():
    # Agents call router.call(purpose, system, user, max_tokens, json_mode).
    # Same positional/keyword shape as the frozen LLMRouter — agents unchanged.
    ollama = StubClient("ollama", "ok", tokens=1)
    router = ConfigurableLLMRouter({}, default=[ollama], budget=_budget())
    text, tokens = router.call("summarization", "sys", "usr", max_tokens=50, json_mode=True)
    assert (text, tokens) == ("ok", 1)
