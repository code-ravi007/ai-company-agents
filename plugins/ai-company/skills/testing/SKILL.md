---
name: testing
description: How to decide what to test and write tests that catch real regressions, in the project's existing framework and style - unit, integration and UI tests, edge cases, and how to run and report them. Use when writing tests or verifying a change.
---

# Testing a change

## Use what the project uses
- Find the framework (Jest, Vitest, pytest, Go test, JUnit, Playwright, Cypress ...) and the command (`npm test`, `pytest -q`, `make test`, CI config).
- Put tests next to similar tests and copy their structure, naming and helpers.
- If there are no tests at all, add the most mainstream minimal setup for the stack and one script to run it.

## What to test
- Every acceptance criterion gets at least one test that would fail if the criterion broke.
- Edge cases: empty, zero, one, many, maximum length, invalid input, unicode, duplicate submits.
- Error paths: network failure, server error, permission denied, timeouts.
- UI: test behaviour the user sees (text, roles, labels), not implementation details. Prefer queries by role and label.
- Bug fixes: a test that reproduces the bug first.

## Good tests
- Deterministic: no real network, no real time, no order dependence. Mock at the boundary.
- One reason to fail each; a clear name that says the behaviour ("shows an error when the email is empty").
- Fast. Slow end-to-end tests only for the critical flows.

## Running and reporting
- Run the whole suite, not only new tests, plus linters and type checks the project has.
- Report the exact command and the result. If you could not run something (no browser, missing service), say what and why.
- Never delete, skip, or loosen an existing test to make the suite pass. If an existing test is wrong, explain why in your report.
