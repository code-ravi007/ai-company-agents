"""Runtime configuration.

Settings come from three places, later ones winning:
  1. defaults in this file
  2. `ai-company.toml` at the root of the target repository
  3. environment variables (AI_COMPANY_*)

Secrets are never read from files. The GitHub token and the Anthropic API key
come only from the environment (GitHub Actions secrets in CI).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass(frozen=True)
class RoleSettings:
    model: str = DEFAULT_MODEL
    effort: str = "high"
    max_turns: int = 40
    max_budget_usd: float = 5.0


@dataclass(frozen=True)
class Config:
    repo_root: Path
    base_branch: str = "main"
    # GitHub login that should review and merge PRs (the human owner).
    # Empty means "the repository owner".
    owner_login: str = ""
    # Logins allowed to trigger the team. Anyone else is ignored.
    # Empty means "only the owner".
    allowed_triggerers: tuple[str, ...] = ()
    # Empty means "the account that owns the GitHub token" (the bot account).
    git_author_name: str = ""
    git_author_email: str = ""
    branch_prefix: str = "ai/"
    docs_dir: str = "docs/ai-company"
    # Shell command the orchestrator runs after the developer finishes, e.g.
    # "npm test" or "pytest -q". Empty means "let the developer decide".
    test_command: str = ""
    max_review_rounds: int = 2
    # "auto": Claude subscription token if set, else API key.
    # "subscription" or "api" forces one.
    auth_mode: str = "auto"
    # Switch to the API key when the subscription limit is hit, instead of
    # pausing until it resets. Spends API credit, so it is off by default.
    api_fallback_on_limit: bool = False
    manager: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=25, max_budget_usd=2.0))
    designer: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=25, max_budget_usd=2.0))
    developer: RoleSettings = field(default_factory=lambda: RoleSettings(effort="xhigh", max_turns=80, max_budget_usd=8.0))
    reviewer: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=30, max_budget_usd=3.0))

    def triggerers(self) -> set[str]:
        return set(self.allowed_triggerers) | ({self.owner_login} if self.owner_login else set())

    def role(self, name: str) -> RoleSettings:
        return getattr(self, name)


_ROLE_NAMES = ("manager", "designer", "developer", "reviewer")


def _coerce(value: object, like: object) -> object:
    if isinstance(like, bool):
        return str(value).lower() in ("1", "true", "yes") if isinstance(value, str) else bool(value)
    if isinstance(like, int):
        return int(value)  # type: ignore[arg-type]
    if isinstance(like, float):
        return float(value)  # type: ignore[arg-type]
    if isinstance(like, tuple):
        if isinstance(value, str):
            return tuple(v.strip() for v in value.split(",") if v.strip())
        return tuple(value)  # type: ignore[arg-type]
    return str(value)


def _apply(cfg: Config, data: dict) -> Config:
    updates: dict[str, object] = {}
    for f in fields(cfg):
        if f.name == "repo_root" or f.name not in data:
            continue
        current = getattr(cfg, f.name)
        if f.name in _ROLE_NAMES:
            role_updates = {
                rf.name: _coerce(data[f.name][rf.name], getattr(current, rf.name))
                for rf in fields(current)
                if rf.name in data[f.name]
            }
            updates[f.name] = replace(current, **role_updates)
        else:
            updates[f.name] = _coerce(data[f.name], current)
    return replace(cfg, **updates)


def _env_overrides(environ: dict[str, str]) -> dict:
    data: dict = {}
    prefix = "AI_COMPANY_"
    for key, value in environ.items():
        if not key.startswith(prefix) or not value:
            continue
        name = key[len(prefix):].lower()
        # AI_COMPANY_DEVELOPER__MODEL=... sets a role field.
        if "__" in name:
            role, attr = name.split("__", 1)
            if role in _ROLE_NAMES:
                data.setdefault(role, {})[attr] = value
        else:
            data[name] = value
    return data


def load_config(repo_root: Path, environ: dict[str, str] | None = None) -> Config:
    environ = dict(os.environ if environ is None else environ)
    cfg = Config(repo_root=repo_root.resolve())
    toml_path = repo_root / "ai-company.toml"
    if toml_path.exists():
        cfg = _apply(cfg, tomllib.loads(toml_path.read_text()))
    return _apply(cfg, _env_overrides(environ))
