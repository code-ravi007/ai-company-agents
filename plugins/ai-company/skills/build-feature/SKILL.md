---
name: build-feature
description: Run the whole AI product team on an idea in the current project - Manager writes the spec, Designer the design, Developer implements, Reviewer checks, QA tests it in a browser, Tech writer updates the docs - then offer to commit and open a pull request. Use when the user asks the team to build, add or create a feature.
argument-hint: <idea or issue URL/number>
---

# Build a feature with the team

Request: $ARGUMENTS

You coordinate specialist subagents from this plugin: `manager`, `designer`, `developer`, `reviewer`, `qa` and `tech-writer`. You do not write the spec, design or code yourself; you hand work between them, keep the human informed, and own git.

## 0. Prepare

- If the request is a GitHub issue number or URL and `gh` is available, read the issue title, body and comments.
- If the request is empty or unclear, ask the user one short question before starting.
- Note the current branch and whether the working tree is clean (`git status`). If there are uncommitted changes, ask the user before continuing so their work is not mixed with the team's.
- Pick a slug (2-5 lowercase words joined by hyphens). Docs go in `docs/ai-company/<slug>/`.

## 1. Spec (manager)

Delegate to the **manager** subagent with the full request, and tell it to write the spec to `docs/ai-company/<slug>/spec.md`.
- If it reports blocking questions, show them to the user and stop until they answer.
- Show the user a 3-5 line summary of the spec (title, criteria count, whether design is needed).

## 2. Branch

Create a branch `ai/<slug>` from the current branch with `git switch -c ai/<slug>` (if it already exists, switch to it). Never work on `main` or `master` directly.

## 3. Design (designer, only if needed)

If the manager said design is needed, delegate to the **designer** subagent with the spec path and tell it to write `docs/ai-company/<slug>/design.md`. Skip this step for internal changes.

## 4. Build and review loop (developer, reviewer)

Repeat at most 3 rounds:
1. Delegate to the **developer** with the spec path, the design path (if any), and, from round 2, the reviewer's blocking issues verbatim.
2. Delegate to the **reviewer** with the spec and design paths and the base branch name, and ask for a verdict.
3. If the verdict is `approve`, stop the loop. Otherwise pass the blocking issues back to the developer.

If the reviewer still requests changes after 3 rounds, stop and tell the user what is unresolved.

## 5. QA (qa, only for user-facing changes)

If there is a design (the change is user-facing), delegate to the **qa** subagent with the spec and design paths and tell it to write `docs/ai-company/<slug>/qa/report.md` with screenshots in the same folder. If the verdict is `fail`, give its bugs to the **developer**, then run the reviewer and QA again (at most 2 QA rounds).

## 6. Docs (tech-writer)

Delegate to the **tech-writer** subagent with the spec path and the base branch, and ask it to update the README, docs and `CHANGELOG.md` for this change.

## 7. Hand over

Tell the user, briefly:
- what was built and the files changed,
- the test command and result,
- the reviewer's verdict and any suggestions,
- the QA verdict and the screenshots folder (if QA ran), and the docs that changed,
- anything that needs a manual check (for example, a visual check in a browser).

Then **ask** whether to commit and open a pull request. Only after the user says yes:
- `git add -A` and commit with a message in the repository's style (title from the spec, body summarising the change).
- Push the branch and open a pull request with `gh pr create`, using the spec summary, the acceptance criteria with the reviewer's evidence, and the test result as the body.

## Rules

- Never delete files, force push, rewrite history, or merge. The human merges.
- Never print or store secrets.
- Keep the user updated between stages with one or two lines, not full documents.
