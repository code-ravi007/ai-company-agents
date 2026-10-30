---
name: revise-feature
description: Address review feedback on a feature the team built - collect the owner's pull request comments or the user's notes, have the developer fix them, re-run the reviewer, then offer to push. Use when the user asks the team to revise, fix review comments, or update a pull request.
argument-hint: <PR number/URL or feedback text>
---

# Revise a feature

Feedback source: $ARGUMENTS

1. **Collect feedback.** If given a pull request and `gh` is available, read its review comments, reviews and conversation comments from the repository owner (`gh pr view <n> --comments`, `gh api repos/{owner}/{repo}/pulls/<n>/comments`). Otherwise use the text the user gave. Check out the pull request's branch (`gh pr checkout <n>`) if you are not on it.
2. **Find the spec and design** under `docs/ai-company/<slug>/` on that branch, if they exist.
3. **Developer.** Delegate to the **developer** subagent with the feedback, quoted exactly, plus the spec and design paths. Ask it to address every point or explain any disagreement.
4. **Reviewer.** Delegate to the **reviewer** subagent to check the result against the spec and the feedback.
5. **Hand over.** Summarise what changed and the reviewer's verdict, then ask before committing and pushing to the existing branch. Never force push.
