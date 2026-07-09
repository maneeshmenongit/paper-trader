"""Attesting single-model router for the frontier confirmation run (DT-17).

The Stage-1 caveat exists because the tiered router SILENTLY fell back to a local 7B
when the strong tier's quota died — so a "frontier" verdict could unknowingly have
run on the weak model. This wrapper makes that impossible for the confirmation run:

- **One model, no fallback chain.** It wraps exactly ONE client; there is no weaker
  tier to fall through to. A provider failure (quota, outage) RAISES — which the
  ``LLMSelector`` turns into a clean ``LLMUnavailableError`` halt — never a downgrade.
- **Per-call attestation.** Every served call records the serving ``(provider, model)``.
  ``served_models`` is the set actually used; for a valid frontier run it must be
  exactly the one intended strong model.

This is deliberately NOT the ``ConfigurableLLMRouter`` (which hides which client
served and is built to degrade). It presents the same ``SelectorRouter`` surface the
selector needs, so it drops in without touching the frozen router.
"""

from __future__ import annotations

from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.errors import BudgetExhaustedError
from paper_trader.llm.interfaces import LLMClient


class ModelDowngradeError(RuntimeError):
    """A call was served by a model other than the single intended one (DT-17)."""


class AttestingRouter:
    """Route every call to ONE client and attest the serving model.

    ``expected_model`` is the provider-qualified id we require (e.g.
    ``groq/llama-3.3-70b-versatile``). Any deviation raises ``ModelDowngradeError``;
    a provider failure propagates (no fallback), so the selector halts cleanly rather
    than downgrading.
    """

    def __init__(self, client: LLMClient, *, expected_model: str, budget: TokenBudget):
        self.client = client
        self.expected_model = expected_model
        self.budget = budget
        self.served_models: set[str] = set()
        self.calls_served = 0

    def _model_id(self) -> str:
        # Provider-qualified so "groq/llama-3.3-70b" != "ollama/llama-3.3-70b".
        model = getattr(self.client, "_model", None) or getattr(
            self.client, "_model_name", "?"
        )
        return f"{self.client.name}/{model}"

    def call(
        self,
        purpose: str,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        if not self.budget.has_capacity(estimate=max_tokens):
            raise BudgetExhaustedError(
                f"{purpose}: {max_tokens} requested, {self.budget.remaining} remaining"
            )
        served = self._model_id()
        # No fallback: a provider error propagates (→ LLMUnavailableError → clean halt).
        text, tokens = self.client.complete(system, user, max_tokens, json_mode)
        self.budget.consume(tokens)
        self.served_models.add(served)
        self.calls_served += 1
        if served != self.expected_model:
            raise ModelDowngradeError(
                f"served by {served!r}, expected {self.expected_model!r} — "
                "no silent downgrade allowed (DT-17)"
            )
        return text, tokens
