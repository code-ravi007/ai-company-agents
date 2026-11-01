#!/usr/bin/env python3
"""Safety guard for the AI company agents.

One file, two uses:

1. Claude Code PreToolUse hook (see ../hooks/hooks.json). It reads the hook
   input on stdin and blocks tool calls from the team's agents
   (manager, designer, developer, reviewer, researcher, qa, tech-writer,
   marketing, content-writer, support) that break the rules below.
   Calls from your own main session and from other agents are left alone.
2. Imported by the CI orchestrator (`ai_company.guardrails`), which applies
   the same policy through the Agent SDK's `can_use_tool` callback.

The policy is deny-by-default:

- Nobody deletes anything: rm, rmdir, unlink, find -delete, git rm,
  git clean, git reset --hard, force pushes and file deletes from Python or
  Node are refused.
- Agents never touch git history or GitHub. Only the human (locally) or the
  orchestrator (in CI) commits, pushes and opens pull requests.
- Writes stay in the repository, and each role in its own area: the manager,
  designer, researcher and QA tester write only the team's docs, the tech
  writer only documentation, marketing only `marketing/`, the content writer
  only `content/`; the reviewer and support write nothing. `.git/`, CI
  workflows, `.env` files and the team's own code are off limits.
- Only the researcher, marketing and content writer may search and read the
  web (WebSearch, WebFetch). Nobody posts anything outside GitHub.
- Reads stay in the repository and skip secret-looking files.
- Commands that read the environment or credentials, escalate privileges or
  open raw network connections are refused.

Only the Python standard library is used, so the hook runs anywhere.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import shlex
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

READ_TOOLS = {"Read", "Glob", "Grep", "LS"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
BASH_TOOLS = {"Bash"}
WEB_TOOLS = {"WebSearch", "WebFetch"}
# In-memory planning, skill-loading and structured-result tools, no side effects.
SIDE_EFFECT_FREE_TOOLS = {"TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "Skill", "StructuredOutput"}

# Files nobody may read or write, even inside the repository.
SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"(^|/)\.env(\..*)?$",
        r"\.pem$",
        r"\.key$",
        r"(^|/)id_(rsa|ed25519|ecdsa)",
        r"(^|/)\.npmrc$",
        r"(^|/)\.netrc$",
        r"(^|/)\.git-credentials$",
        r"(^|/)\.credentials\.json$",
        r"^\.git/config$",
    )
]
# The team may not edit its own code, config or guardrails.
PROTECTED_WRITE_PREFIXES = (".git/", ".github/workflows/", ".ai-company/", "ai_company/", "plugins/ai-company/", "ai-company.toml")

# First words of shell commands that are always refused.
DENIED_COMMANDS = {
    "rm", "rmdir", "unlink", "shred", "truncate", "dd", "mkfs",
    "sudo", "su", "doas", "chown", "chmod",
    "gh", "hub",
    "curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp", "sftp", "rsync", "ftp",
    "env", "printenv", "export", "set",
    "kill", "pkill", "killall", "shutdown", "reboot",
    "crontab", "systemctl", "service",
    "eval", "exec", "source", ".",
}
# Git subcommands agents may use. Everything else (commit, push, reset,
# clean, rm, checkout, branch -D, rebase, ...) is the orchestrator's job.
ALLOWED_GIT = {
    "status", "diff", "log", "show", "blame", "ls-files", "ls-tree", "grep", "rev-parse",
    "rev-list", "merge-base", "describe", "shortlog", "cat-file", "branch",
}
# `git branch` may only list; these flags change branches.
GIT_BRANCH_WRITE_FLAGS = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                          "-u", "--set-upstream-to", "--unset-upstream", "--edit-description"}

# Patterns refused anywhere in a command, whatever the first word is.
DENIED_SUBSTRINGS = [
    re.compile(p)
    for p in (
        r"\bfind\b.*\s-delete\b",
        r"\bfind\b.*-exec\s+rm\b",
        r"\bxargs\b.*\brm\b",
        r"/proc/[^/\s]+/environ",
        r"\.credentials\.json|\.git-credentials|/\.ssh/|\.netrc\b",
        r"\$\{?(GH_TOKEN|GITHUB_TOKEN|AGENT_GITHUB_TOKEN|AI_COMPANY_GITHUB_TOKEN|ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_AUTH_TOKEN)\b",
        r"--force\b|\s-f\s.*\bpush\b",
        r"\bos\.(remove|unlink|rmdir)\b|\bshutil\.rmtree\b|\brmSync\b|\bunlinkSync\b|\brimraf\b",
        r"\bpython[0-9.]*\s+-c\b.*\b(environ|getenv)\b",
        r"\bnode\s+-e\b.*process\.env",
        r">\s*/(?!dev/null|tmp/)",  # redirecting output to absolute paths outside the repo
    )
]
# Commands that write files. Roles with a limited write lane (everyone except
# the developer) may not run them; their writes go through Write/Edit, which
# are checked against the lane.
FILE_WRITING_COMMANDS = {"tee", "cp", "mv", "ln", "install", "touch", "patch"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
SUBSHELL = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
SCRATCH_DIR = Path(tempfile.gettempdir()).resolve()


def command_segments(command: str) -> list[list[str]]:
    """Split a shell command into simple commands (lists of words).

    Quote-aware, so `node -e "a(); eval(b)"` is one command, not three.
    Command substitutions are checked as commands of their own, including
    ones inside double quotes.
    """
    segments: list[list[str]] = []
    for match in SUBSHELL.finditer(command):
        segments.extend(command_segments(match.group(1) or match.group(2) or ""))
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:  # unbalanced quotes: fall back to a crude split
        tokens = re.split(r"\s+|(?=[;&|()])|(?<=[;&|()])", command)
    current: list[str] = []
    for token in tokens:
        if token and set(token) <= set(";&|()"):
            if current:
                segments.append(current)
            current = []
        elif token:
            current.append(token)
    if current:
        segments.append(current)
    return segments


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


@dataclass
class RolePolicy:
    can_read: bool = True
    can_bash: bool = False
    # Repository-relative prefixes this role may write under. Empty = no writes.
    write_prefixes: tuple[str, ...] = ()
    # May search and read the web (WebSearch, WebFetch).
    can_web: bool = False


@dataclass
class Guardrails:
    repo_root: Path
    policy: RolePolicy
    denials: list[str] = field(default_factory=list)

    # -- path helpers -------------------------------------------------------
    def _rel(self, raw: str) -> str | None:
        """Repository-relative POSIX path, or None if it escapes the repo."""
        path = Path(raw)
        if not path.is_absolute():
            path = self.repo_root / path
        try:
            resolved = path.resolve()
            return resolved.relative_to(self.repo_root.resolve()).as_posix()
        except (ValueError, OSError):
            return None

    @staticmethod
    def _in_scratch(raw: str) -> bool:
        try:
            Path(raw).resolve().relative_to(SCRATCH_DIR)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_secret(rel: str) -> bool:
        return any(p.search(rel) for p in SECRET_PATTERNS)

    # -- checks -------------------------------------------------------------
    def _check_read(self, tool_input: dict[str, Any]) -> Decision:
        if not self.policy.can_read:
            return Decision(False, "This role may not read files.")
        raw = tool_input.get("file_path") or tool_input.get("path") or "."
        rel = self._rel(raw)
        if rel is None:
            return Decision(False, f"Reading outside the repository is not allowed: {raw}")
        if self._is_secret(rel):
            return Decision(False, f"Reading secret-looking files is not allowed: {rel}")
        return Decision(True)

    def _check_write(self, tool_input: dict[str, Any]) -> Decision:
        if not self.policy.write_prefixes:
            return Decision(False, "This role may not write files.")
        raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        rel = self._rel(raw)
        if rel is None and self.policy.can_bash and self._in_scratch(raw):
            return Decision(True)  # throwaway scripts in the temp dir are fine
        if rel is None:
            return Decision(False, f"Writing outside the repository is not allowed: {raw}")
        if self._is_secret(rel):
            return Decision(False, f"Writing secret-looking files is not allowed: {rel}")
        if any(rel == p.rstrip("/") or rel.startswith(p) for p in PROTECTED_WRITE_PREFIXES):
            return Decision(False, f"{rel} is protected (git internals and CI workflows are human-only).")
        if not any(p in ("", ".") or rel == p.rstrip("/") or rel.startswith(p.rstrip("/") + "/") for p in self.policy.write_prefixes):
            allowed = ", ".join(self.policy.write_prefixes)
            return Decision(False, f"This role may only write under: {allowed}")
        return Decision(True)

    def _full_write(self) -> bool:
        return any(p in ("", ".") for p in self.policy.write_prefixes)

    def _check_shell_writes(self, first: str, words: list[str]) -> Decision:
        """Keep limited-lane roles (QA, reviewer) from writing files through the shell."""
        if first in FILE_WRITING_COMMANDS:
            return Decision(False, f"`{first}` writes files; this role may only write through the Write tool, inside its lane.")
        if first in ("sed", "perl") and any(w == "-i" or w.startswith("-i") or w.startswith("--in-place") for w in words[1:]):
            return Decision(False, f"In-place edits with `{first} -i` are not allowed for this role.")
        for i, word in enumerate(words):
            target = None
            if word in REDIRECTS:
                target = words[i + 1] if i + 1 < len(words) else ""
            else:
                m = re.match(r"^[0-9]*>>?(.+)$", word)
                if m and word[0] != "-":
                    target = m.group(1)
            if target is None or target.startswith("&") or target in ("/dev/null", "/dev/stdout", "/dev/stderr"):
                continue
            if self._in_scratch(target):
                continue
            if not self._check_write({"file_path": target}).allowed:
                return Decision(False, f"Redirecting output to {target} is outside this role's write lane.")
        return Decision(True)

    def _check_bash(self, tool_input: dict[str, Any]) -> Decision:
        if not self.policy.can_bash:
            return Decision(False, "This role may not run shell commands.")
        command = str(tool_input.get("command", ""))
        for pattern in DENIED_SUBSTRINGS:
            if pattern.search(command):
                return Decision(False, f"Command refused by safety policy (matched {pattern.pattern!r}).")
        for words in command_segments(command):
            # Skip leading VAR=value assignments.
            while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
                words = words[1:]
            if not words:
                continue
            first = Path(words[0]).name
            if first in DENIED_COMMANDS:
                return Decision(False, f"`{first}` is not allowed for agents (no deletes, no GitHub, no network tools, no env reads).")
            if first == "git":
                sub = next((w for w in words[1:] if not w.startswith("-")), "")
                if sub not in ALLOWED_GIT:
                    return Decision(False, f"`git {sub}` is not allowed. Agents may only inspect git; the orchestrator commits and pushes.")
                if sub == "branch":
                    args = words[words.index("branch") + 1:]
                    creates = [a for a in args if not a.startswith("-")] and not {"--list", "-l", "--contains", "--merged", "--no-merged", "--points-at"} & set(args)
                    if creates or GIT_BRANCH_WRITE_FLAGS & set(args):
                        return Decision(False, "`git branch` may only list branches for agents.")
            if not self._full_write():
                decision = self._check_shell_writes(first, words)
                if not decision.allowed:
                    return decision
            if first in ("npm", "pnpm", "yarn") and any(w in ("publish", "unpublish", "login", "adduser", "token") for w in words[1:]):
                return Decision(False, "Publishing or logging in to package registries is not allowed.")
            if first in ("pip", "pip3") and "uninstall" in words[1:]:
                return Decision(False, "Uninstalling packages is not allowed.")
        return Decision(True)

    def check(self, tool_name: str, tool_input: dict[str, Any]) -> Decision:
        if tool_name in READ_TOOLS:
            decision = self._check_read(tool_input)
        elif tool_name in WRITE_TOOLS:
            decision = self._check_write(tool_input)
        elif tool_name in BASH_TOOLS:
            decision = self._check_bash(tool_input)
        elif tool_name in WEB_TOOLS:
            decision = Decision(True) if self.policy.can_web else Decision(False, "This role may not use the web.")
        elif tool_name in SIDE_EFFECT_FREE_TOOLS:
            decision = Decision(True)
        else:
            decision = Decision(False, f"Tool {tool_name} is not enabled for this team.")
        if not decision.allowed:
            self.denials.append(f"{tool_name}: {decision.reason}")
        return decision


# --------------------------------------------------------------------- roles
PLUGIN_NAME = "ai-company"
DEFAULT_DOCS_DIR = "docs/ai-company"


def role_policies(docs_dir: str = DEFAULT_DOCS_DIR) -> dict[str, RolePolicy]:
    return {
        "manager": RolePolicy(can_read=True, can_bash=False, write_prefixes=(docs_dir,)),
        "designer": RolePolicy(can_read=True, can_bash=False, write_prefixes=(docs_dir,)),
        "developer": RolePolicy(can_read=True, can_bash=True, write_prefixes=(".",)),
        "reviewer": RolePolicy(can_read=True, can_bash=True, write_prefixes=()),
        "researcher": RolePolicy(can_read=True, can_bash=False, write_prefixes=(docs_dir,), can_web=True),
        "qa": RolePolicy(can_read=True, can_bash=True, write_prefixes=(docs_dir,)),
        "tech-writer": RolePolicy(
            can_read=True, can_bash=False, write_prefixes=("docs", docs_dir, "README.md", "CHANGELOG.md")
        ),
        "marketing": RolePolicy(can_read=True, can_bash=False, write_prefixes=("marketing",), can_web=True),
        "content-writer": RolePolicy(can_read=True, can_bash=False, write_prefixes=("content",), can_web=True),
        "support": RolePolicy(can_read=True, can_bash=False, write_prefixes=()),
    }


def role_from_hook(data: dict[str, Any], environ: dict[str, str]) -> str | None:
    """Which team role made this call, or None if it is not one of ours."""
    agent_type = str(data.get("agent_type") or "")
    if agent_type.startswith(PLUGIN_NAME + ":"):
        role = agent_type.split(":")[-1]
    elif environ.get("AI_COMPANY_ROLE"):
        # Set by the CI orchestrator for every agent run.
        role = environ["AI_COMPANY_ROLE"]
    else:
        return None
    return role if role in role_policies() else None


def repo_root_for(cwd: str) -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd or None, capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(cwd or ".")


def hook_main(stdin: Any = sys.stdin, environ: dict[str, str] | None = None) -> int:
    environ = dict(os.environ if environ is None else environ)
    try:
        data = json.load(stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # not our input; never break the session over it
    role = role_from_hook(data, environ)
    if role is None:
        return 0
    docs_dir = environ.get("AI_COMPANY_DOCS_DIR", DEFAULT_DOCS_DIR)
    guard = Guardrails(repo_root=repo_root_for(str(data.get("cwd") or "")), policy=role_policies(docs_dir)[role])
    decision = guard.check(str(data.get("tool_name") or ""), data.get("tool_input") or {})
    if decision.allowed:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"AI company safety rule ({role}): {decision.reason}",
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(hook_main())
