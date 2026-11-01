from pathlib import Path

import pytest

from ai_company.guardrails import Guardrails, RolePolicy

DEV = RolePolicy(can_read=True, can_bash=True, write_prefixes=(".",))
DESIGNER = RolePolicy(can_read=True, can_bash=False, write_prefixes=("docs/ai-company",))
MANAGER = RolePolicy(can_read=True, can_bash=False, write_prefixes=())


def guard(tmp_path: Path, policy: RolePolicy) -> Guardrails:
    return Guardrails(repo_root=tmp_path, policy=policy)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf src",
        "rm file.txt",
        "ls && rm -r build",
        "find . -name '*.tmp' -delete",
        "git push origin main",
        "git push --force",
        "git commit -m x",
        "git reset --hard HEAD~1",
        "git clean -fdx",
        "git rm old.py",
        "git branch -D main",
        "git branch new-feature",
        "git branch -m old new",
        "git checkout -- .",
        "gh pr create",
        "curl https://example.com",
        "env",
        "printenv ANTHROPIC_API_KEY",
        "echo $GH_TOKEN",
        "echo $CLAUDE_CODE_OAUTH_TOKEN",
        "cat ~/.claude/.credentials.json",
        "cat /proc/self/environ",
        "sudo apt-get install x",
        "npm publish",
        "python -c 'import shutil; shutil.rmtree(\"src\")'",
        "python3 -c 'import os; print(os.environ)'",
        "echo hi > /etc/passwd",
        "FOO=1 rm -rf x",
        "echo $(rm -rf x)",
        'echo "$(rm -rf x)"',
        "echo `rm -rf x`",
        "eval rm x",
        "ls; (rm -rf x)",
    ],
)
def test_dangerous_commands_are_denied(tmp_path, command):
    assert not guard(tmp_path, DEV).check("Bash", {"command": command}).allowed


@pytest.mark.parametrize(
    "command",
    ["node -e \"const x = eval('1'); console.log(x)\"", "node check.js > /tmp/out.txt 2>&1", "npm test", "pytest -q", "git status", "git diff origin/main", "git log --oneline -5", "git branch --show-current", "git branch -a", "git status --short && git branch --show-current && ls -la", "ls -la src", "npm install", "python -m pytest 2>&1 | tail -20", "mkdir -p src/components"],
)
def test_normal_dev_commands_are_allowed(tmp_path, command):
    assert guard(tmp_path, DEV).check("Bash", {"command": command}).allowed


def test_manager_cannot_write_or_run(tmp_path):
    g = guard(tmp_path, MANAGER)
    assert not g.check("Write", {"file_path": str(tmp_path / "a.md")}).allowed
    assert not g.check("Bash", {"command": "ls"}).allowed
    assert g.check("Read", {"file_path": str(tmp_path / "README.md")}).allowed


def test_designer_writes_only_design_docs(tmp_path):
    g = guard(tmp_path, DESIGNER)
    assert g.check("Write", {"file_path": str(tmp_path / "docs/ai-company/x/design.md")}).allowed
    assert not g.check("Write", {"file_path": str(tmp_path / "src/app.js")}).allowed
    assert not g.check("Write", {"file_path": str(tmp_path / "docs/ai-company-evil/x.md")}).allowed


def test_developer_write_boundaries(tmp_path):
    g = guard(tmp_path, DEV)
    assert g.check("Edit", {"file_path": str(tmp_path / "src/app.js")}).allowed
    assert g.check("Write", {"file_path": "relative/file.py"}).allowed
    assert not g.check("Write", {"file_path": "/etc/hosts"}).allowed
    assert not g.check("Write", {"file_path": "/usr/local/escape.txt"}).allowed
    assert not g.check("Write", {"file_path": str(tmp_path / ".github/workflows/ci.yml")}).allowed
    assert not g.check("Write", {"file_path": str(tmp_path / ".git/config")}).allowed
    assert not g.check("Write", {"file_path": str(tmp_path / "ai_company/guardrails.py")}).allowed
    assert not g.check("Write", {"file_path": str(tmp_path / ".env")}).allowed


def test_reads_stay_in_repo_and_skip_secrets(tmp_path):
    g = guard(tmp_path, DEV)
    assert not g.check("Read", {"file_path": "/etc/passwd"}).allowed
    assert not g.check("Read", {"file_path": str(tmp_path / ".env.local")}).allowed
    assert not g.check("Read", {"file_path": str(tmp_path / ".git/config")}).allowed
    assert g.check("Grep", {"pattern": "x", "path": str(tmp_path / "src")}).allowed
    assert g.check("Glob", {"pattern": "**/*.py"}).allowed


