# Setup

## Local use (any project on your machine)

Nothing to configure. In Claude Code:

```
/plugin marketplace add ravikumar1002/ai-company-agents
/plugin install ai-company@ai-company-agents
```

The plugin uses whatever Claude login Claude Code already has (your Pro subscription). Update later with `/plugin marketplace update ai-company-agents`.

## GitHub use

You do steps 1 and 2 once. Step 3 is one command per repository, or one command for all of them.

### 1. The bot account's token (signed in as the bot, e.g. `code-ravi007`)

The bot works in repositories owned by your main account as a collaborator. Fine-grained tokens can only target repositories owned by the token's own account or an organization, so this needs a **classic** token:

**Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)**

- Note: `ai-company`
- Expiration: 90 days or more (set a reminder to renew)
- Scopes: **`repo`** only. Leave `workflow`, `admin:*`, `delete_repo` and everything else unticked.

Copy the token. Don't paste it into chat or any file.

The token can reach every repository the bot is a collaborator on, and only those, so only invite the bot where you want the team.

### 2. Your Claude token (on your own computer)

```bash
claude setup-token
```

It opens the browser, you approve, and it prints a token valid for one year. Copy it.

### 3. Turn the team on for repositories

```bash
gh auth login                      # as your main account
gh auth refresh -s workflow        # lets the script add the workflow file
git clone https://github.com/ravikumar1002/ai-company-agents && cd ai-company-agents
scripts/enable-repo.sh ravikumar1002/my-app            # one repo
scripts/enable-repo.sh ravikumar1002/a ravikumar1002/b # several
scripts/enable-repo.sh --all                           # asks about each of your repos
```

It asks for the two tokens without echoing them (or reads `CLAUDE_CODE_OAUTH_TOKEN` and `AI_COMPANY_GITHUB_TOKEN` from the environment), then for each repository:

1. invites the bot with Write access and accepts the invite as the bot,
2. stores the secrets `CLAUDE_CODE_OAUTH_TOKEN` and `AI_COMPANY_GITHUB_TOKEN` (and `ANTHROPIC_API_KEY` if you give one),
3. creates the `ai:build` label,
4. opens a PR adding `.github/workflows/ai-company.yml`.

Merge that PR and the team is live in that repository. Personal GitHub accounts have no account-wide secrets, so each repository stores its own copy; the script does that for you. (With a GitHub organization you could store the secrets once at organization level instead.)

**Manual alternative:** copy [templates/ai-company.yml](../templates/ai-company.yml) to `.github/workflows/ai-company.yml`, add the secrets under **Settings → Secrets and variables → Actions**, and add the bot as a collaborator. Inside Claude Code, `/ai-company:enable-github-automation` prepares the files for you.

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
