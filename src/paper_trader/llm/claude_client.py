"""Anthropic Claude LLM client — implements the LLMClient Protocol.

Application-owned (NOT oracle-provenance): added for the Stage 1 frontier
confirmation run, which needs a strong reasoner for the ``predict_selection``
purpose once the free tiers (Groq quota) are exhausted. Wired into the tiered
router via ``llm/model_tiers.build_client``.

Matches the frozen ``LLMClient`` surface: ``complete(system, user, max_tokens,
json_mode) -> (text, tokens)``. Sonnet 5 / Opus 4.8 semantics: no ``temperature``
(rejected), adaptive thinking on by default. ``json_mode`` is a soft hint here — the
selector prompt already instructs "ONLY compact JSON" and the caller's parser
tolerates prose around the object, so we do NOT use ``output_config.format`` (its
strict schema would pin the exact keys and couple this client to one purpose).
"""

from __future__ import annotations

from anthropic import Anthropic
from anthropic.types import TextBlock

from paper_trader.llm.groq_client import LLMError, LLMRateLimitError


class ClaudeClient:
    """Live Anthropic client. Default model is Sonnet 5 (strong + cost-effective)."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self.name = "claude"
        self._model = model
        self._client = Anthropic(api_key=api_key)

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        # json_mode is a soft hint (see module docstring): reinforce it in the
        # system prompt rather than via a strict schema.
        sys_prompt = system
        if json_mode:
            sys_prompt = f"{system}\n\nRespond with ONLY the JSON object, no other text."

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:  # noqa: BLE001 — classify then re-raise as domain errors
            err_str = str(e).lower()
            if "429" in err_str or "rate_limit" in err_str or "overloaded" in err_str:
                raise LLMRateLimitError(f"Claude rate limited: {e}") from e
            raise LLMError(f"Claude error: {e}") from e

        # A safety refusal returns stop_reason='refusal' with empty content.
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined the request (safety refusal)")

        text = "".join(
            block.text for block in response.content if isinstance(block, TextBlock)
        )
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens_used
