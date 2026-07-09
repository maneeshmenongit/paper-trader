"""Model-tier routing: FAST vs REASONING (framework capability).

Purposes fall into two tiers by their nature, not by which provider happens to be
configured:

- **FAST** — high-volume, mechanical purposes (classification, summarization,
  bias_tagging). A cheap/local model is the right tool; latency and cost dominate.
- **REASONING** — judgment-heavy purposes (method selection / ``predict_selection``).
  A stronger model earns its cost; a weak model here produces a weak result.

This module declares the tier of each purpose and builds a provider client from a
``(provider, model)`` pair, so wiring a router is *declarative* — the caller states
"fast tier = ollama, reasoning tier = groq" and the router falls out — instead of
each call site hand-assembling provider chains.

It only *constructs* the frozen provenance clients (GroqClient, GeminiClient,
OllamaClient, OpenRouterClient); it never edits them. DC-1: application layer.
"""

from __future__ import annotations

from typing import Literal

from paper_trader.llm.interfaces import LLMClient

Tier = Literal["fast", "reasoning"]

# The reasoning tier — everything else is fast. ``predict_selection`` is the Stage 1
# method-selector purpose (unmapped in the frozen LLMPurpose Literal by design).
REASONING_PURPOSES: frozenset[str] = frozenset({"predict_selection", "reasoning"})


def tier_of(purpose: str) -> Tier:
    """The tier a purpose belongs to (reasoning if judgment-heavy, else fast)."""
    return "reasoning" if purpose in REASONING_PURPOSES else "fast"


def build_client(provider: str, *, model: str = "", config: object) -> LLMClient:
    """Construct a client for ``provider`` (optionally with an explicit ``model``).

    ``config`` is a ``LiveConfig`` (duck-typed to avoid a live-layer import cycle);
    keys/endpoints are read from it. Raises ``ValueError`` for an unknown provider or
    a missing required key.
    """
    provider = provider.strip().lower()
    if provider in ("claude", "anthropic"):
        from paper_trader.llm.claude_client import ClaudeClient

        key = getattr(config, "anthropic_api_key", "")
        if not key:
            raise ValueError("reasoning provider 'claude' requires ANTHROPIC_API_KEY")
        return ClaudeClient(api_key=key, model=model) if model else ClaudeClient(api_key=key)
    if provider == "groq":
        from paper_trader.llm.groq_client import GroqClient

        key = getattr(config, "groq_api_key", "")
        if not key:
            raise ValueError("reasoning/fast provider 'groq' requires GROQ_API_KEY")
        return GroqClient(api_key=key, model=model) if model else GroqClient(api_key=key)
    if provider == "gemini":
        from paper_trader.llm.gemini_client import GeminiClient

        key = getattr(config, "gemini_api_key", "")
        if not key:
            raise ValueError("provider 'gemini' requires GEMINI_API_KEY")
        return GeminiClient(api_key=key, model=model) if model else GeminiClient(api_key=key)
    if provider == "openrouter":
        from paper_trader.llm.openrouter_client import OpenRouterClient

        key = getattr(config, "openrouter_api_key", "")
        if not key:
            raise ValueError("provider 'openrouter' requires OPENROUTER_API_KEY")
        m = model or getattr(config, "openrouter_model", "")
        return OpenRouterClient(api_key=key, model=m)
    if provider == "ollama":
        from paper_trader.llm.ollama_client import OllamaClient

        return OllamaClient(
            model=model or getattr(config, "ollama_model", ""),
            endpoint=getattr(config, "ollama_endpoint", "http://localhost:11434"),
        )
    raise ValueError(f"unknown LLM provider: {provider!r}")
