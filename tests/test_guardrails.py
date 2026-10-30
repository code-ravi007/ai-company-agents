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
