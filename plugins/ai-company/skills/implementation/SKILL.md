---
name: implementation
description: Engineering practices for implementing a spec in an existing codebase - reading conventions first, small focused diffs, configuration via environment, error handling, documentation, and safe working rules. Use when writing or changing code.
---

# Implementing a change

## Before you code
- Read the spec and design end to end. List the acceptance criteria; they are your checklist.
- Read the code you will touch and its neighbours. Note conventions: formatting, naming, error handling, logging, folder layout, test style, commit of generated files.
- Find how the project builds, runs and tests (README, package.json scripts, Makefile, pyproject, CI config).

## While coding
- Smallest diff that meets the spec. No drive-by refactors, renames or reformatting of untouched code.
- Match the existing style exactly, even where you would choose differently.
- Validate inputs at boundaries; handle errors explicitly with useful messages. Do not swallow exceptions.
- Configuration comes from environment variables or the project's config system. Document new variables in the README and any `.env.example` (never a real `.env`).
- Keep functions small and names descriptive. Comment why, not what, at the density the file already uses.
- New dependencies only when clearly worth it; prefer what the project already uses. Pin versions the way the project does.

## Finishing
- Run the full test suite, linter and type checker that exist. Fix what your change broke.
- Walk through every acceptance criterion and confirm each one, by running the code where possible.
- Update docs for anything that changed how to set up or use the project.
- Report honestly: what changed, files touched, test command, pass or fail, known gaps.

## Safety rules
- Never delete files or directories, and never rewrite git history.
- Never commit, push, or open pull requests yourself; leave that to the owner or orchestrator.
- Never read or print secrets (`.env`, credential files, tokens in environment variables).
- Stay inside the repository. Temporary files go in the system temp directory.
