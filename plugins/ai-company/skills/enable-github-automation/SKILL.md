---
name: enable-github-automation
description: Turn on the AI company team for the current GitHub repository, so labelling an issue `ai:build` makes the team open a pull request automatically. Adds a small workflow file and config, and lists the secrets to add. Use when the user wants the team to run on GitHub for this repo.
disable-model-invocation: true
---

# Enable the team on GitHub for this repository

1. Confirm this is a git repository with a GitHub remote (`git remote -v`) and find `owner/repo`.
2. Create `.github/workflows/ai-company.yml` with exactly this content (do not change the `uses:` line except the version tag):

```yaml
name: AI company
on:
  issues:
    types: [labeled]
  issue_comment:
    types: [created]
  pull_request_review:
    types: [submitted]
  workflow_dispatch:
    inputs:
      idea:
        description: "Idea to build (opens an issue first)"
        required: false
      issue:
        description: "Or: an issue number to build"
        required: false
  schedule:
    - cron: "17 * * * *"   # resumes runs paused by the usage limit

jobs:
  team:
    uses: ravikumar1002/ai-company-agents/.github/workflows/team.yml@main
    secrets: inherit
```

3. Optionally create `ai-company.toml` at the repository root with the project's test command, for example `test_command = "npm test"`. Everything else has sensible defaults.
4. Do not commit. Show the user the two files and tell them to:
   - commit them (or let you commit on a branch and open a PR, if they ask),
   - add the repository secrets `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) and `AI_COMPANY_GITHUB_TOKEN` (the bot account's token) under Settings → Secrets and variables → Actions, or run `scripts/enable-repo.sh owner/repo` from the ai-company-agents checkout, which does all of this in one go,
   - make sure the bot account is a collaborator with Write access.
5. Never ask the user to paste a token into the chat.
