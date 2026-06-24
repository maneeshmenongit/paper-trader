"""Gemini LLM client — implements LLMClient Protocol.

Uses the new google-genai SDK (successor to google-generativeai).
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

from google import genai
from google.genai import types

from paper_trader.llm.groq_client import LLMError, LLMRateLimitError


class GeminiClient:
    """Live Gemini client using the google-genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.name = "gemini"
        self._model_name = model
        self._client = genai.Client(api_key=api_key)

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> tuple[str, int]:
        gen_config: dict = {"max_output_tokens": max_tokens}
        if json_mode:
            gen_config["response_mime_type"] = "application/json"
        if temperature is not None:
            gen_config["temperature"] = temperature
        # Disable thinking for 2.5 models to get clean JSON output
        gen_config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    **gen_config,
                ),
            )
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "rate" in err_str:
                raise LLMRateLimitError(f"Gemini rate limited: {e}") from e
            raise LLMError(f"Gemini error: {e}") from e

        # Extract text from non-thought parts only
        text = ""
        if response.candidates:
            content = response.candidates[0].content
            if content and content.parts:
                for part in content.parts:
                    if not getattr(part, "thought", False):
                        text += part.text or ""
        if not text:
            text = response.text or ""
        tokens_used = 0
        if response.usage_metadata:
            tokens_used = response.usage_metadata.total_token_count or 0
        return text, tokens_used
