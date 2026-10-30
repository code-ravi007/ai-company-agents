from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pytest

from ai_company.config import Config, RoleSettings
from ai_company.github import Git
from ai_company.runner import RoleResult, UsageLimitPause

SPEC = {
    "title": "Add greeting page",
    "summary": "Show a friendly greeting.",
    "branch_slug": "greeting-page",
    "user_stories": ["As a visitor I see a greeting"],
    "acceptance_criteria": ["The page shows 'Hello'"],
    "tasks": [{"title": "Create page", "details": "hello.html", "area": "frontend"}],
    "out_of_scope": [],
    "assumptions": [],
    "needs_design": True,
    "blocked": False,
    "open_questions": [],
}
DEV = {"summary": "Added hello.html", "files_changed": ["hello.html"], "test_command": "", "tests_passed": True, "notes": ""}
APPROVE = {"verdict": "approve", "summary": "Looks good", "blocking_issues": [], "suggestions": [], "criteria_checked": []}
CHANGES = {
    "verdict": "request_changes",
    "summary": "Missing exclamation",
    "blocking_issues": [{"file": "hello.html", "problem": "no !", "fix": "add !"}],
    "suggestions": [],
    "criteria_checked": [],
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    (work / "README.md").write_text("# demo\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "-u", "origin", "main")
    return work


@pytest.fixture
def config(repo: Path) -> Config:
    fast = RoleSettings(max_turns=1, max_budget_usd=0.1)
    return Config(repo_root=repo, owner_login="ravikumar1002", manager=fast, designer=fast, developer=fast, reviewer=fast)


@pytest.fixture
def make_git(repo: Path) -> Callable[[], Git]:
    return lambda: Git(repo, author_name="bot", author_email="bot@example.com")


@dataclass
class FakeRunner:
    """Scripted runner: each role pops its next behaviour from a queue."""

    script: dict[str, list[Any]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def run(self, role, settings, prompt, cwd: Path) -> RoleResult:
        self.calls.append((role.name, prompt))
        step = self.script[role.name].pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            step = step(cwd, prompt)
        return RoleResult(role=role.name, output=step, cost_usd=0.01, turns=1)


def designer_writes(cwd: Path, prompt: str) -> dict:
    import re

    path = re.search(r"`([^`]+design\.md)`", prompt).group(1)
    (cwd / path).parent.mkdir(parents=True, exist_ok=True)
    (cwd / path).write_text("# Design\n")
    return {"summary": "One page", "screens": ["hello"], "open_questions": []}


def developer_writes(content: str) -> Callable[[Path, str], dict]:
    def _write(cwd: Path, prompt: str) -> dict:
        (cwd / "hello.html").write_text(content)
        return DEV

    return _write


@dataclass
class FakeGitHub:
    issues: dict[int, dict] = field(default_factory=dict)
    comments: dict[int, list[dict]] = field(default_factory=dict)
    labels: dict[int, set[str]] = field(default_factory=dict)
    prs: list[dict] = field(default_factory=list)
    review_requests: list[tuple[int, str]] = field(default_factory=list)
    _next_comment: int = 100

    def get_issue(self, n):
        return self.issues[n]

    def issue_comments(self, n):
        return list(self.comments.get(n, []))

    def create_issue(self, title, body, labels=None):
        n = max(self.issues, default=0) + 1
        self.issues[n] = {"number": n, "title": title, "body": body}
        self.labels[n] = set(labels or [])
        return self.issues[n]

    def comment(self, n, body):
        self._next_comment += 1
        c = {"id": self._next_comment, "body": body, "user": {"login": "bot"}}
        self.comments.setdefault(n, []).append(c)
        return c

    def update_comment(self, cid, body):
        for cs in self.comments.values():
            for c in cs:
                if c["id"] == cid:
                    c["body"] = body

    def ensure_labels(self, labels):
        pass

    def add_labels(self, n, labels):
        self.labels.setdefault(n, set()).update(labels)

    def remove_label(self, n, label):
        self.labels.setdefault(n, set()).discard(label)

    def issues_with_label(self, label):
        return [self.issues[n] for n, ls in self.labels.items() if label in ls]

    def find_pr(self, branch):
        return next((p for p in self.prs if p["head"]["ref"] == branch), None)

    def create_pr(self, branch, base, title, body, draft):
        pr = {"number": 50 + len(self.prs), "html_url": f"https://github.test/pr/{50 + len(self.prs)}",
              "head": {"ref": branch}, "title": title, "body": body, "draft": draft}
        self.prs.append(pr)
        return pr

    def update_pr(self, n, body):
        for p in self.prs:
            if p["number"] == n:
                p["body"] = body

    def get_pr(self, n):
        return next(p for p in self.prs if p["number"] == n)

    def pr_reviews(self, n):
        return []

    def pr_review_comments(self, n):
        return []

    def assign(self, n, login):
        pass

    def request_review(self, n, login):
        self.review_requests.append((n, login))


__all__ = ["SPEC", "DEV", "APPROVE", "CHANGES", "FakeRunner", "FakeGitHub", "designer_writes", "developer_writes", "git", "UsageLimitPause"]
