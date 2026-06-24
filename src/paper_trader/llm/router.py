"""LLM router — picks provider based on call purpose and enforces budget.

Agents never know which provider they got. They call router.call(purpose=...)
and get back (text, tokens_used). This is the LLM-provider-agnostic abstraction
that the broader World Agents framework should adopt.
"""

# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations

from paper_trader.llm.budget import TokenBudget
from paper_trader.llm.errors import BudgetExhaustedError
from paper_trader.llm.interfaces import LLMClient, LLMPurpose


class LLMRouter:
    def __init__(self, groq: LLMClient, gemini: LLMClient, budget: TokenBudget):
        self.groq = groq
        self.gemini = gemini
        self.budget = budget

    def call(
        self,
        purpose: LLMPurpose,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        if not self.budget.has_capacity(estimate=max_tokens):
            raise BudgetExhaustedError(
                f"Cannot satisfy {purpose} call: {max_tokens} requested, "
                f"{self.budget.remaining} remaining"
            )

        # Fast/cheap → Groq; quality/long-context → Gemini
        if purpose in ("routing", "classification", "bias_tagging"):
            client = self.groq
        else:
            client = self.gemini

        text, tokens = client.complete(system, user, max_tokens, json_mode)
        self.budget.consume(tokens)
        return text, tokens
