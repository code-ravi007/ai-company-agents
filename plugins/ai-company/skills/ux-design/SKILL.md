---
name: ux-design
description: How to write a precise, text-based UX/UI design doc - user flows, screen and component specs, all states, exact copy, design tokens, responsive and accessibility notes - that a developer can implement without guessing. Use for any user-facing change.
---

# Writing a design doc

You are designing in words, so precision replaces pictures. Every value a developer would otherwise guess (spacing, colour, copy, focus order, what happens on error) must be written down.

## Start from what exists

- Find the design system: token or theme files, CSS variables, Tailwind config, component library, existing screens.
- Reuse existing components and tokens by name. A new component needs a reason.
- Match existing tone of voice in copy.

## Template

```markdown
# Design: <feature>

## User flow
1. <entry point> → <step> → ... → <done state>
   - Unhappy paths: <validation error, network error, empty data, no permission>

## Screens and components
### <Screen or component name>
- Layout, top to bottom: <element> (<existing component or new>), ...
- New component `<Name>` props: `<prop>: <type>` - <meaning>
- Behaviour: <what happens on click, hover, submit, keyboard>

## States
| View | Empty | Loading | Error | Success | Disabled | Long content |
|---|---|---|---|---|---|---|

## Copy
| Key / location | Text |
|---|---|

## Visual tokens
- Colours, spacing, type, radii, shadows: reference existing tokens; give exact values only for new ones.

## Responsive behaviour
- <breakpoint>: <what changes>

## Accessibility
- Keyboard order, focus on open/close, labels, live regions, contrast, reduced motion.

## Developer notes
- <anything easy to get wrong>

## Open design questions
- <only if needed>
```

## Principles

- **Every state is designed.** Empty, loading, error and success are not edge cases; they are most of what users see.
- **Hierarchy first.** One primary action per view. Secondary actions are visually quieter.
- **Copy is design.** Buttons say what they do ("Save changes", not "OK"). Errors say what happened and what to do next.
- **Touch and pointer.** Targets at least 44×44 px. Do not rely on hover alone.
- **Layout.** Use the existing spacing scale. Align to a grid. Nothing scrolls horizontally at 320 px.
- **Motion.** Short (150-250 ms), purposeful, and disabled under `prefers-reduced-motion`.
- **Non-visual work.** For a CLI: commands, flags, output format, exit codes, error messages, examples. For an API: endpoints, request and response shapes, status codes, error bodies, examples.
