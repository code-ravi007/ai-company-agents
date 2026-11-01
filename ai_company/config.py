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
    # QA tests user-facing changes in a browser after the review; a failed QA
    # sends the bugs back to the developer at most this many times.
    qa_enabled: bool = True
    max_qa_rounds: int = 1
    # The tech writer updates README, docs and CHANGELOG before the PR opens.
    docs_enabled: bool = True
    # The support agent triages issues opened by people other than the owner.
    # Off by default: on a public repo anyone can open issues, and each triage
    # is a (small, budget-capped) Claude run on your subscription.
    support_enabled: bool = False
    # False: support posts its labels and a *draft* reply for the owner.
    # True: support replies to the issue author directly.
    support_auto_reply: bool = False
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
    qa: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=50, max_budget_usd=3.0))
    tech_writer: RoleSettings = field(default_factory=lambda: RoleSettings(effort="medium", max_turns=30, max_budget_usd=1.5))
    researcher: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=40, max_budget_usd=3.0))
    marketing: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=40, max_budget_usd=2.0))
    content_writer: RoleSettings = field(default_factory=lambda: RoleSettings(max_turns=40, max_budget_usd=2.0))
    support: RoleSettings = field(default_factory=lambda: RoleSettings(effort="medium", max_turns=20, max_budget_usd=0.5))

    def triggerers(self) -> set[str]:
        return set(self.allowed_triggerers) | ({self.owner_login} if self.owner_login else set())

    def role(self, name: str) -> RoleSettings:
        return getattr(self, name.replace("-", "_"))


_ROLE_NAMES = (
    "manager", "designer", "developer", "reviewer", "qa", "tech_writer",
    "researcher", "marketing", "content_writer", "support",
)


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
