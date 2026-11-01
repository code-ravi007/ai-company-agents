---
name: write-post
description: Have the team's Content writer research and write a blog post, tutorial or article on a topic into content/. Use when the user asks for a blog post, article or other written content.
argument-hint: <topic, audience, length>
---

# Write a post

Brief: $ARGUMENTS

1. If the topic is missing, ask for it. Default the audience to the product's users and the length to about 1,200 words.
2. Pick a slug (2-6 lowercase words joined by hyphens).
3. Delegate to the **content-writer** subagent with the brief and tell it to write `content/<slug>.md`.
4. Show the user the title, the one-sentence summary and the word count, with the path.
5. Nothing is published. Do not commit unless the user asks; then branch and open a PR as in `build-feature`.
