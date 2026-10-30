"""Runs one role as a Claude Agent SDK session.

`AgentRunner` is the seam the pipeline talks to, so tests can swap in a fake.
`SdkRunner` is the real implementation. It handles usage limits: when the API
says the limit is hit it waits for the reset (up to `max_wait_seconds`) and
retries; if the wait would be longer, it raises `UsageLimitPause` so the
pipeline can save its state and resume later.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ai_company.config import RoleSettings
from ai_company.credentials import Credentials
from ai_company.guardrails import Guardrails, sdk_callback
from ai_company.paths import plugin_dir
from ai_company.roles import Role

log = logging.getLogger(__name__)


@dataclass
class RoleResult:
    role: str
    output: dict[str, Any]
    text: str = ""
    cost_usd: float = 0.0
    turns: int = 0
    denials: list[str] = field(default_factory=list)


class UsageLimitPause(Exception):
    """The usage limit is hit and the reset is too far away to wait in-process."""

    def __init__(self, resets_at: float | None, message: str = ""):
        self.resets_at = resets_at
        super().__init__(message or f"Usage limit reached; resets at {resets_at}")


class AgentRunError(Exception):
    pass


class AgentRunner(Protocol):
    async def run(self, role: Role, settings: RoleSettings, prompt: str, cwd: Path) -> RoleResult: ...


_LIMIT_HINTS = ("rate limit", "rate_limit", "usage limit", "overloaded", "429", "529", "quota")


def _looks_like_limit(text: str) -> bool:
    lowered = text.lower()
    return any(h in lowered for h in _LIMIT_HINTS)


@dataclass
class SdkRunner:
    max_wait_seconds: float = 30 * 60
    max_attempts: int = 4
    backoff_seconds: float = 30.0
    sleep: Any = asyncio.sleep
    clock: Any = time.time
    credentials: Credentials = field(default_factory=Credentials)
    docs_dir: str = "docs/ai-company"

    async def run(self, role: Role, settings: RoleSettings, prompt: str, cwd: Path) -> RoleResult:
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._run_once(role, settings, prompt, cwd)
            except _RetryableLimit as exc:
                if self.credentials.can_fall_back():
                    log.warning("%s hit the subscription usage limit; switching to the API key", role.name)
                    self.credentials.fall_back_to_api()
                    attempt -= 1
                    continue
                if attempt >= self.max_attempts:
                    raise UsageLimitPause(exc.resets_at, f"{role.name}: still limited after {attempt} attempts") from exc
                wait = self._wait_for(exc.resets_at, attempt)
                if wait > self.max_wait_seconds:
                    raise UsageLimitPause(exc.resets_at) from exc
                log.warning("%s hit a usage limit; waiting %.0fs before retry %d", role.name, wait, attempt + 1)
                await self.sleep(wait)

    def _wait_for(self, resets_at: float | None, attempt: int) -> float:
        if resets_at:
            return max(5.0, resets_at - self.clock() + 5)
        return self.backoff_seconds * (2 ** (attempt - 1))

    async def _run_once(self, role: Role, settings: RoleSettings, prompt: str, cwd: Path) -> RoleResult:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            RateLimitEvent,
            ResultMessage,
            TextBlock,
            query,
        )

        guard = Guardrails(repo_root=cwd, policy=role.policy)
        options = ClaudeAgentOptions(
            system_prompt=role.system_prompt,
            model=settings.model,
            effort=settings.effort,  # type: ignore[arg-type]
            max_turns=settings.max_turns or role.max_turns,
            max_budget_usd=settings.max_budget_usd,
            tools=list(role.tools),
            permission_mode="default",
            can_use_tool=sdk_callback(guard),
            cwd=str(cwd),
            # The plugin's PreToolUse hook enforces the same rules a second
            # time; AI_COMPANY_ROLE tells it which role is running.
            env={**self.credentials.env(), "AI_COMPANY_ROLE": role.name, "AI_COMPANY_DOCS_DIR": self.docs_dir},
            plugins=[{"type": "local", "path": str(plugin_dir())}],
            # Do not load the machine's or repo's Claude settings; the team's
            # behaviour is defined entirely here.
            setting_sources=[],
            output_format={"type": "json_schema", "schema": role.output_schema},
        )

        resets_at: float | None = None
        texts: list[str] = []
        result: ResultMessage | None = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, RateLimitEvent):
                    info = message.rate_limit_info
                    if info.status == "rejected":
                        resets_at = info.resets_at
                elif isinstance(message, AssistantMessage):
                    texts.extend(b.text for b in message.content if isinstance(b, TextBlock))
                elif isinstance(message, ResultMessage):
                    result = message
        except Exception as exc:  # noqa: BLE001 - classify, then re-raise
            if resets_at or _looks_like_limit(str(exc)):
                raise _RetryableLimit(resets_at) from exc
            raise AgentRunError(f"{role.name} failed: {exc}") from exc

        if result is None:
            if resets_at:
                raise _RetryableLimit(resets_at)
            raise AgentRunError(f"{role.name} ended without a result")
        if result.is_error:
            detail = f"{result.subtype} {result.result or ''} {result.errors or ''} {result.api_error_status or ''}"
            if resets_at or _looks_like_limit(detail):
                raise _RetryableLimit(resets_at)
            raise AgentRunError(f"{role.name} ended with an error: {detail.strip()}")

        output = result.structured_output
        if output is None and result.result:
            try:
                output = json.loads(result.result)
            except json.JSONDecodeError:
                output = None
        if not isinstance(output, dict):
            raise AgentRunError(f"{role.name} did not return structured output")

        return RoleResult(
            role=role.name,
            output=output,
            text="\n".join(texts),
            cost_usd=result.total_cost_usd or 0.0,
            turns=result.num_turns,
            denials=guard.denials,
        )


class _RetryableLimit(Exception):
    def __init__(self, resets_at: float | None):
        self.resets_at = resets_at
        super().__init__("usage limit")
