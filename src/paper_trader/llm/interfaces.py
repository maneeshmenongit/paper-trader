# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

LLMPurpose = Literal[
    "routing", "classification", "reasoning", "summarization", "bias_tagging"
]


@runtime_checkable
class LLMClient(Protocol):
    name: str

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:  # (text, tokens_used)
        ...
