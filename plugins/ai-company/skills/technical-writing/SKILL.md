---
name: technical-writing
description: How to write and update user and developer documentation - README sections, how-to guides, configuration reference and changelog entries - clearly and briefly, matching the project's existing docs. Use when documenting a change or a project.
---

# Technical writing

## Principles
- Start with what the reader wants to do. Lead with the command or the steps; explain after.
- One idea per sentence. Short paragraphs. Use the words the UI and code use.
- Every code block is copy-pasteable and correct for this project.
- Match the existing docs' headings, tone and formatting. Do not restructure what you were not asked to change.

## README
Keep this order when creating one: what it is (one or two sentences), quick start, usage, configuration, development, license. When updating, change only the sections the change affects.

## How-to guide
Title as a task ("Export your data"). Prerequisites, numbered steps, the expected result, troubleshooting for the one or two likely failures.

## Changelog
Use Keep a Changelog. Add entries under `## [Unreleased]`, grouped as Added, Changed, Fixed, Removed, Security. One line per change, written for users:

```markdown
## [Unreleased]
### Added
- Dark mode toggle in Settings (#42).
```

## Checklist
- Steps tested against the code (commands, flags, file names and defaults exist).
- No secrets, internal URLs or personal data.
- Links work and are relative inside the repository.
