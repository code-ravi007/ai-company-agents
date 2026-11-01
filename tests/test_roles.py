"""The six roles added on top of the build pipeline: document tasks and support."""

import asyncio
import json
import re

import pytest

from ai_company import cli
from ai_company.pipeline import Pipeline
from ai_company.runner import UsageLimitPause
from ai_company.state import RunState

from conftest import FakeGitHub, FakeRunner, git

DOC = {"title": "Habit trackers compared", "summary": "Five apps compared.", "highlights": ["Streaks win"], "open_questions": []}
TRIAGE = {
    "category": "bug",
    "labels": ["bug", "not-a-real-label"],
    "summary": "Crash on save",
    "reply": "Thanks @someone! Which version are you on?",
    "ready_for_team": True,
    "duplicate_of": 0,
}


def writes_doc(cwd, prompt):
    path = re.search(r"`([^`]+\.md)`", prompt).group(1)
    (cwd / path).parent.mkdir(parents=True, exist_ok=True)
    (cwd / path).write_text("# Doc\n")
    return DOC


@pytest.mark.parametrize(
    "role,expected_path",
    [
        ("researcher", "docs/ai-company/research/4-habit-tracker-apps.md"),
        ("marketing", "marketing/4-habit-tracker-apps/launch-kit.md"),
        ("content-writer", "content/4-habit-tracker-apps.md"),
    ],
)
def test_task_writes_one_document_and_opens_a_pr(config, make_git, repo, role, expected_path):
    gh = FakeGitHub(issues={4: {"number": 4, "title": "Habit tracker apps", "body": "Compare them"}})
    runner = FakeRunner({role: [writes_doc]})
    state = asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_task(role, 4))

    assert state.stage == "done", state.error
    assert expected_path in git(repo, "ls-files")
    pr = gh.prs[0]
    assert "Closes #4" in pr["body"] and expected_path in pr["body"]
    assert "Nothing has been posted" in pr["body"]
    assert gh.labels[4] == {"ai:pr-open"}


def test_task_on_a_pr_refers_to_it_instead_of_closing(config, make_git):
    gh = FakeGitHub(issues={9: {"number": 9, "title": "Dark mode", "body": "Adds dark mode", "pull_request": {}}})
    runner = FakeRunner({"marketing": [writes_doc]})
    asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_task("marketing", 9))
    assert "Refs #9" in gh.prs[0]["body"] and "Closes" not in gh.prs[0]["body"]


def test_task_that_writes_nothing_fails(config, make_git):
    gh = FakeGitHub(issues={4: {"number": 4, "title": "Topic", "body": ""}})
    runner = FakeRunner({"content-writer": [DOC]})
    state = asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_task("content-writer", 4))
    assert "did not write" in state.error
    assert "ai:failed" in gh.labels[4]


def test_task_that_leaves_an_existing_file_untouched_fails(config, make_git, repo):
    target = repo / "content" / "4-topic.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Old post\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "old post")
    git(repo, "push", "-q", "origin", "HEAD")
    gh = FakeGitHub(issues={4: {"number": 4, "title": "Topic", "body": ""}})
    runner = FakeRunner({"content-writer": [DOC]})
    state = asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_task("content-writer", 4))
    assert "did not write" in state.error


def test_two_issues_with_the_same_title_get_separate_files(config, make_git, repo):
    gh = FakeGitHub(issues={
        4: {"number": 4, "title": "Launch plan", "body": ""},
        5: {"number": 5, "title": "Launch plan", "body": ""},
    })
    runner = FakeRunner({"marketing": [writes_doc, writes_doc]})
    pipeline = Pipeline(config, runner, make_git(), github=gh)
    paths = [asyncio.run(pipeline.run_task("marketing", n)).task["path"] for n in (4, 5)]
    assert paths[0] != paths[1]


def test_resume_picks_the_run_that_paused(config, make_git):
    gh = FakeGitHub(issues={6: {"number": 6, "title": "Pricing research", "body": ""}})
    runner = FakeRunner({"researcher": [UsageLimitPause(resets_at=100.0), writes_doc]})
    pipeline = Pipeline(config, runner, make_git(), github=gh, clock=lambda: 200.0)
    asyncio.run(pipeline.run_task("researcher", 6))
    finished_build = RunState(key="issue-6", issue=6, stage="done")
    gh.comments.setdefault(6, []).append({"id": 999, "body": finished_build.marker()})
    [state] = asyncio.run(pipeline.resume_paused())
    assert state.kind == "researcher" and state.stage == "done"


