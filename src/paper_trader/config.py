"""Application config (Wave 2.5 Task 2).

Wires the SKILL-VERSION REGISTRY path so agents can open it READ-ONLY to load
their pinned @v1 skills via steward's loader. This is the only governance-store
path wired this wave.

DELIBERATELY NOT wired: Store A / Store B paths. This wave does NOT emit to the
governance trace/ledger (that is a later wave), so opening those connections here
would be premature — and the hard-stop invariant forbids any Store A/B write path.
The app db + checkpointer paths remain the existing PAPER_TRADER_DB_PATH /
CHECKPOINTER_DB_PATH env vars (unchanged).
"""

from __future__ import annotations

import os
from pathlib import Path

from steward.storage.skill_version import SkillVersionRegistry

# Env var naming mirrors the existing PAPER_TRADER_DB_PATH / CHECKPOINTER_DB_PATH.
SKILL_REGISTRY_PATH_ENV = "SKILL_REGISTRY_DB_PATH"
DEFAULT_SKILL_REGISTRY_PATH = "./data/skills.sqlite"


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
