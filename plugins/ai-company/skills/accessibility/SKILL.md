---
name: accessibility
description: Practical accessibility (WCAG 2.2 AA) checklist for designing, building and reviewing user interfaces - semantics, keyboard, focus, labels, contrast, motion, screen readers. Use whenever a change touches UI.
---

# Accessibility checklist (WCAG 2.2 AA)

Use native elements first; ARIA only fills gaps.

## Structure and semantics
- One `<h1>` per page; headings in order without skipping levels.
- Landmarks: `header`, `nav`, `main`, `footer`.
- Buttons are `<button>`, links are `<a href>`. Never a clickable `<div>`.
- Lists are lists; tables with headers are `<table>` with `<th scope>`.
- `lang` on `<html>`; a meaningful `<title>`.

## Keyboard and focus
- Everything works with Tab, Shift+Tab, Enter, Space, Escape and arrow keys where expected.
- Focus order follows visual order. No positive `tabindex`.
- Focus is always visible (`:focus-visible` outline, contrast at least 3:1).
- Dialogs: move focus in on open, trap it while open, return it on close, close on Escape.
- Do not move focus unexpectedly on input.

## Labels and names
- Every input has a visible `<label for>` (placeholder is not a label).
- Icon-only buttons have an accessible name (`aria-label` or visually hidden text).
- Images: meaningful `alt`, or `alt=""` if decorative.
- Errors are tied to fields with `aria-describedby` and announced.

## Dynamic content
- Status updates use `aria-live="polite"` (errors may use `assertive`).
- Loading states are announced, and do not trap focus.

## Visual
- Text contrast at least 4.5:1 (3:1 for 18 px bold or 24 px and up); UI components and focus rings at least 3:1.
- Never use colour alone to convey meaning.
- Works at 200% zoom and 320 px width without loss of content.
- Targets at least 24×24 px (aim for 44×44).
- Respect `prefers-reduced-motion`; nothing flashes more than 3 times per second.

## How to check
- Tab through the whole flow without a mouse.
- Run an automated checker if the project has one (axe, Lighthouse, eslint-plugin-jsx-a11y, pa11y).
- Read the markup for the items above; automated tools catch only about a third of issues.
