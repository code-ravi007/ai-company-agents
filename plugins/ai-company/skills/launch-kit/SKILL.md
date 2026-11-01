---
name: launch-kit
description: Have the team's Marketing agent write a launch kit (positioning, landing copy, social posts, launch email, SEO) for a feature or product into marketing/. Use when the user wants to announce or market something.
argument-hint: <feature, PR number or product>
---

# Write a launch kit

Subject: $ARGUMENTS

1. Gather what shipped: if it is a PR or issue number and `gh` is available, read its title, description and linked spec; otherwise use the README and the user's description. If it is unclear what to market, ask one question.
2. Pick a slug (2-5 lowercase words joined by hyphens).
3. Delegate to the **marketing** subagent with that context and tell it to write `marketing/<slug>/launch-kit.md`.
4. Show the user the positioning statement, the headline and one social post, with the path to the full kit.
5. Nothing is posted anywhere. Do not commit unless the user asks; then branch and open a PR as in `build-feature`.
