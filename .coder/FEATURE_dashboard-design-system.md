# Dashboard Design System Refactor

## Scope

- Refactor `src/dashboard` in a single implementation wave.
- Redesign the dashboard visual system while preserving behavior and script wiring.
- Keep the existing warm `amber + stone` palette.
- Use serif display typography for hero/display headings and sans-serif for body, form, table, and control text.

## Goals

- Remove duplicated layout and form patterns across dashboard pages and shells.
- Standardize hero, toolbar, card, stat, breadcrumb, guide-aside, and footer presentation.
- Enforce a consistent page content width and max-width across all dashboard screens.
- Reduce per-page hard-coded widths and one-off spacing/radius/font decisions.

## Non-Goals

- No API contract or endpoint changes.
- No data-flow changes.
- No script rewrites unless required for compatibility, which is currently not expected.
- No changes to graph explorer canvas-specific IDs/styles beyond wrapping shared surrounding chrome.

## Behavior Contracts

- Preserve all existing DOM IDs used by `src/dashboard/src/scripts/*`.
- Preserve existing dashboard `data-*` attributes relied on by scripts.
- Keep existing route structure intact.
- Keep footer and layout compatible with authenticated and unauthenticated screens.

## Design Decisions

- Palette: keep warm `amber + stone`.
- Typography:
  - Display/headings: `Fraunces` with existing serif fallbacks.
  - Body/forms/buttons/tables: `Inter` with system fallbacks.
  - Code/pre: `JetBrains Mono`.
- Layout:
  - Shared page max-width is fixed through one container system.
  - Inner content wrappers should fill the available shared width instead of introducing page-specific `max-w-*` constraints unless intentionally narrow.
  - Sidebar-main shells should use one standard sidebar width.

## Quality Gates

- `astro check`
- `bun run build`

## Success Criteria

- Dashboard pages render with one consistent content width and spacing system.
- Repeated primitives use shared components/classes instead of duplicated inline utility strings.
- Footer is present and consistent across dashboard layouts.
- All existing page scripts continue to function without ID regressions.
