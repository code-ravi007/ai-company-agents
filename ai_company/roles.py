"""The team roles, loaded from the Claude Code plugin.

Each role's prompt, tool list and preloaded skills come from
`plugins/ai-company/agents/<role>.md` and `plugins/ai-company/skills/`, so
the agents behave the same in CI as they do in an interactive Claude Code
session. This module adds what only CI needs: the structured output schema
for each hand-off and the role's guardrail policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_company.guardrails import RolePolicy, role_policies
from ai_company.paths import plugin_dir

# The build pipeline: idea -> spec -> design -> code -> review -> QA -> docs.
BUILD_ROLES = ("manager", "designer", "developer", "reviewer", "qa", "tech-writer")
# Roles that each produce one document in a pull request, on request.
TASK_ROLES = ("researcher", "marketing", "content-writer")
ROLE_NAMES = BUILD_ROLES + TASK_ROLES + ("support",)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


def parse_markdown(text: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown file into (frontmatter, body).

    Supports the subset of YAML the plugin files use: `key: value` scalars,
    comma-separated values, and `- item` lists.
    """
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    current: str | None = None
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current:
            meta.setdefault(current, [])
            meta[current].append(item.group(1).strip())
            continue
        key, _, value = line.partition(":")
        current = key.strip()
        value = value.strip()
        if value:
            meta[current] = value
    return meta, match.group(2).strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def _strings() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


MANAGER_SCHEMA = _obj(
    {
        "title": {"type": "string", "description": "Short PR-style title for the change."},
        "summary": {"type": "string", "description": "Two to four sentences: what and why."},
        "branch_slug": {"type": "string"},
        "user_stories": _strings(),
        "acceptance_criteria": _strings(),
        "tasks": {
            "type": "array",
            "items": _obj(
                {
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "area": {"type": "string", "enum": ["design", "frontend", "backend", "infra", "docs", "tests"]},
                }
            ),
        },
        "out_of_scope": _strings(),
        "assumptions": _strings(),
        "needs_design": {"type": "boolean"},
        "blocked": {"type": "boolean"},
        "open_questions": _strings(),
    }
)

DESIGNER_SCHEMA = _obj(
    {
        "summary": {"type": "string", "description": "What the design covers, in a few sentences."},
        "screens": _strings(),
        "open_questions": _strings(),
    }
)

DEVELOPER_SCHEMA = _obj(
    {
        "summary": {"type": "string", "description": "What changed, for the PR description."},
        "files_changed": _strings(),
        "test_command": {"type": "string", "description": "The command that runs the tests, or empty."},
        "tests_passed": {"type": "boolean"},
        "notes": {"type": "string", "description": "Anything the reviewer or owner should know."},
    }
)

REVIEWER_SCHEMA = _obj(
    {
        "verdict": {"type": "string", "enum": ["approve", "request_changes"]},
        "summary": {"type": "string"},
        "blocking_issues": {
            "type": "array",
            "items": _obj(
                {
                    "file": {"type": "string"},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                }
            ),
        },
        "suggestions": _strings(),
        "criteria_checked": {
            "type": "array",
            "items": _obj({"criterion": {"type": "string"}, "met": {"type": "boolean"}, "evidence": {"type": "string"}}),
        },
    }
)


QA_SCHEMA = _obj(
    {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "summary": {"type": "string"},
        "bugs": {
            "type": "array",
            "items": _obj(
                {
                    "title": {"type": "string"},
                    "steps": {"type": "string"},
                    "expected": {"type": "string"},
                    "actual": {"type": "string"},
                    "screenshot": {"type": "string", "description": "File name of the screenshot, or empty."},
                }
            ),
        },
        "screenshots": _strings(),
        "not_tested": _strings(),
    }
)

TECH_WRITER_SCHEMA = _obj(
    {
        "summary": {"type": "string", "description": "What the docs now cover."},
        "files_changed": _strings(),
    }
)

DOCUMENT_SCHEMA = _obj(
    {
        "title": {"type": "string", "description": "Title of the document written."},
        "summary": {"type": "string", "description": "Two to four sentences for the pull request."},
        "highlights": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The three to five most useful points, e.g. the recommendation, the headline, key messages.",
        },
        "open_questions": _strings(),
    }
)

SUPPORT_LABELS = ("bug", "question", "enhancement", "duplicate", "needs-info", "invalid", "good first issue")

SUPPORT_SCHEMA = _obj(
    {
        "category": {"type": "string", "enum": ["bug", "question", "enhancement", "duplicate", "needs-info", "invalid"]},
        "labels": {"type": "array", "items": {"type": "string", "enum": list(SUPPORT_LABELS)}},
        "summary": {"type": "string", "description": "One or two sentences for the owner: what this issue is about."},
        "reply": {"type": "string", "description": "The reply to the issue author, in Markdown, under 120 words."},
        "ready_for_team": {"type": "boolean", "description": "A confirmed bug or small clear enhancement the build team can take."},
        "duplicate_of": {"type": "integer", "description": "Number of the open issue this duplicates, or 0."},
    }
)


@dataclass(frozen=True)
class Role:
    name: str
    system_prompt: str
    tools: tuple[str, ...]
    policy: RolePolicy
    output_schema: dict[str, Any]
    max_turns: int | None = None


SCHEMAS = {
    "manager": MANAGER_SCHEMA,
    "designer": DESIGNER_SCHEMA,
    "developer": DEVELOPER_SCHEMA,
    "reviewer": REVIEWER_SCHEMA,
    "qa": QA_SCHEMA,
    "tech-writer": TECH_WRITER_SCHEMA,
    "researcher": DOCUMENT_SCHEMA,
    "marketing": DOCUMENT_SCHEMA,
    "content-writer": DOCUMENT_SCHEMA,
    "support": SUPPORT_SCHEMA,
}


def load_skill(root: Path, name: str) -> str:
    path = root / "skills" / name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill {name!r} not found at {path}")
    return parse_markdown(path.read_text())[1]


def load_role(name: str, docs_dir: str, root: Path | None = None) -> Role:
    root = root or plugin_dir()
    meta, body = parse_markdown((root / "agents" / f"{name}.md").read_text())
    skills = _as_list(meta.get("skills"))
    prompt = body
    if skills:
        prompt += "\n\n# Skills\n\nThese skills are part of your instructions.\n"
        for skill in skills:
            prompt += f"\n\n## Skill: {skill}\n\n" + load_skill(root, skill)
    # In CI there is no human to ask; the orchestrator owns git and GitHub.
    prompt += (
        "\n\n# Running in CI\n\nYou are running unattended inside the team's orchestrator. "
        "Nobody can answer questions mid-task: use sensible defaults and say what you assumed. "
        "Return your final result in the required structured format."
    )
    max_turns = int(meta["maxTurns"]) if str(meta.get("maxTurns", "")).isdigit() else None
    return Role(
        name=name,
        system_prompt=prompt,
        tools=tuple(_as_list(meta.get("tools"))),
        policy=role_policies(docs_dir)[name],
        output_schema=SCHEMAS[name],
        max_turns=max_turns,
    )


def build_roles(docs_dir: str, root: Path | None = None) -> dict[str, Role]:
    return {name: load_role(name, docs_dir, root) for name in ROLE_NAMES}
