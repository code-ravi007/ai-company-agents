import asyncio

from ai_company.config import load_config
from ai_company.pipeline import Pipeline
from ai_company.runner import SdkRunner, UsageLimitPause
from ai_company.state import RunState

from conftest import APPROVE, CHANGES, SPEC, FakeGitHub, FakeRunner, designer_writes, developer_writes, git


def test_local_idea_runs_every_stage(config, make_git, repo):
    runner = FakeRunner({
        "manager": [SPEC],
        "designer": [designer_writes],
        "developer": [developer_writes("<h1>Hello</h1>")],
        "reviewer": [APPROVE],
    })
    state = asyncio.run(Pipeline(config, runner, make_git()).run_idea("Add a greeting page"))

    assert state.stage == "done", state.error
    assert [c[0] for c in runner.calls] == ["manager", "designer", "developer", "reviewer"]
    assert state.branch == "ai/greeting-page"
    files = git(repo, "show", "--name-only", "--format=", "HEAD")
    assert "hello.html" in files
    assert "docs/ai-company/greeting-page/spec.md" in git(repo, "ls-files")
    assert "docs/ai-company/greeting-page/design.md" in git(repo, "ls-files")
    assert ".ai-company" not in git(repo, "ls-files")
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "ai/greeting-page"


def test_designer_is_skipped_for_internal_work(config, make_git):
    runner = FakeRunner({
        "manager": [{**SPEC, "needs_design": False}],
        "developer": [developer_writes("x")],
        "reviewer": [APPROVE],
    })
    state = asyncio.run(Pipeline(config, runner, make_git()).run_idea("Refactor"))
    assert state.stage == "done"
    assert "designer" not in [c[0] for c in runner.calls]


def test_review_loop_sends_feedback_back_to_developer(config, make_git):
    runner = FakeRunner({
        "manager": [SPEC],
        "designer": [designer_writes],
        "developer": [developer_writes("Hello"), developer_writes("Hello!")],
        "reviewer": [CHANGES, APPROVE],
    })
    state = asyncio.run(Pipeline(config, runner, make_git()).run_idea("Greeting"))
    assert state.stage == "done"
    assert state.review_round == 2
    second_dev_prompt = [p for r, p in runner.calls if r == "developer"][1]
    assert "no !" in second_dev_prompt


def test_review_rounds_are_capped(config, make_git):
    runner = FakeRunner({
        "manager": [SPEC],
        "designer": [designer_writes],
        "developer": [developer_writes(str(i)) for i in range(3)],
        "reviewer": [CHANGES, CHANGES, CHANGES],
    })
    state = asyncio.run(Pipeline(config, runner, make_git()).run_idea("Greeting"))
    assert state.stage == "done"
    assert state.review_round == config.max_review_rounds + 1
    assert state.review["verdict"] == "request_changes"


def test_usage_limit_pauses_and_resumes_without_redoing_work(config, make_git):
    runner = FakeRunner({
        "manager": [SPEC],
        "designer": [designer_writes],
        "developer": [UsageLimitPause(resets_at=1_900_000_000), developer_writes("Hello")],
        "reviewer": [APPROVE],
    })
    pipeline = Pipeline(config, runner, make_git())
    state = asyncio.run(pipeline.run_idea("Greeting"))
    assert state.stage == "developer"
    assert state.paused_until == 1_900_000_000

    state = asyncio.run(pipeline.run_idea("Greeting"))
    assert state.stage == "done"
    assert [c[0] for c in runner.calls].count("manager") == 1
    assert [c[0] for c in runner.calls].count("designer") == 1


def test_github_flow_opens_pr_and_tracks_status(config, make_git, repo):
    gh = FakeGitHub(issues={7: {"number": 7, "title": "Greeting page", "body": "Please add one"}})
    runner = FakeRunner({
        "manager": [SPEC],
        "designer": [designer_writes],
        "developer": [developer_writes("Hello")],
        "reviewer": [APPROVE],
    })
    state = asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_issue(7))

    assert state.stage == "done"
    assert state.branch == "ai/7-greeting-page"
    pr = gh.prs[0]
    assert pr["draft"] is False
    assert "Closes #7" in pr["body"]
    assert gh.review_requests == [(pr["number"], "code-ravi007")]
    assert gh.labels[7] == {"ai:pr-open"}
    # Branch was pushed to origin.
    assert "ai/7-greeting-page" in git(repo, "ls-remote", "--heads", "origin")
    # Status comment carries resumable state.
    restored = [RunState.from_comment(c["body"]) for c in gh.comments[7]]
    assert any(s and s.stage == "done" for s in restored)


def test_unapproved_work_becomes_draft_pr(config, make_git):
    gh = FakeGitHub(issues={8: {"number": 8, "title": "X", "body": ""}})
    runner = FakeRunner({
        "manager": [{**SPEC, "needs_design": False}],
        "developer": [developer_writes(str(i)) for i in range(3)],
        "reviewer": [CHANGES] * 3,
    })
    asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_issue(8))
    assert gh.prs[0]["draft"] is True
    assert "Unresolved review issues" in gh.prs[0]["body"]


