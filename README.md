# AI company agents

A small AI product team for [Claude Code](https://code.claude.com): a **Manager**, a **Designer**, a **Developer** and a **Reviewer**, plus the skills they work with. Set it up once, then use it in any project, on your machine or on GitHub.

| Role | Does | Can change |
|---|---|---|
| **Manager** | Turns an idea or issue into a spec: user stories, testable acceptance criteria, ordered tasks | Only the spec doc |
| **Designer** | Writes the design: user flow, screens and components, every state, exact copy, tokens, responsive and accessibility notes. Skipped for internal changes | Only the design doc |
| **Developer** | Implements the spec and design with tests, following the project's own conventions | Code in the project |
| **Reviewer / QA** | Reads the diff, runs the tests, checks every acceptance criterion, approves or sends back concrete issues | Nothing (read and run only) |

```
idea ─▶ Manager ─spec─▶ Designer ─design─▶ Developer ◀─feedback─ Reviewer
                                               │                    ▲
                                               └────────diff────────┘
                                                       │ approved
                                                       ▼
                                  you (locally) or the bot (on GitHub) opens a PR; you merge
```

## What's inside

```
.claude-plugin/marketplace.json     the marketplace (this repo)
plugins/ai-company/                 the Claude Code plugin
  agents/                           manager, designer, developer, reviewer
  skills/                           product-spec, ux-design, accessibility, frontend-craft,
                                    implementation, testing, code-review,
                                    build-feature, revise-feature, enable-github-automation
  hooks/hooks.json, scripts/guard.py  safety rules for the team's agents
ai_company/                         the GitHub orchestrator (Python, Claude Agent SDK)
.github/workflows/team.yml          reusable workflow any repo can call
templates/                          the 20-line workflow and optional config for a repo
scripts/enable-repo.sh              turn the team on for one repo, several, or all of yours
```

The orchestrator on GitHub loads the same agent files and skills as the plugin, so the team behaves the same everywhere.

## 1. Use it in any project on your machine

In Claude Code:

```
/plugin marketplace add ravikumar1002/ai-company-agents
/plugin install ai-company@ai-company-agents
```

Then, in any project:

```
/ai-company:build-feature add a dark mode toggle to the settings page
```

The team writes `docs/ai-company/<slug>/spec.md` and `design.md`, builds on a branch `ai/<slug>`, reviews until approved, and then asks you before committing and opening a PR. You can also call one role directly, for example `@"ai-company:reviewer (agent)" review my last commit`, or use a skill on its own, such as `/ai-company:code-review`.

`/ai-company:revise-feature 42` addresses your review comments on PR #42.

Claude Code's normal permission prompts still apply: you approve shell commands and edits as usual (or allow them in your settings), and the safety hook blocks the dangerous ones before they ever reach you.

## 2. Use it on GitHub, in any repo

Once per repository (or for all of them at once):

```bash
git clone https://github.com/ravikumar1002/ai-company-agents && cd ai-company-agents
scripts/enable-repo.sh ravikumar1002/my-app        # or: scripts/enable-repo.sh --all
```

The script invites the bot account, stores the secrets, creates the `ai:build` label and opens a PR that adds a 20-line workflow. Merge it, then:

| You do | The team does |
|---|---|
| Add the label `ai:build` to an issue | Builds it and opens a PR, requesting your review |
| Comment `/ai build` on an issue | Same, e.g. after answering the Manager's questions |
| Leave review comments on the PR, then comment `/ai revise` | Addresses them, re-reviews, pushes |
| Actions → *AI company* → *Run workflow* with an idea | Opens an issue for the idea and builds it |

Each issue gets one status comment the team keeps up to date, plus labels (`ai:in-progress`, `ai:needs-info`, `ai:paused`, `ai:pr-open`, `ai:failed`). See [docs/SETUP.md](docs/SETUP.md) for the one-time setup (bot token, Claude token).

## Claude subscription or API key

The team runs on your Claude subscription (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`) or an API key (`ANTHROPIC_API_KEY`). With both, it uses the subscription; the API key is only an opt-in fallback when the usage limit is hit. When the limit is hit, a GitHub run **pauses**: it pushes its work, labels the issue `ai:paused`, and the hourly schedule resumes it after the reset. Use the subscription only for your own repositories; see [docs/SETUP.md](docs/SETUP.md#on-a-pro-subscription).

## Safety

`plugins/ai-company/scripts/guard.py` runs before every tool call the team's agents make, locally (as a plugin hook) and on GitHub (as a hook and as the SDK permission callback). It applies only to the team's agents; your own Claude Code session is not affected.

- **Nothing is deleted**: `rm`, `rmdir`, `unlink`, `find -delete`, `git rm`, `git clean`, `git reset --hard`, force pushes, and file deletes from Python or Node are refused.
- **Agents never touch git history or GitHub**: only `git status/diff/log/show` are allowed. You (locally) or the orchestrator (on GitHub) commit and open PRs.
- **Secrets stay secret**: tokens are removed from the orchestrator's environment and never stored in `.git/config`; agents can't read `.env` files, credential files, or token variables.
- **Each role stays in its lane**: the Manager and Designer write only docs, the Reviewer writes nothing, nobody edits CI workflows, `.git/`, or the team's own code.
- **Only you trigger it and only you merge**: the team ignores events from anyone not in `allowed_triggerers` (default: the repo owner), and it cannot merge.

## Development

```bash
pip install -e '.[dev]'
pytest                                       # no API calls
claude plugin validate plugins/ai-company    # plugin structure
ai-company idea --local "A static page with a click counter"   # full run, no GitHub
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it fits together.
