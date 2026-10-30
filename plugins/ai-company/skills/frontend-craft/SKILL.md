---
name: frontend-craft
description: How to implement polished, robust front-end UI from a design doc - component structure, state handling, styling with existing tokens, responsiveness, performance and visual polish. Use when building or changing user interfaces in any framework.
---

# Front-end craft

## Fit the project
- Use the project's framework, component library, styling approach (CSS modules, Tailwind, styled-components, plain CSS) and token names. Do not introduce a new UI library for one feature.
- Put files where similar files live; name them the way neighbours are named.

## Components
- Small, focused components with explicit props. Keep data fetching and presentation separate where the codebase does.
- Model every state from the design: empty, loading, error, success, disabled, long content. A missing state is a bug.
- Derive state instead of duplicating it. Keep form state close to the form.
- Handle async properly: cancel or ignore stale responses, disable double submits, show progress.

## Styling
- Use design tokens and the spacing scale; no magic numbers unless the design gives one.
- Layout with flexbox or grid; avoid fixed heights for text containers.
- Mobile first. Check 320 px, 768 px, 1280 px. Nothing scrolls horizontally.
- Long text wraps or truncates deliberately (`overflow-wrap: anywhere`, `text-overflow: ellipsis` with a title).
- Support dark mode if the project does.

## Polish
- Consistent alignment and spacing; one primary action per view.
- Hover, active, focus-visible and disabled styles for every interactive element.
- Transitions 150-250 ms, disabled under `prefers-reduced-motion`.
- Exact copy from the design, including punctuation and capitalisation.

## Performance
- No layout shift: reserve space for images (`width`/`height`) and async content (skeletons).
- Lazy-load heavy, below-the-fold content. Avoid re-rendering large lists unnecessarily; virtualise lists over a few hundred rows.
- Do not ship large dependencies for small tasks.

## Safety
- Never inject untrusted HTML (`innerHTML`, `dangerouslySetInnerHTML`) without sanitising.
- No secrets in front-end code; anything shipped to the browser is public.
