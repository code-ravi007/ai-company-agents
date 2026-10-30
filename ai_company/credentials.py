"""Which Claude credential the team runs on.

Two credentials are supported:

- `CLAUDE_CODE_OAUTH_TOKEN`: a Claude subscription token (Pro, Max, Team or
  Enterprise) made with `claude setup-token`. Runs count against the
  subscription's usage limits instead of API billing.
- `ANTHROPIC_API_KEY`: a Claude Console API key, billed per token.

Both are taken out of the process environment at startup, like the GitHub
token, and handed only to the Claude Code subprocess of each agent run. That
way the orchestrator decides which one is used (the CLI would otherwise
always prefer the API key when both are set).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

OAUTH_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
API_KEY_VAR = "ANTHROPIC_API_KEY"

SUBSCRIPTION = "subscription"
API = "api"


@dataclass
class Credentials:
    oauth_token: str = ""
    api_key: str = ""
    # "auto" uses the subscription when a token is set, else the API key.
    mode: str = "auto"
    # When the subscription's usage limit is hit, switch to the API key
    # instead of pausing. Off by default: it spends money.
    api_fallback_on_limit: bool = False
    _active: str = ""

    @classmethod
    def take_from_env(cls, mode: str = "auto", api_fallback_on_limit: bool = False, environ: dict[str, str] | None = None) -> "Credentials":
        environ = os.environ if environ is None else environ
        return cls(
            oauth_token=environ.pop(OAUTH_VAR, ""),
            api_key=environ.pop(API_KEY_VAR, ""),
            mode=mode,
            api_fallback_on_limit=api_fallback_on_limit,
        )

    @property
    def active(self) -> str:
        """The credential in use: "subscription", "api", or "" for none."""
        if not self._active:
            if self.mode == SUBSCRIPTION or (self.mode == "auto" and self.oauth_token):
                self._active = SUBSCRIPTION if self.oauth_token else ""
            elif self.mode in (API, "auto"):
                self._active = API if self.api_key else ""
        return self._active

    def env(self) -> dict[str, str]:
        """Environment for one Claude Code subprocess, with exactly one credential."""
        if self.active == SUBSCRIPTION:
            return {OAUTH_VAR: self.oauth_token}
        if self.active == API:
            return {API_KEY_VAR: self.api_key}
        return {}  # fall back to whatever login the machine has (local use)

    def can_fall_back(self) -> bool:
        return self.active == SUBSCRIPTION and self.api_fallback_on_limit and bool(self.api_key)

    def fall_back_to_api(self) -> None:
        self._active = API

    def describe(self) -> str:
        return {SUBSCRIPTION: "Claude subscription", API: "API key"}.get(self.active, "local Claude login")
