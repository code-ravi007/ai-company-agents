---
name: triage-issue
description: Have the team's Support agent triage a GitHub issue - classify, suggest labels, draft a reply, and say whether the build team should take it. Use when the user asks to triage or answer issues.
argument-hint: <issue number or URL>
---

# Triage an issue

Issue: $ARGUMENTS

1. Read the issue title, body and comments with `gh issue view <number> --comments` (ask the user to paste it if `gh` is not available).
2. Delegate to the **support** subagent with the issue text.
3. Show the user the classification, the suggested labels, the draft reply, and whether it is ready for the build team.
4. Only if the user says yes: apply the labels with `gh issue edit` and post the reply with `gh issue comment`. Never post without asking.
