# Setup

## Local use (any project on your machine)

Nothing to configure. In Claude Code:

```
/plugin marketplace add code-ravi007/ai-company-agents
/plugin install ai-company@ai-company-agents
```

The plugin uses whatever Claude login Claude Code already has (your Pro subscription). Update later with `/plugin marketplace update ai-company-agents`.

## GitHub use

You do steps 1 and 2 once. Step 3 is one command per repository, or one command for all of them.

### 1. A GitHub token for the account the team works as

Everything runs under one GitHub account, `code-ravi007`: it owns the repositories, and the team commits and opens pull requests as it. (Working in repositories owned by a different account also works; see "Repositories owned by another account" below.)

Signed in as `code-ravi007`: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

- Name: `ai-company`; expiration: 90 days or more (set a reminder to renew)
- Repository access: **All repositories** (or only the ones you want the team in)
- Repository permissions: **Contents**, **Issues** and **Pull requests**: Read and write. **Metadata**: Read. Nothing else; in particular no Administration and no Workflows.

Copy the token. Don't paste it into chat or any file.

### 2. Your Claude token (on your own computer)

```bash
claude setup-token
```

It opens the browser, you approve, and it prints a token valid for one year. Copy it.

### 3. Turn the team on for repositories

```bash
gh auth login                      # as code-ravi007
gh auth refresh -s workflow        # lets the script add the workflow file
git clone https://github.com/code-ravi007/ai-company-agents && cd ai-company-agents
scripts/enable-repo.sh code-ravi007/my-app            # one repo
scripts/enable-repo.sh code-ravi007/a code-ravi007/b # several
scripts/enable-repo.sh --all                           # asks about each of your repos
```

It asks for the two tokens without echoing them (or reads `CLAUDE_CODE_OAUTH_TOKEN` and `AI_COMPANY_GITHUB_TOKEN` from the environment), then for each repository:

1. stores the secrets `CLAUDE_CODE_OAUTH_TOKEN` and `AI_COMPANY_GITHUB_TOKEN` (and `ANTHROPIC_API_KEY` if you give one),
2. creates the `ai:build` label,
3. opens a PR adding `.github/workflows/ai-company.yml`.

Merge that PR and the team is live in that repository. Personal GitHub accounts have no account-wide secrets, so each repository stores its own copy; the script does that for you. (With a GitHub organization you could store the secrets once at organization level instead.)

**Manual alternative:** copy [templates/ai-company.yml](../templates/ai-company.yml) to `.github/workflows/ai-company.yml` and add the secrets under **Settings → Secrets and variables → Actions**. Inside Claude Code, `/ai-company:enable-github-automation` prepares the files for you.

### Repositories owned by another account

If a repository belongs to a different account, set `AI_COMPANY_BOT=code-ravi007` and run the script signed in as that repository's owner: it then also invites `code-ravi007` as a collaborator and accepts the invite. Fine-grained tokens can't reach another personal account's repositories, so in that case the token must be a classic token with only the `repo` scope.

### Optional per-repository settings

Copy [templates/ai-company.toml](../templates/ai-company.toml) to the repository root as `ai-company.toml` to set the test command, models, review rounds and so on. Repository variables override it: `AI_COMPANY_OWNER_LOGIN`, `AI_COMPANY_ALLOWED_TRIGGERERS`, `AI_COMPANY_API_FALLBACK_ON_LIMIT`.

### Recommended: protect `main`

**Settings → Branches → Add rule** for `main`: require a pull request and one approval. Then nothing lands on `main` without you, whatever happens.

## On a Pro subscription

- **Usage limits are shared** with your own Claude and Claude Code use. A big feature can use up a usage window.
- **When the limit is hit, GitHub runs pause and resume** after the reset (the caller workflow's hourly schedule picks them up). Nothing is lost.
- **Stretch the limits** by using `claude-sonnet-5-5` for the Manager, Designer and Reviewer in `ai-company.toml` and keeping the strongest model for the Developer. If your plan doesn't include a model, switch that role to one it does.
- **Personal use only.** The token is tied to your own subscription. Use it for your own repositories and don't use it to run the team for other people; use an API key for that.
- **Optional paid fallback:** add `ANTHROPIC_API_KEY` and set the repository variable `AI_COMPANY_API_FALLBACK_ON_LIMIT` to `true` to switch to the API key instead of pausing.

## Updating the team

Every repository calls `team.yml@main`, and the plugin installs from `main`. Merging a change into this repository rolls it out everywhere on the next run (locally, after `/plugin marketplace update ai-company-agents`). To pin a repository to a fixed version, change `@main` in its workflow to a tag or commit SHA and set `tool_ref` to the same value.
