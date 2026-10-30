"""Git and GitHub operations, done by the orchestrator only.

The GitHub token is taken out of the process environment when the
orchestrator starts (`take_token`), so agent subprocesses never inherit it.
It is handed to `git` and `gh` per command through their environment.

Nothing here deletes anything: no branch deletes, no force pushes, no closing
or deleting issues. The human owner merges.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TOKEN_VARS = ("AI_COMPANY_GITHUB_TOKEN", "AGENT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def take_token(environ: dict[str, str] | None = None) -> str:
    """Return the GitHub token and remove every token variable from the env."""
    environ = os.environ if environ is None else environ
    token = ""
    for name in TOKEN_VARS:
        value = environ.pop(name, "")
        token = token or value
    return token


class GitError(RuntimeError):
    pass


@dataclass
class Git:
    repo_root: Path
    token: str = ""
    author_name: str = ""
    author_email: str = ""

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.author_name:
            env.update(
                GIT_AUTHOR_NAME=self.author_name,
                GIT_COMMITTER_NAME=self.author_name,
                GIT_AUTHOR_EMAIL=self.author_email,
                GIT_COMMITTER_EMAIL=self.author_email,
            )
        if self.token:
            basic = base64.b64encode(f"x-access-token:{self.token}".encode()).decode()
            env.update(
                GIT_CONFIG_COUNT="1",
                GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}",
                GIT_TERMINAL_PROMPT="0",
            )
        return env

    def run(self, *args: str, check: bool = True) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=self.repo_root, env=self._env(), capture_output=True, text=True
        )
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc.stdout

    def current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD").strip()

    def branch_exists_remote(self, branch: str) -> bool:
        return bool(self.run("ls-remote", "--heads", "origin", branch, check=False).strip())

    def fetch(self, *refs: str) -> None:
        self.run("fetch", "--no-tags", "origin", *refs, check=False)

    def start_branch(self, branch: str, base: str) -> None:
        """Check out `branch`, creating it from `base` if it does not exist yet."""
        self.fetch(base)
        if self.branch_exists_remote(branch):
            self.fetch(branch)
            self.run("checkout", "-B", branch, f"origin/{branch}")
        elif self.run("rev-parse", "--verify", "--quiet", branch, check=False).strip():
            self.run("checkout", branch)
        else:
            start = f"origin/{base}" if self.run("rev-parse", "--verify", "--quiet", f"origin/{base}", check=False).strip() else "HEAD"
            self.run("checkout", "-b", branch, start)

    def has_changes(self) -> bool:
        return bool(self.run("status", "--porcelain").strip())

    def diff_against(self, base: str) -> str:
        ref = f"origin/{base}" if self.run("rev-parse", "--verify", "--quiet", f"origin/{base}", check=False).strip() else base
        self.run("add", "-A", "--intent-to-add", check=False)
        return self.run("diff", ref, check=False)

    def commit_all(self, message: str) -> bool:
        self.run("add", "-A")
        if not self.run("diff", "--cached", "--name-only").strip():
            return False
        self.run("commit", "-m", message)
        return True

    def push(self, branch: str) -> None:
        # Never force: if the remote moved, fail loudly instead of overwriting.
        self.run("push", "-u", "origin", f"{branch}:{branch}")


@dataclass
class GitHub:
    repo: str  # owner/name
    token: str
    repo_root: Path

    def _gh(self, *args: str, input_text: str | None = None) -> str:
        env = dict(os.environ)
        env["GH_TOKEN"] = self.token
        env["GH_REPO"] = self.repo
        env["GH_PROMPT_DISABLED"] = "1"
        proc = subprocess.run(
            ["gh", *args], cwd=self.repo_root, env=env, capture_output=True, text=True, input=input_text
        )
        if proc.returncode != 0:
            raise GitError(f"gh {args[0]} {args[1] if len(args) > 1 else ''} failed: {proc.stderr.strip()}")
        return proc.stdout

    def _api(self, path: str, method: str = "GET", fields: dict[str, Any] | None = None) -> Any:
        args = ["api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
        body = json.dumps(fields) if fields is not None else None
        if body is not None:
            args += ["--input", "-"]
        out = self._gh(*args, input_text=body)
        return json.loads(out) if out.strip() else None

    def whoami(self) -> dict[str, Any]:
        return self._api("user")

    # -- issues -------------------------------------------------------------
    def get_issue(self, number: int) -> dict[str, Any]:
        return self._api(f"repos/{self.repo}/issues/{number}")

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        return self._api(f"repos/{self.repo}/issues/{number}/comments?per_page=100")

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        return self._api(f"repos/{self.repo}/issues", "POST", {"title": title, "body": body, "labels": labels or []})

    def comment(self, number: int, body: str) -> dict[str, Any]:
        return self._api(f"repos/{self.repo}/issues/{number}/comments", "POST", {"body": body})

    def update_comment(self, comment_id: int, body: str) -> None:
        self._api(f"repos/{self.repo}/issues/comments/{comment_id}", "PATCH", {"body": body})

    def ensure_labels(self, labels: dict[str, str]) -> None:
        existing = {l["name"] for l in self._api(f"repos/{self.repo}/labels?per_page=100")}
        for name, color in labels.items():
            if name not in existing:
                self._api(f"repos/{self.repo}/labels", "POST", {"name": name, "color": color})

    def add_labels(self, number: int, labels: list[str]) -> None:
        self._api(f"repos/{self.repo}/issues/{number}/labels", "POST", {"labels": labels})

    def remove_label(self, number: int, label: str) -> None:
        try:
            self._api(f"repos/{self.repo}/issues/{number}/labels/{label}", "DELETE")
        except GitError:
            pass  # label was not on the issue

    def issues_with_label(self, label: str) -> list[dict[str, Any]]:
        return self._api(f"repos/{self.repo}/issues?state=open&labels={label}&per_page=50")

    # -- pull requests --------------------------------------------------------
    def find_pr(self, branch: str) -> dict[str, Any] | None:
        owner = self.repo.split("/")[0]
        prs = self._api(f"repos/{self.repo}/pulls?state=open&head={owner}:{branch}")
        return prs[0] if prs else None

    def get_pr(self, number: int) -> dict[str, Any]:
        return self._api(f"repos/{self.repo}/pulls/{number}")

    def pr_review_comments(self, number: int) -> list[dict[str, Any]]:
        return self._api(f"repos/{self.repo}/pulls/{number}/comments?per_page=100")

    def pr_reviews(self, number: int) -> list[dict[str, Any]]:
        return self._api(f"repos/{self.repo}/pulls/{number}/reviews?per_page=100")

    def create_pr(self, branch: str, base: str, title: str, body: str, draft: bool) -> dict[str, Any]:
        return self._api(
            f"repos/{self.repo}/pulls",
            "POST",
            {"title": title, "head": branch, "base": base, "body": body, "draft": draft},
        )

    def update_pr(self, number: int, body: str) -> None:
        self._api(f"repos/{self.repo}/pulls/{number}", "PATCH", {"body": body})

    def request_review(self, number: int, login: str) -> None:
        try:
            self._api(f"repos/{self.repo}/pulls/{number}/requested_reviewers", "POST", {"reviewers": [login]})
        except GitError as exc:
            log.warning("Could not request review from %s: %s", login, exc)

    def assign(self, number: int, login: str) -> None:
        try:
            self._api(f"repos/{self.repo}/issues/{number}/assignees", "POST", {"assignees": [login]})
        except GitError as exc:
            log.warning("Could not assign %s: %s", login, exc)
