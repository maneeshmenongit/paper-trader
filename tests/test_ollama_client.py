"""Ollama + OpenRouter client tests (Live-Operation T2).

Both clients are exercised against a FAKED httpx transport — no network, ever.
They implement the LLMClient protocol verbatim, so these tests also assert
protocol conformance and the (text, tokens) contract the router relies on.
"""

from __future__ import annotations

import httpx
import pytest

from paper_trader.llm.groq_client import LLMError, LLMRateLimitError
from paper_trader.llm.interfaces import LLMClient
from paper_trader.llm.ollama_client import OllamaClient
from paper_trader.llm.openrouter_client import OpenRouterClient


def _transport(handler):
    return httpx.MockTransport(handler)


# ─── Ollama ──────────────────────────────────────────────────────────────

def _ollama_ok(content="hello", *, prompt=7, eval_=5):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": content},
                "prompt_eval_count": prompt,
                "eval_count": eval_,
            },
        )

    return OllamaClient(transport=_transport(handler))


def test_ollama_conforms_to_protocol():
    assert isinstance(_ollama_ok(), LLMClient)
    assert _ollama_ok().name == "ollama"


def test_ollama_complete_returns_text_and_token_sum():
    text, tokens = _ollama_ok(content="momentum", prompt=10, eval_=3).complete("s", "u")
    assert text == "momentum"
    assert tokens == 13  # prompt_eval_count + eval_count


def test_ollama_json_mode_sets_format():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "{}"}})

    client = OllamaClient(transport=_transport(handler))
    client.complete("s", "u", json_mode=True)
    assert seen["body"]["format"] == "json"
    assert seen["body"]["options"]["num_predict"] == 1000


def test_ollama_rate_limit_maps_to_ratelimit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "busy"})

    with pytest.raises(LLMRateLimitError):
        OllamaClient(transport=_transport(handler)).complete("s", "u")


def test_ollama_server_error_maps_to_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(LLMError):
        OllamaClient(transport=_transport(handler)).complete("s", "u")


def test_ollama_missing_content_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done": True})

    with pytest.raises(LLMError, match="missing message content"):
        OllamaClient(transport=_transport(handler)).complete("s", "u")


def test_ollama_missing_token_counts_default_to_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "hi"}})

    text, tokens = OllamaClient(transport=_transport(handler)).complete("s", "u")
    assert (text, tokens) == ("hi", 0)


# ─── OpenRouter ──────────────────────────────────────────────────────────

def _openrouter_ok(content="hi", total=12):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"total_tokens": total},
            },
        )

    return OpenRouterClient(api_key="test-key", transport=_transport(handler))


def test_openrouter_conforms_to_protocol():
    assert isinstance(_openrouter_ok(), LLMClient)
    assert _openrouter_ok().name == "openrouter"


def test_openrouter_complete_returns_text_and_tokens():
    text, tokens = _openrouter_ok(content="story", total=42).complete("s", "u")
    assert (text, tokens) == ("story", 42)


def test_openrouter_no_choices_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(LLMError, match="no choices"):
        OpenRouterClient(api_key="k", transport=_transport(handler)).complete("s", "u")


def test_openrouter_rate_limit_maps():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with pytest.raises(LLMRateLimitError):
        OpenRouterClient(api_key="k", transport=_transport(handler)).complete("s", "u")
