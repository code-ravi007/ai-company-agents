# AI company agents

A small AI company for [Claude Code](https://code.claude.com): ten agents that build, test, document, research, market and support your product, plus the skills they work with. Set it up once, then use it in any project, on your machine or on GitHub.

**Build team** (one pipeline, from idea to pull request)

| Role | Does | Can change |
|---|---|---|
| **Manager** | Turns an idea or issue into a spec: user stories, testable acceptance criteria, ordered tasks | Only the spec doc |
| **Designer** | Writes the design: user flow, screens and components, every state, exact copy, tokens, responsive and accessibility notes. Skipped for internal changes | Only the design doc |
| **Developer** | Implements the spec and design with tests, following the project's own conventions | Code in the project |
| **Reviewer** | Reads the diff, runs the tests, checks every acceptance criterion, approves or sends back concrete issues | Nothing (read and run only) |
| **QA tester** | Runs the app in a headless browser, clicks through every flow, takes screenshots, sends real bugs back to the Developer. User-facing changes only | Only its QA report and screenshots |
| **Tech writer** | Updates the README, docs and changelog for the change | Only `README.md`, `CHANGELOG.md`, `docs/` |

**Growth and support** (each on request, each ends in its own pull request or comment)

| Role | You ask by | You get |
|---|---|---|
| **Researcher** | label `ai:research` or comment `/ai research` | A sourced research brief in `docs/ai-company/research/` |
| **Marketing** | label `ai:marketing`, or comment `/ai marketing` on a merged PR | A launch kit in `marketing/`: positioning, landing copy, social posts, launch email, SEO |
| **Content writer** | label `ai:content` on an issue with the topic | A blog post or article draft in `content/` |
| **Support** | nothing: it runs on every new issue from someone else | Labels and a drafted reply for you (or a direct reply if you turn that on) |

Nobody posts, publishes or sends anything outside GitHub. Marketing and content are drafts for you to edit and use.

```
idea ─▶ Manager ─spec─▶ Designer ─design─▶ Developer ◀─feedback─ Reviewer
                                             ▲  │                   ▲
                                        bugs │  └───────diff────────┘
                                             │          │ approved
                                             └──────── QA tester (user-facing changes)
                                                        │ pass
                                                        ▼
                         Tech writer ─▶ you (locally) or the team (on GitHub) opens a PR; you merge
```

## What's inside

```
.claude-plugin/marketplace.json     the marketplace (this repo)
plugins/ai-company/                 the Claude Code plugin
  agents/                           manager, designer, developer, reviewer, qa, tech-writer,
                                    researcher, marketing, content-writer, support
  skills/                           product-spec, ux-design, accessibility, frontend-craft,
                                    implementation, testing, code-review,
                                    product-research, qa-testing, technical-writing,
                                    marketing-launch, content-writing, support-triage,
                                    build-feature, revise-feature, research, launch-kit,
                                    write-post, triage-issue, enable-github-automation
  hooks/hooks.json, scripts/guard.py  safety rules for the team's agents
ai_company/                         the GitHub orchestrator (Python, Claude Agent SDK)
.github/workflows/team.yml          reusable workflow any repo can call
templates/                          the workflows (team + Claude PR review) and optional config for a repo
scripts/enable-repo.sh              turn the team on for one repo, several, or all of yours
```

The orchestrator on GitHub loads the same agent files and skills as the plugin, so the team behaves the same everywhere.

## 1. Use it in any project on your machine

In Claude Code:

```
/plugin marketplace add code-ravi007/ai-company-agents
/plugin install ai-company@ai-company-agents
```

Then, in any project:

```
/ai-company:build-feature add a dark mode toggle to the settings page
```

The team writes `docs/ai-company/<slug>/spec.md` and `design.md`, builds on a branch `ai/<slug>`, reviews until approved, and then asks you before committing and opening a PR. You can also call one role directly, for example `@"ai-company:reviewer (agent)" review my last commit`, or use a skill on its own, such as `/ai-company:code-review`.

`/ai-company:revise-feature 42` addresses your review comments on PR #42. The other roles have their own commands: `/ai-company:research <question>`, `/ai-company:launch-kit <feature>`, `/ai-company:write-post <topic>` and `/ai-company:triage-issue <number>`.

Claude Code's normal permission prompts still apply: you approve shell commands and edits as usual (or allow them in your settings), and the safety hook blocks the dangerous ones before they ever reach you.

## 2. Use it on GitHub, in any repo

Once per repository (or for all of them at once):

```bash
git clone https://github.com/code-ravi007/ai-company-agents && cd ai-company-agents
scripts/enable-repo.sh code-ravi007/my-app        # or: scripts/enable-repo.sh --all
```

The script stores the secrets, creates the `ai:build` label and opens a PR that adds a 20-line workflow. Merge it, then:

| You do | The team does |
|---|---|
| Add the label `ai:build` to an issue | Builds it and opens a PR, requesting your review |
| Comment `/ai build` on an issue | Same, e.g. after answering the Manager's questions |
| Leave review comments on the PR, then comment `/ai revise` | Addresses them, re-reviews, pushes |
| Actions → *AI company* → *Run workflow* with an idea | Opens an issue for the idea and builds it |
| Add `ai:research`, `ai:marketing` or `ai:content` to an issue (or comment `/ai research`, `/ai marketing`, `/ai content`) | The Researcher, Marketing or Content writer writes one document and opens a PR |
| Someone else opens an issue | Support labels it and drafts a reply for you; comment `/ai triage` to run it on any issue |
| Open any pull request, or comment `@claude <question>` | Claude reviews it with inline comments, or answers (`claude-review.yml`) |

Each issue gets one status comment the team keeps up to date, plus labels (`ai:in-progress`, `ai:needs-info`, `ai:paused`, `ai:pr-open`, `ai:failed`). See [docs/SETUP.md](docs/SETUP.md) for the one-time setup (a GitHub token and a Claude token).

## Claude subscription or API key

The team runs on your Claude subscription (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`) or an API key (`ANTHROPIC_API_KEY`). With both, it uses the subscription; the API key is only an opt-in fallback when the usage limit is hit. When the limit is hit, a GitHub run **pauses**: it pushes its work, labels the issue `ai:paused`, and the hourly schedule resumes it after the reset. Use the subscription only for your own repositories; see [docs/SETUP.md](docs/SETUP.md#on-a-pro-subscription).

## Safety

`plugins/ai-company/scripts/guard.py` runs before every tool call the team's agents make, locally (as a plugin hook) and on GitHub (as a hook and as the SDK permission callback). It applies only to the team's agents; your own Claude Code session is not affected.

- **Nothing is deleted**: `rm`, `rmdir`, `unlink`, `find -delete`, `git rm`, `git clean`, `git reset --hard`, force pushes, and file deletes from Python or Node are refused.
- **Agents never touch git history or GitHub**: only `git status/diff/log/show` are allowed. You (locally) or the orchestrator (on GitHub) commit and open PRs.
- **Secrets stay secret**: tokens are removed from the orchestrator's environment and never stored in `.git/config`; agents can't read `.env` files, credential files, or token variables.
- **Each role stays in its lane**: the Manager, Designer, Researcher and QA tester write only the team's docs, the Tech writer only documentation, Marketing only `marketing/`, the Content writer only `content/`; the Reviewer and Support write nothing. Nobody edits CI workflows, `.git/`, or the team's own code.
- **Web access only where needed**: only the Researcher, Marketing and Content writer can search and read the web, and nobody can post anything.
- **Strangers can't steer the team**: Support reads issues from anyone, but it is read-only and can only add labels from a fixed list and one comment; agent-written replies never @-mention anyone.
- **Only you trigger it and only you merge**: the team ignores events from anyone not in `allowed_triggerers` (default: the repo owner), and it cannot merge.

## Development

```bash
pip install -e '.[dev]'
pytest                                       # no API calls
claude plugin validate plugins/ai-company    # plugin structure
ai-company idea --local "A static page with a click counter"   # full run, no GitHub
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it fits together.
