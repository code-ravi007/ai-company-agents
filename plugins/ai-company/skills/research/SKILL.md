---
name: research
description: Have the team's Researcher investigate a question, market or feature idea and write a sourced brief to docs/ai-company/research/. Use when the user asks to research something before deciding what to build.
argument-hint: <question or topic>
---

# Research a question

Question: $ARGUMENTS

1. If the question is empty, ask the user what they want to find out and what decision it should inform.
2. Pick a slug (2-5 lowercase words joined by hyphens).
3. Delegate to the **researcher** subagent with the question and tell it to write the brief to `docs/ai-company/research/<slug>.md`.
4. Show the user the recommendation and the three most important findings, with the path to the full brief.
5. Do not commit. If the user wants it in a pull request, follow the same branch and PR steps as the `build-feature` skill and ask first.