def test_blocked_spec_asks_questions_instead_of_building(config, make_git):
    gh = FakeGitHub(issues={9: {"number": 9, "title": "Vague", "body": "make it better"}})
    runner = FakeRunner({"manager": [{**SPEC, "blocked": True, "open_questions": ["Better how?"]}]})
    state = asyncio.run(Pipeline(config, runner, make_git(), github=gh).run_issue(9))
    assert state.stage == "manager"
    assert "ai:needs-info" in gh.labels[9]
    assert any("Better how?" in c["body"] for c in gh.comments[9])
    assert not gh.prs


def test_paused_issue_resumes_from_github_state(config, make_git):
    gh = FakeGitHub(issues={5: {"number": 5, "title": "Greeting", "body": ""}})
    runner = FakeRunner({
        "manager": [SPEC],
        "designer": [UsageLimitPause(resets_at=100.0), designer_writes],
        "developer": [developer_writes("Hello")],
        "reviewer": [APPROVE],
    })
    pipeline = Pipeline(config, runner, make_git(), github=gh, clock=lambda: 50.0)
    asyncio.run(pipeline.run_issue(5))
    assert "ai:paused" in gh.labels[5]
    assert asyncio.run(pipeline.resume_paused()) == []  # window not reset yet

    # Fresh process (no local state file) after the reset.
    (config.repo_root / ".ai-company").rename(config.repo_root.parent / "old-state")
    pipeline = Pipeline(config, runner, make_git(), github=gh, clock=lambda: 200.0)
    [state] = asyncio.run(pipeline.resume_paused())
    assert state.stage == "done"
    assert [c[0] for c in runner.calls].count("manager") == 1


def test_config_from_toml_and_env(repo):
    (repo / "ai-company.toml").write_text('base_branch = "develop"\nallowed_triggerers = ["a", "b"]\n[developer]\nmax_turns = 7\n')
    cfg = load_config(repo, {"AI_COMPANY_DEVELOPER__MODEL": "claude-sonnet-5-5", "AI_COMPANY_MAX_REVIEW_ROUNDS": "4"})
    assert cfg.base_branch == "develop"
    assert cfg.allowed_triggerers == ("a", "b")
    assert cfg.developer.max_turns == 7
    assert cfg.developer.model == "claude-sonnet-5-5"
    assert cfg.max_review_rounds == 4
    assert cfg.manager.model == "claude-opus-5-5"


def test_runner_waits_until_reset():
    runner = SdkRunner(clock=lambda: 1000.0)
    assert runner._wait_for(1600.0, 1) == 605.0
    assert runner._wait_for(None, 3) == 120.0


def test_token_is_removed_from_environment():
    from ai_company.github import take_token

    env = {"AGENT_GITHUB_TOKEN": "secret", "GH_TOKEN": "other", "PATH": "/bin"}
    assert take_token(env) == "secret"
    assert env == {"PATH": "/bin"}


def test_subscription_is_preferred_and_hidden_from_env():
    from ai_company.credentials import Credentials

    env = {"CLAUDE_CODE_OAUTH_TOKEN": "sub", "ANTHROPIC_API_KEY": "key", "PATH": "/bin"}
    creds = Credentials.take_from_env(environ=env)
    assert env == {"PATH": "/bin"}
    assert creds.describe() == "Claude subscription"
    assert creds.env() == {"CLAUDE_CODE_OAUTH_TOKEN": "sub"}
    assert not creds.can_fall_back()  # fallback is opt-in


def test_api_key_only_and_forced_modes():
    from ai_company.credentials import Credentials

    assert Credentials(api_key="key").env() == {"ANTHROPIC_API_KEY": "key"}
    assert Credentials(oauth_token="sub", api_key="key", mode="api").env() == {"ANTHROPIC_API_KEY": "key"}
    assert Credentials().env() == {}


def test_limit_falls_back_to_api_key_when_allowed():
    from ai_company.credentials import Credentials
    from ai_company.roles import build_roles
    from ai_company.runner import RoleResult, _RetryableLimit

    seen = []

    class Runner(SdkRunner):
        async def _run_once(self, role, settings, prompt, cwd):
            seen.append(self.credentials.env())
            if len(seen) == 1:
                raise _RetryableLimit(resets_at=10**10)
            return RoleResult(role=role.name, output={})

    creds = Credentials(oauth_token="sub", api_key="key", api_fallback_on_limit=True)
    role = build_roles("docs")["manager"]
    asyncio.run(Runner(credentials=creds).run(role, None, "", None))
    assert seen == [{"CLAUDE_CODE_OAUTH_TOKEN": "sub"}, {"ANTHROPIC_API_KEY": "key"}]


def test_limit_pauses_without_fallback():
    import pytest

    from ai_company.credentials import Credentials
    from ai_company.roles import build_roles
    from ai_company.runner import _RetryableLimit

    class Runner(SdkRunner):
        async def _run_once(self, role, settings, prompt, cwd):
            raise _RetryableLimit(resets_at=10**10)

    creds = Credentials(oauth_token="sub", api_key="key")
    with pytest.raises(UsageLimitPause):
        asyncio.run(Runner(credentials=creds).run(build_roles("docs")["manager"], None, "", None))
