"""Groq LLM client — implements LLMClient Protocol."""

# ─── PROVENANCE ───────────────────────────────────────────────────────
# Copied verbatim from oracle-agents @ b14b8f5cde141a35c6708b17cc3ebd95e5ad3967
# on 2026-06-23 as part of paper-trader T01 scaffolding.
#
# DO NOT EDIT INDEPENDENTLY. When oracle-agents updates this file,
# sync the change here. Eventual extraction to a shared
# worldwise-core package is tracked in ADR-PT-001.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations

from groq import Groq


class LLMRateLimitError(Exception):
    pass


class LLMError(Exception):
    pass


class GroqClient:
    """Live Groq client using the groq SDK."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.name = "groq"
        self._model = model
        self._client = Groq(api_key=api_key)

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str:
                raise LLMRateLimitError(f"Groq rate limited: {e}") from e
            raise LLMError(f"Groq error: {e}") from e

        text = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        return text, tokens_used
