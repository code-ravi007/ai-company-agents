# Architecture

One repository, two ways to run the same team.

```
plugins/ai-company/          ← single source of truth for the team
  agents/*.md                  role prompts, tools, preloaded skills
  skills/*/SKILL.md            the know-how each role uses + orchestration playbooks
  hooks/hooks.json             PreToolUse → scripts/guard.py
  scripts/guard.py             the safety policy (stdlib only)

Locally (Claude Code plugin)            On GitHub (reusable workflow)
────────────────────────────            ─────────────────────────────
/ai-company:build-feature skill         .github/workflows/team.yml
  main session coordinates                ai_company/ orchestrator (Python)
  subagents: ai-company:manager …         one Agent SDK session per role, built from
  hook blocks unsafe agent calls            the same agents/*.md + skills
  you approve commit + PR                  hook + can_use_tool both enforce guard.py
                                           bot account commits, pushes, opens PR
```

## Python orchestrator (`ai_company/`)

```
cli.py         entry point; `event` turns a GitHub Actions event into a pipeline call
pipeline.py    stages, review loop, pause/resume, PRs, labels, status comment
roles.py       loads agents/*.md and their skills from the plugin; output schemas
runner.py      one Agent SDK session per role; usage-limit wait, fallback, pause
guardrails.py  loads plugins/ai-company/scripts/guard.py; SDK permission callback
credentials.py subscription token or API key, handed only to the agent process
github.py      git and GitHub (gh api) operations; token handling
state.py       resumable run state (local file + hidden marker in the issue comment)
render.py      prompts, spec markdown, comments, PR body
config.py      defaults < ai-company.toml < AI_COMPANY_* env vars
paths.py       where the plugin lives ($AI_COMPANY_PLUGIN_DIR or the checkout)
```

Why a code-driven pipeline on GitHub instead of one agent spawning subagents: each stage gets its own tool list and policy, returns JSON against a schema the code can branch on (`needs_design`, `blocked`, `verdict`), state is checkpointed after every stage so a usage-limit pause resumes at the right step, and every side effect (commit, push, PR, comment) happens in code with a token the agents never see. Locally a human is present, so the plugin lets Claude coordinate the subagents and asks before committing.

## A GitHub run

1. The caller repo's workflow calls `team.yml`, which checks out this repository into the runner's temp directory (outside the project), installs it, and checks out the project.
2. `ai-company event` checks the sender is allowed, loads saved state from the issue's status comment, labels `ai:in-progress`.
3. **Manager** → spec JSON; blocked questions go to the issue (`ai:needs-info`).
4. Branch `ai/<issue>-<slug>`; `docs/ai-company/<slug>/spec.md`.
5. **Designer** (if needed) → `design.md`.
6. **Developer** → code + tests; orchestrator runs `test_command`; checkpoint commit.
7. **Reviewer** → verdict; `request_changes` loops back to 6, up to `max_review_rounds`.
8. Push, open PR (draft if not approved), assign and request review from the owner, comment on the issue.

On a usage limit: wait if the reset is under 30 minutes away, else switch to the API key if `api_fallback_on_limit`, else pause (`ai:paused`) and let the hourly schedule resume it.

## Roles beyond the build pipeline

- **QA tester** (`qa`) and **Tech writer** (`tech-writer`) are pipeline stages: after the reviewer approves a user-facing change, QA runs the app in a headless browser and writes `docs/ai-company/<slug>/qa/`; a `fail` sends its bugs back to the developer (at most `max_qa_rounds` times, then the PR is a draft). The tech writer then updates README, docs and CHANGELOG before the PR opens. Run state stages: manager, designer, developer, reviewer, qa, docs, pr, done.
- **Researcher**, **Marketing** and **Content writer** are document tasks (`Pipeline.run_task`): one agent run writes one file (`docs/ai-company/research/`, `marketing/<slug>/launch-kit.md`, `content/<slug>.md`), then the orchestrator commits it on `ai/<kind>-<issue>-<slug>` and opens a PR. Their run state has `kind` set to the role, so pauses resume as the same task and `/ai revise` revises the document with the same agent.
- **Support** (`Pipeline.triage_issue`) runs on `issues: opened` from anyone but the owner and allowed triggerers. It is read-only (no writes, no shell, no web). The orchestrator applies only labels from a fixed list and posts one comment; @-mentions in agent-written text are defused.

## Extending

- **A new role** (say, a Tech Writer): add `agents/writer.md`, a policy in `guard.py:role_policies`, a schema and stage in `roles.py`/`pipeline.py`, and a step in `skills/build-feature`.
- **A new skill**: add `skills/<name>/SKILL.md` and list it under `skills:` in the agents that should preload it.
- **Project rules**: put them in the project's `CLAUDE.md` or README; every role reads the repository before working.