def test_paused_task_resumes_as_the_same_task(config, make_git):
    gh = FakeGitHub(issues={6: {"number": 6, "title": "Pricing research", "body": ""}})
    runner = FakeRunner({"researcher": [UsageLimitPause(resets_at=100.0), writes_doc]})
    pipeline = Pipeline(config, runner, make_git(), github=gh, clock=lambda: 200.0)
    asyncio.run(pipeline.run_task("researcher", 6))
    assert "ai:paused" in gh.labels[6]
    [state] = asyncio.run(pipeline.resume_paused())
    assert state.kind == "researcher" and state.stage == "done"
    assert [c[0] for c in runner.calls] == ["researcher", "researcher"]


def test_support_labels_and_drafts_a_reply_for_the_owner(config, make_git):
    gh = FakeGitHub(issues={11: {"number": 11, "title": "Crash", "body": "It crashes", "user": {"login": "stranger"}}})
    runner = FakeRunner({"support": [TRIAGE]})
    asyncio.run(Pipeline(config, runner, make_git(), github=gh).triage_issue(11))

    assert gh.labels[11] == {"bug"}  # unknown labels are dropped
    comment = gh.comments[11][-1]["body"]
    assert "Support triage for @code-ravi007" in comment
    assert "Suggested reply" in comment and "ai:build" in comment
    assert "@someone" not in comment  # agent-written mentions never ping anyone
    assert not gh.prs


def test_support_can_reply_directly_when_allowed(config, make_git):
    from dataclasses import replace

    gh = FakeGitHub(issues={12: {"number": 12, "title": "How?", "body": "How do I start?"}})
    runner = FakeRunner({"support": [{**TRIAGE, "category": "question", "labels": ["question"]}]})
    asyncio.run(Pipeline(replace(config, support_auto_reply=True), runner, make_git(), github=gh).triage_issue(12))
    comment = gh.comments[12][-1]["body"]
    assert comment.startswith("Thanks") and "Automated reply" in comment


# ------------------------------------------------------------- event routing
class Recorder:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def __getattr__(self, name):
        async def record(*args):
            self.calls.append((name, *args))
        return record


def dispatch(monkeypatch, tmp_path, config, name, event):
    recorder = Recorder(config)
    monkeypatch.setattr(cli, "_build", lambda args: recorder)
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", name)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    cli._dispatch_event(None)
    return recorder.calls


def test_new_issue_from_a_stranger_goes_to_support(monkeypatch, tmp_path, config):
    from dataclasses import replace

    event = {"action": "opened", "issue": {"number": 3}, "sender": {"login": "stranger"}}
    assert dispatch(monkeypatch, tmp_path, replace(config, support_enabled=True), "issues", event) == [("triage_issue", 3)]


def test_support_is_off_by_default(monkeypatch, tmp_path, config):
    event = {"action": "opened", "issue": {"number": 3}, "sender": {"login": "stranger"}}
    assert dispatch(monkeypatch, tmp_path, config, "issues", event) == []


def test_owner_issues_and_bot_issues_skip_support(monkeypatch, tmp_path, config):
    from dataclasses import replace

    config = replace(config, support_enabled=True)
    for login in ("code-ravi007", "dependabot[bot]"):
        event = {"action": "opened", "issue": {"number": 3}, "sender": {"login": login}}
        assert dispatch(monkeypatch, tmp_path, config, "issues", event) == []


def test_task_labels_and_commands_start_tasks(monkeypatch, tmp_path, config):
    labelled = {"action": "labeled", "label": {"name": "ai:content"}, "issue": {"number": 5}, "sender": {"login": "code-ravi007"}}
    assert dispatch(monkeypatch, tmp_path, config, "issues", labelled) == [("run_task", "content-writer", 5)]
    comment = {"comment": {"body": "/ai marketing"}, "issue": {"number": 8, "pull_request": {}}, "sender": {"login": "code-ravi007"}}
    assert dispatch(monkeypatch, tmp_path, config, "issue_comment", comment) == [("run_task", "marketing", 8)]


def test_strangers_cannot_start_tasks(monkeypatch, tmp_path, config):
    labelled = {"action": "labeled", "label": {"name": "ai:research"}, "issue": {"number": 5}, "sender": {"login": "stranger"}}
    assert dispatch(monkeypatch, tmp_path, config, "issues", labelled) == []