def test_unknown_tools_are_denied_and_recorded(tmp_path):
    g = guard(tmp_path, DEV)
    assert not g.check("WebFetch", {"url": "https://x"}).allowed
    assert g.denials and "WebFetch" in g.denials[0]


def test_bash_roles_may_write_scratch_files(tmp_path):
    import tempfile

    scratch = Path(tempfile.gettempdir()) / "check.js"
    assert guard(tmp_path, DEV).check("Write", {"file_path": str(scratch)}).allowed
    assert not guard(tmp_path, DESIGNER).check("Write", {"file_path": str(scratch)}).allowed


def test_new_roles_stay_in_their_lanes(tmp_path):
    from ai_company.guardrails import role_policies

    policies = role_policies("docs/ai-company")
    lanes = {
        "researcher": ("docs/ai-company/research/x.md", "src/app.py"),
        "qa": ("docs/ai-company/x/qa/report.md", "src/app.py"),
        "tech-writer": ("README.md", "src/app.py"),
        "marketing": ("marketing/x/launch-kit.md", "content/post.md"),
        "content-writer": ("content/post.md", "marketing/x.md"),
    }
    for role, (allowed, denied) in lanes.items():
        g = guard(tmp_path, policies[role])
        assert g.check("Write", {"file_path": allowed}).allowed, role
        assert not g.check("Write", {"file_path": denied}).allowed, role
    tw = guard(tmp_path, policies["tech-writer"])
    assert tw.check("Write", {"file_path": "docs/guide.md"}).allowed
    assert tw.check("Write", {"file_path": "CHANGELOG.md"}).allowed
    support = guard(tmp_path, policies["support"])
    assert not support.check("Write", {"file_path": "docs/x.md"}).allowed
    assert not support.check("Bash", {"command": "ls"}).allowed
    assert support.check("Read", {"file_path": "README.md"}).allowed


def test_only_research_and_writing_roles_use_the_web(tmp_path):
    from ai_company.guardrails import role_policies

    for role, policy in role_policies().items():
        g = guard(tmp_path, policy)
        expected = role in ("researcher", "marketing", "content-writer")
        assert g.check("WebSearch", {"query": "x"}).allowed is expected, role
        assert g.check("WebFetch", {"url": "https://example.com"}).allowed is expected, role


def test_team_code_and_config_are_protected(tmp_path):
    g = guard(tmp_path, RolePolicy(can_bash=True, write_prefixes=(".",)))
    for path in ("ai-company.toml", "plugins/ai-company/scripts/guard.py", ".ai-company/state/x.json", ".github/workflows/ci.yml"):
        assert not g.check("Write", {"file_path": path}).allowed, path


def test_team_token_variable_is_not_readable(tmp_path):
    g = guard(tmp_path, RolePolicy(can_bash=True, write_prefixes=(".",)))
    assert not g.check("Bash", {"command": "echo $AI_COMPANY_GITHUB_TOKEN"}).allowed


@pytest.mark.parametrize(
    "command",
    [
        "echo x > src/app.py",
        "echo x >> src/app.py",
        "echo x >src/app.py",
        "cat a | tee src/app.py",
        "cp docs/x.md src/app.py",
        "mv README.md other.md",
        "sed -i 's/a/b/' src/app.py",
        "touch src/new.py",
    ],
)
def test_limited_lane_roles_cannot_write_through_the_shell(tmp_path, command):
    from ai_company.guardrails import role_policies

    for role in ("qa", "reviewer"):
        assert not guard(tmp_path, role_policies("docs/ai-company")[role]).check("Bash", {"command": command}).allowed, (role, command)


def test_limited_lane_roles_can_still_redirect_inside_their_lane(tmp_path):
    import tempfile

    from ai_company.guardrails import role_policies

    qa = guard(tmp_path, role_policies("docs/ai-company")["qa"])
    assert qa.check("Bash", {"command": "npm test > docs/ai-company/x/qa/test.log 2>&1"}).allowed
    assert qa.check("Bash", {"command": "python check.py 2>/dev/null"}).allowed
    assert qa.check("Bash", {"command": f"echo x > {tempfile.gettempdir()}/shot.py"}).allowed
    assert guard(tmp_path, DEV).check("Bash", {"command": "echo x > src/app.py"}).allowed
