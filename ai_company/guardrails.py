"""The team's safety policy, shared with the Claude Code plugin hook.

The rules live in `plugins/ai-company/scripts/guard.py` so the plugin (used
interactively in any project) and the CI orchestrator enforce exactly the
same thing. This module loads that file and adds the Agent SDK callback.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

from ai_company.paths import plugin_dir

_spec = importlib.util.spec_from_file_location("ai_company_guard", plugin_dir() / "scripts" / "guard.py")
assert _spec and _spec.loader
_guard = importlib.util.module_from_spec(_spec)
sys.modules["ai_company_guard"] = _guard
_spec.loader.exec_module(_guard)

Decision = _guard.Decision
Guardrails = _guard.Guardrails
RolePolicy = _guard.RolePolicy
role_policies = _guard.role_policies
command_segments = _guard.command_segments
hook_main = _guard.hook_main


def sdk_callback(guard: Any):
    """Agent SDK `can_use_tool` callback that applies `guard`."""

    async def can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        decision = guard.check(tool_name, tool_input)
        if decision.allowed:
            return PermissionResultAllow()
        return PermissionResultDeny(message=decision.reason)

    return can_use_tool
