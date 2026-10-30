---
name: code-review
description: Checklist and verdict rules for reviewing a change against its spec and design - correctness, security, tests, design fidelity, maintainability - with concrete, actionable findings. Use when reviewing a diff or pull request.
---

# Reviewing a change

## Gather context
1. Spec and design: what must be true when this is done.
2. `git status` and `git diff <base>...` (or the PR diff): what actually changed. Read new files in full.
3. Run the tests and, where quick, the feature itself.

## Checklist (in priority order)

**Correctness**
- Each acceptance criterion is met; check each one with evidence (test, run, or code path).
- Edge cases: empty, null, large, concurrent, repeated actions, off-by-one, time zones, unicode.
- Errors are handled and surfaced; nothing is silently swallowed.

**Security**
- No secrets, tokens or keys in code, tests, logs or fixtures.
- Untrusted input is validated and escaped: no SQL/command/HTML injection, no path traversal, no unsafe deserialisation.
- Auth and permission checks where needed; no widened access.
- New dependencies are reputable and pinned.

**Tests**
- New behaviour is covered; tests would fail if the code broke.
- No tests deleted, skipped or weakened without a stated reason.
- The suite passes.

**Design fidelity (UI changes)**
- States, copy, tokens and responsive behaviour match the design.
- Accessibility checklist items hold (keyboard, focus, labels, contrast).

**Maintainability**
- Follows the repository's conventions; no unrelated changes or dead code.
- Names are clear; complex parts have a short comment explaining why.
- Docs updated where setup or usage changed.

## Writing findings
- Blocking issue: `file` (and line), what is wrong, why it matters, how to fix it.
- Suggestion: optional polish, clearly marked non-blocking.
- Do not request changes outside the spec; note them as follow-ups instead.

## Verdict
- **approve**: all criteria met, nothing blocking.
- **request_changes**: at least one blocking issue. Be specific enough that the developer can fix it without asking.
