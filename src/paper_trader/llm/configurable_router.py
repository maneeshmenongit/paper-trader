"""Config-selectable LLM router (Live-Operation T2).

Lives ALONGSIDE the frozen oracle-provenance ``LLMRouter`` (llm/router.py), which
hardwires ``groq``/``gemini`` per purpose and must not be edited in place. This
router adds what T2 needs and the frozen one cannot express: a **per-purpose
provider selection** driven by config, with an ordered **fallback chain** so a
provider miss (rate-limit / outage) degrades to the next provider instead of
failing the call.

It presents the SAME surface agents already use —
``call(purpose, system, user, max_tokens, json_mode) -> (text, tokens)`` — and
enforces the SAME per-cycle ``TokenBudget``. Agents are therefore unchanged;
which provider serves a purpose is a config decision (wired in T3), not an agent
decision.

Authority (§3 T2): route Research (classification + summarization) and PostMortem
(bias_tagging) to Ollama, keeping Groq/Gemini as fallback. Predict is NOT routed
here — its selector is not built and it makes no LLM calls; nothing in this router
engages a Predict path.
"""

from __future__ import annotations

from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.errors import BudgetExhaustedError
from paper_trader.llm.groq_client import LLMError, LLMRateLimitError
from paper_trader.llm.interfaces import LLMClient, LLMPurpose

# Errors worth failing OVER to the next provider (transient/provider-side). A
# programming error (e.g. a bad payload) is not in here — it propagates.
_FAILOVER_ERRORS: tuple[type[BaseException], ...] = (LLMError, LLMRateLimitError)


class ConfigurableLLMRouter:
    """Route each purpose to a config-chosen ordered chain of ``LLMClient``s.

    ``routes`` maps a purpose to the ordered list of clients to try. ``default``
    is the chain used for any purpose not explicitly mapped. The first client that
    returns wins; on a failover-eligible error the next client is tried; if all
    fail, the last error propagates.
    """

    def __init__(
        self,
        routes: dict[LLMPurpose, list[LLMClient]],
        *,
        default: list[LLMClient],
        budget: TokenBudget,
    ):
        if not default:
            raise ValueError("default provider chain must be non-empty")
        for purpose, chain in routes.items():
            if not chain:
                raise ValueError(f"provider chain for {purpose!r} must be non-empty")
        self.routes = routes
        self.default = default
        self.budget = budget

    def _chain_for(self, purpose: LLMPurpose) -> list[LLMClient]:
        return self.routes.get(purpose, self.default)

    def call(
        self,
        purpose: LLMPurpose,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        # Budget check mirrors the frozen router exactly: reserve BEFORE the call.
        if not self.budget.has_capacity(estimate=max_tokens):
            raise BudgetExhaustedError(
                f"Cannot satisfy {purpose} call: {max_tokens} requested, "
                f"{self.budget.remaining} remaining"
            )

        chain = self._chain_for(purpose)
        last_exc: BaseException | None = None
        for client in chain:
            try:
                text, tokens = client.complete(system, user, max_tokens, json_mode)
            except _FAILOVER_ERRORS as exc:
                last_exc = exc
                continue  # provider miss → try the next in the chain
            self.budget.consume(tokens)
            return text, tokens

        # Every provider in the chain failed over — surface the last real error.
        assert last_exc is not None  # chain is non-empty by construction
        raise last_exc
