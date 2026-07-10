"""Live-mode configuration (Live-Operation T3).

Env-sourced config for taking the skeleton live: the live-mode flag that swaps
fakes → live clients, data-provider keys, the LLM endpoints/models, and the
watchlist location. This is the ONLY place secrets/endpoints are read.

CRITICAL (DT-4.2 MUST-NOT-freeze): none of these values may enter the immutable
trace. The freeze builder (graph/freeze.py) already excludes secrets/paths; this
config is passed to the run harness for WIRING, never handed to the freeze
builder. ``LiveConfig.redacted()`` exists so a value can be logged safely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ─── env var names (mirroring the existing PAPER_TRADER_* convention) ──────
LIVE_MODE_ENV = "PAPER_TRADER_LIVE_MODE"  # "1"/"true" → live clients; else fakes

FINNHUB_API_KEY_ENV = "FINNHUB_API_KEY"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
GROQ_API_KEY_ENV = "GROQ_API_KEY"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"

LLM_PROVIDER_ENV = "PAPER_TRADER_LLM_PROVIDER"  # ollama | openrouter | hosted
OLLAMA_ENDPOINT_ENV = "OLLAMA_ENDPOINT"
OLLAMA_MODEL_ENV = "OLLAMA_MODEL"
OPENROUTER_MODEL_ENV = "OPENROUTER_MODEL"

# Model-TIER routing (fast vs reasoning). Fast purposes (classification,
# summarization, bias_tagging) are high-volume + mechanical → a cheap/local model.
# Reasoning purposes (predict_selection) are judgment-heavy → a stronger model.
# The reasoning tier is configured independently so an operator can point it at a
# strong provider while fast stays local. Empty reasoning_provider → reasoning
# falls back to the fast tier (single-tier behavior, unchanged).
REASONING_PROVIDER_ENV = "PAPER_TRADER_REASONING_PROVIDER"  # groq | gemini | ollama | openrouter
REASONING_MODEL_ENV = "PAPER_TRADER_REASONING_MODEL"  # provider-specific model id (optional)

WATCHLIST_PATH_ENV = "PAPER_TRADER_WATCHLIST_PATH"
DEFAULT_WATCHLIST_PATH = "./config/watchlist.toml"

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class LiveConfig:
    """Resolved live-operation config. Secrets are held here and NOWHERE else.

    ``live_mode=False`` (the default) keeps the process on fakes — CI and any
    unconfigured run stay offline. Turning it on requires the operator to set the
    flag *and* supply the relevant keys.
    """

    live_mode: bool
    # LLM provider selection: which open-source path serves the FAST tier
    # (Research/PostMortem — classification, summarization, bias_tagging).
    llm_provider: str  # "ollama" | "openrouter"
    ollama_endpoint: str
    ollama_model: str
    openrouter_model: str
    # REASONING tier (judgment-heavy purposes, e.g. predict_selection). Empty
    # provider → reasoning reuses the fast tier. Model empty → the provider's default.
    reasoning_provider: str = ""  # "" | groq | gemini | ollama | openrouter
    reasoning_model: str = ""
    # Secrets (may be empty when not configured / not in live mode).
    finnhub_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    watchlist_path: Path = field(default_factory=lambda: Path(DEFAULT_WATCHLIST_PATH))

    def redacted(self) -> dict[str, object]:
        """A log-safe view: flags/models/endpoints shown, secrets masked."""

        def mask(secret: str) -> str:
            return "set" if secret else "unset"

        return {
            "live_mode": self.live_mode,
            "llm_provider": self.llm_provider,
            "ollama_endpoint": self.ollama_endpoint,
            "ollama_model": self.ollama_model,
            "openrouter_model": self.openrouter_model,
            "reasoning_provider": self.reasoning_provider or "(fast-tier)",
            "reasoning_model": self.reasoning_model or "(provider-default)",
            "finnhub_api_key": mask(self.finnhub_api_key),
            "openrouter_api_key": mask(self.openrouter_api_key),
            "groq_api_key": mask(self.groq_api_key),
            "gemini_api_key": mask(self.gemini_api_key),
            "anthropic_api_key": mask(self.anthropic_api_key),
            "watchlist_path": str(self.watchlist_path),
        }


def load_live_config(env: dict[str, str] | None = None) -> LiveConfig:
    """Build a LiveConfig from the environment (injectable for tests).

    Defaults are safe: ``live_mode`` off, Ollama at localhost. Missing keys are
    empty strings, not errors — a fakes run needs none of them; live mode's
    provider factories validate what they actually require.
    """
    src = os.environ if env is None else env

    def get(name: str, default: str = "") -> str:
        return src.get(name, default)

    live_mode = (get(LIVE_MODE_ENV).strip().lower() in _TRUTHY)
    return LiveConfig(
        live_mode=live_mode,
        llm_provider=get(LLM_PROVIDER_ENV, "ollama").strip().lower(),
        ollama_endpoint=get(OLLAMA_ENDPOINT_ENV, "http://localhost:11434"),
        ollama_model=get(OLLAMA_MODEL_ENV, "llama3.1:8b"),
        openrouter_model=get(OPENROUTER_MODEL_ENV, "meta-llama/llama-3.1-8b-instruct"),
        reasoning_provider=get(REASONING_PROVIDER_ENV).strip().lower(),
        reasoning_model=get(REASONING_MODEL_ENV),
        finnhub_api_key=get(FINNHUB_API_KEY_ENV),
        openrouter_api_key=get(OPENROUTER_API_KEY_ENV),
        groq_api_key=get(GROQ_API_KEY_ENV),
        gemini_api_key=get(GEMINI_API_KEY_ENV),
        anthropic_api_key=get(ANTHROPIC_API_KEY_ENV),
        watchlist_path=Path(get(WATCHLIST_PATH_ENV, DEFAULT_WATCHLIST_PATH)),
    )
