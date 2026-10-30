"""Where the plugin (agents, skills, guard) lives relative to this package."""

from __future__ import annotations

import os
from pathlib import Path


def plugin_dir() -> Path:
    """The ai-company plugin directory: $AI_COMPANY_PLUGIN_DIR, or the checkout's copy."""
    override = os.environ.get("AI_COMPANY_PLUGIN_DIR")
    if override:
        return Path(override).resolve()
    return (Path(__file__).resolve().parent.parent / "plugins" / "ai-company").resolve()
