---
name: product-spec
description: How to write a product spec that a designer and developer can build from without asking questions - scope, user stories, testable acceptance criteria, ordered tasks. Use when turning an idea, issue or feature request into a spec.
---

# Writing a product spec

A good spec is short, concrete, and checkable. Someone who was not in the conversation should be able to build the right thing from it, and a reviewer should be able to say "met" or "not met" for every criterion.

## Before writing

- Restate the request in one sentence. If you cannot, the request is ambiguous; pick the most likely reading and record it as an assumption.
- Look at the repository: stack, folder layout, existing features this touches, how tests run. The spec must fit what exists.
- Find the smallest change that fully delivers the request. Ask "what would the person be disappointed to not get?" and stop there.

## Template

```markdown
# Spec: <short title, written like a PR title>

<2-4 sentences: what changes for the user, and why.>

## User stories
- As a <who>, I can <do what> so that <why>.

## Acceptance criteria
- [ ] <observable behaviour, with exact values, text and states>

## Tasks
1. **<task>** (<design|frontend|backend|infra|docs|tests>): <what to do, which files or areas>

## Out of scope
- <things deliberately not done now>

## Assumptions
- <defaults you picked instead of asking>

## Open questions
- <only questions that block building; empty is normal>
```

## Acceptance criteria that work

| Weak | Strong |
|---|---|
| The form validates input | Submitting with an empty email shows "Email is required" under the field and does not submit |
| It is fast | The list renders 1,000 rows without the page freezing (no task over 200 ms in the performance panel) |
| Works on mobile | At 360 px wide nothing scrolls horizontally and every button is at least 44 px tall |
| Handles errors | If the API returns 500, a banner says "Something went wrong. Try again." with a Retry button |

Each criterion: one behaviour, observable from outside, with exact copy and numbers where they matter. Cover the unhappy paths (empty, error, loading, permission denied, very long input) for anything user-facing.

## Tasks

- Order them so each builds on the last and the app works after each one.
- Name the area and the likely files. Include a tests task (or tests inside each task) and a docs task when setup or usage changes.
- 3 to 8 tasks is typical. More than 10 usually means the scope is too big: split the feature.

## When to block

Block (list open questions and stop) only when a wrong guess would waste the whole build, such as which of two incompatible products is wanted. For everything else, choose a sensible default and write it under Assumptions. The owner can correct it in review.
