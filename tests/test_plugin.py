"""The Claude Code plugin: manifests, agents, skills and the safety hook."""

import io
import json
from pathlib import Path

import pytest

from ai_company.guardrails import hook_main
from ai_company.paths import plugin_dir
from ai_company.roles import ROLE_NAMES, build_roles, parse_markdown

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = plugin_dir()


def test_marketplace_points_at_the_plugin():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    [entry] = market["plugins"]
    assert entry["name"] == "ai-company"
    assert (ROOT / entry["source"]).resolve() == PLUGIN
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == entry["name"]


def test_every_agent_is_valid_and_its_skills_exist():
    for name in ROLE_NAMES:
        meta, body = parse_markdown((PLUGIN / "agents" / f"{name}.md").read_text())
        assert meta["name"] == name
        assert meta["description"] and body
        for skill in meta.get("skills", []):
            assert (PLUGIN / "skills" / skill / "SKILL.md").exists(), f"{name} preloads missing skill {skill}"


def test_every_skill_has_name_and_description():
    skills = sorted(p for p in (PLUGIN / "skills").iterdir() if p.is_dir())
    assert len(skills) >= 10
    for skill in skills:
        meta, body = parse_markdown((skill / "SKILL.md").read_text())
        assert meta.get("name") == skill.name
        assert meta.get("description") and body


def test_reviewer_and_planners_cannot_edit_code():
    roles = build_roles("docs/ai-company")
    assert "Edit" not in roles["reviewer"].tools and "Write" not in roles["reviewer"].tools
    assert "Bash" not in roles["manager"].tools and "Bash" not in roles["designer"].tools
    assert "## Skill: code-review" in roles["reviewer"].system_prompt


def test_hooks_json_runs_the_guard():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    command = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "scripts/guard.py" in command
    assert (PLUGIN / "scripts" / "guard.py").exists()


def _hook(payload: dict, environ: dict | None = None, capsys=None) -> dict | None:
    rc = hook_main(io.StringIO(json.dumps(payload)), environ or {})
    assert rc == 0
    out = capsys.readouterr().out if capsys else ""
    return json.loads(out) if out.strip() else None


@pytest.mark.parametrize(
    "agent_type, tool, tool_input, denied",
    [
        ("ai-company:developer", "Bash", {"command": "rm -rf src"}, True),
        ("ai-company:developer", "Bash", {"command": "git push origin main"}, True),
        ("ai-company:developer", "Bash", {"command": "npm test"}, False),
        ("ai-company:designer", "Write", {"file_path": "src/app.js"}, True),
        ("ai-company:designer", "Write", {"file_path": "docs/ai-company/x/design.md"}, False),
        ("ai-company:reviewer", "Edit", {"file_path": "src/app.js"}, True),
        ("ai-company:manager", "Bash", {"command": "ls"}, True),
        # Not one of the team's agents: your own session is never blocked.
        (None, "Bash", {"command": "rm -rf build"}, False),
        ("Explore", "Bash", {"command": "rm -rf build"}, False),
    ],
)
def test_hook_blocks_only_team_agents(tmp_path, capsys, agent_type, tool, tool_input, denied):
    payload = {"cwd": str(tmp_path), "tool_name": tool, "tool_input": tool_input}
    if agent_type:
        payload["agent_type"] = agent_type
    result = _hook(payload, capsys=capsys)
    assert (result is not None) == denied
    if denied:
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hook_uses_role_from_ci_environment(tmp_path, capsys):
    result = _hook({"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "gh pr list"}}, {"AI_COMPANY_ROLE": "developer"}, capsys)
    assert result and "gh" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_ignores_garbage_input(capsys):
    assert hook_main(io.StringIO("not json"), {}) == 0
    assert capsys.readouterr().out == ""


def test_caller_template_matches_skill():
    template = (ROOT / "templates" / "ai-company.yml").read_text()
    skill = (PLUGIN / "skills" / "enable-github-automation" / "SKILL.md").read_text()
    assert "uses: code-ravi007/ai-company-agents/.github/workflows/team.yml@main" in template
    assert template.strip() in skill


def test_structured_output_tool_is_allowed_for_every_role(tmp_path):
    # The Agent SDK returns each role's result through this tool.
    from ai_company.guardrails import Guardrails, role_policies

    for policy in role_policies().values():
        assert Guardrails(repo_root=tmp_path, policy=policy).check("StructuredOutput", {"title": "x"}).allowed


def test_claude_review_template():
    import yaml

    template = (ROOT / "templates" / "claude-review.yml").read_text()
    assert template == (ROOT / ".github" / "workflows" / "claude-review.yml").read_text()
    workflow = yaml.safe_load(template)
    for job in workflow["jobs"].values():
        assert job["permissions"]["contents"] == "read"  # comments only, never pushes
        step = job["steps"][-1]
        assert step["uses"] == "anthropics/claude-code-action@v1"
        assert step["with"]["claude_code_oauth_token"] == "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"
    assert "claude-review.yml" in (ROOT / "scripts" / "enable-repo.sh").read_text()
