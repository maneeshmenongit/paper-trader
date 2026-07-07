"""Ollama (self-hosted open-source) LLM client (Live-Operation T2).

Implements the ``LLMClient`` protocol from ``paper_trader.llm.interfaces`` verbatim
so it is a drop-in alongside the Groq/Gemini clients — agents call the router, the
router calls ``complete(system, user, max_tokens, json_mode) -> (text, tokens)``,
and never know which provider they got. The authority (§3 T2) routes Research and
PostMortem bias-tagging here; Predict is NOT touched (its selector is not built).

Design:
- Talks local HTTP to the Ollama server's ``POST /api/chat`` (endpoint + model are
  config, never hardcoded, never frozen into the trace — DT-4.2 MUST-NOT-freeze).
- Uses ``httpx`` (already a first-class dependency); the transport is injectable so
  tests hit a faked endpoint with zero network — no ``ollama`` SDK dependency added.
- This module is NOT the frozen oracle-provenance router; it is new application
  code, so it does not carry the copy-verbatim provenance header. It lives beside
  the frozen clients and is wired by config (T3), never inside an agent.
"""

from __future__ import annotations

from typing import Any

import httpx

from paper_trader.llm.groq_client import LLMError, LLMRateLimitError

DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"


class OllamaClient:
    """Live Ollama client over ``/api/chat``. Local, open-weight, no API key.

    ``transport`` (an ``httpx`` transport) is injectable so tests supply a faked
    endpoint. In production the client owns its own ``httpx.Client``.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = "ollama"
        self._model = model
        self._endpoint = endpoint.rstrip("/")
        self._client = httpx.Client(
            base_url=self._endpoint, timeout=timeout, transport=transport
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
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        try:
            response = self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                raise LLMRateLimitError(f"Ollama rate limited: {e}") from e
            raise LLMError(f"Ollama HTTP {code}: {e}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama error: {e}") from e

        return _parse_chat_response(data)


def _parse_chat_response(data: dict[str, Any]) -> tuple[str, int]:
    """Extract (text, tokens_used) from an Ollama /api/chat response.

    Ollama returns ``message.content`` plus ``prompt_eval_count`` +
    ``eval_count`` token counters (either may be absent early in a run). A missing
    message content is a provider error, not a silent empty string.
    """
    message = data.get("message")
    if not isinstance(message, dict) or "content" not in message:
        raise LLMError(f"Ollama response missing message content: {data!r}")
    text = str(message.get("content") or "")
    tokens = int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
    return text, tokens
