"""Attesting single-model router (frontier confirm, DT-17 no-silent-downgrade)."""

from __future__ import annotations

import pytest

from paper_trader.backtest.attesting_router import (
    AttestingRouter,
    ModelDowngradeError,
)
from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.groq_client import LLMError


class _Client:
    def __init__(self, name="groq", model="llama-3.3-70b-versatile", fail=False, tokens=100):
        self.name = name
        self._model = model
        self.fail = fail
        self.tokens = tokens

    def complete(self, system, user, max_tokens=1000, json_mode=False):
        if self.fail:
            raise LLMError("provider down")
        return '{"method":"momentum","confidence":0.9,"rationale":"x"}', self.tokens


def _router(client, expected):
    return AttestingRouter(client, expected_model=expected,
                           budget=TokenBudget(per_cycle_limit=1_000_000))


def test_serves_and_attests_the_expected_model():
    r = _router(_Client(), "groq/llama-3.3-70b-versatile")
    txt, tok = r.call("predict_selection", "sys", "user", max_tokens=200)
    assert "momentum" in txt
    assert r.served_models == {"groq/llama-3.3-70b-versatile"}
    assert r.calls_served == 1


def test_raises_on_unexpected_model():
    # Client is qwen 7B but we expected the frontier model → downgrade error.
    r = _router(_Client(name="ollama", model="qwen2.5:7b"), "groq/llama-3.3-70b-versatile")
    with pytest.raises(ModelDowngradeError):
        r.call("predict_selection", "sys", "user")


def test_no_fallback_provider_error_propagates():
    # A provider failure must RAISE (no downgrade), so the selector halts cleanly.
    r = _router(_Client(fail=True), "groq/llama-3.3-70b-versatile")
    with pytest.raises(LLMError):
        r.call("predict_selection", "sys", "user")


def test_budget_enforced():
    r = AttestingRouter(_Client(), expected_model="groq/llama-3.3-70b-versatile",
                        budget=TokenBudget(per_cycle_limit=50))
    from paper_trader.llm.errors import BudgetExhaustedError
    with pytest.raises(BudgetExhaustedError):
        r.call("predict_selection", "sys", "user", max_tokens=200)


def test_gemini_model_attr_resolved():
    # Gemini uses _model_name (not _model); attestation must still resolve it.
    class Gem:
        name = "gemini"
        _model_name = "gemini-2.5-flash"

        def complete(self, s, u, mt=1000, jm=False):
            return '{"method":"arima","confidence":0.8,"rationale":"y"}', 90

    r = _router(Gem(), "gemini/gemini-2.5-flash")
    r.call("predict_selection", "sys", "user")
    assert r.served_models == {"gemini/gemini-2.5-flash"}
