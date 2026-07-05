"""Application config.

Governance-store paths wired here:
- SKILL-VERSION REGISTRY (Wave 2.5) — opened READ-ONLY for skill loading.
- STORE A (Wave 3) — the execution-trace file, opened for orchestrator-level
  emission (cycle headers + agent invocations). Emission is non-blocking.

DELIBERATELY NOT wired: STORE B (the correction ledger). Nothing in the fast loop
writes the ledger this wave; wiring its path would invite a write path the
hard-stop invariant forbids. The app db + checkpointer paths remain the existing
PAPER_TRADER_DB_PATH / CHECKPOINTER_DB_PATH env vars (unchanged).
"""

from __future__ import annotations

import os
from pathlib import Path

from steward.storage.skill_version import SkillVersionRegistry
from steward.storage.store_a import StoreA

# Env var naming mirrors the existing PAPER_TRADER_DB_PATH / CHECKPOINTER_DB_PATH.
SKILL_REGISTRY_PATH_ENV = "SKILL_REGISTRY_DB_PATH"
DEFAULT_SKILL_REGISTRY_PATH = "./data/skills.sqlite"

STORE_A_PATH_ENV = "STORE_A_DB_PATH"
DEFAULT_STORE_A_PATH = "./data/store_a.sqlite"

# The DC-1 application/instance identifier stamped on every governance record.
APPLICATION_ID = "paper-trader"


def skill_registry_path() -> Path:
    """Resolve the skill-registry file path from env (with a default)."""
    return Path(os.environ.get(SKILL_REGISTRY_PATH_ENV, DEFAULT_SKILL_REGISTRY_PATH))


def open_skill_registry(path: Path | None = None) -> SkillVersionRegistry:
    """Open the skill-version registry for READ-ONLY skill loading.

    The registry object is the framework's; agents use it only to obtain a
    connection for ``steward.storage.skill_loader.load_skill``. No writes occur
    from the application in this wave.
    """
    return SkillVersionRegistry(path or skill_registry_path())


def store_a_path() -> Path:
    """Resolve the Store A (execution-trace) file path from env (with a default)."""
    return Path(os.environ.get(STORE_A_PATH_ENV, DEFAULT_STORE_A_PATH))


def open_store_a(path: Path | None = None) -> StoreA:
    """Open the Store A execution-trace store by injected path.

    The framework helper (steward.storage.store_a.StoreA) creates the file if
    absent and applies the schema. Emission through it is non-blocking (a write
    failure never aborts a cycle). Store A is a DISTINCT file from the app db,
    the checkpointer, the skill registry, and Store B.
    """
    return StoreA(path or store_a_path())
