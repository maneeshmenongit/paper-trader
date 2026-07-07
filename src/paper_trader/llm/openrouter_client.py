"""OpenRouter hosted open-weight LLM client (Live-Operation T2).

The "no-hardware middle path" the authority names (§3 T2 + Appendix): hosted
open-weight models (Llama, Mixtral, …) via OpenRouter's OpenAI-compatible
``POST /v1/chat/completions``, so the open-source route needs zero local GPU/RAM.
Implements the ``LLMClient`` protocol verbatim — a drop-in alongside Ollama and
the frozen Groq/Gemini clients.

Design mirrors OllamaClient: raw ``httpx`` (already a dependency), injectable
transport for network-free tests, no new SDK. The API key + endpoint are config
(never hardcoded, never frozen into the trace).
"""

from __future__ import annotations

from typing import Any

import httpx

from paper_trader.llm.groq_client import LLMError, LLMRateLimitError

DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"


class OpenRouterClient:
    """Live OpenRouter client (OpenAI-compatible). Hosted open-weight; needs a key."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = "openrouter"
        self._model = model
        self._endpoint = endpoint.rstrip("/")
        self._client = httpx.Client(
            base_url=self._endpoint,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> tuple[str, int]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                raise LLMRateLimitError(f"OpenRouter rate limited: {e}") from e
            raise LLMError(f"OpenRouter HTTP {code}: {e}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"OpenRouter error: {e}") from e

        return _parse_completion(data)


def _parse_completion(data: dict[str, Any]) -> tuple[str, int]:
    """Extract (text, tokens_used) from an OpenAI-compatible completion."""
    choices = data.get("choices")
    if not choices:
        raise LLMError(f"OpenRouter response has no choices: {data!r}")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "")
    usage = data.get("usage") or {}
    tokens = int(usage.get("total_tokens", 0))
    return text, tokens
