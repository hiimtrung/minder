# Feature: Dashboard Design System

Date: 2026-04-17
Status: confirmed → executing (1 wave)

## Goal

Refactor `src/dashboard` to introduce a coherent design system. Eliminate
duplicated styles across shells, provide reusable Astro primitives, and
stabilize typography/spacing/layout for maintainability.

## Success Criteria

- [ ] All `src/dashboard/src/components/*Shell.astro` share the same
      hero/toolbar/section-header/footer primitives instead of copy-pasted
      markup.
- [ ] Sidebar grid widths are unified (380px).
- [ ] Typography scale is unified: Fraunces (display) + Inter (body) +
      JetBrains Mono (code); `h1` hero size is 36px (`text-4xl`) everywhere.
- [ ] Dashboard has a consistent footer across all pages (version + API health + links).
- [ ] Design tokens live as CSS variables in `global.css` (colors, radius, spacing, type, shadows).
- [ ] All existing DOM IDs and data attributes remain unchanged; all page scripts
      continue to run without edits.
- [ ] `bun run build` (or `astro build`) succeeds; `astro check` reports no
      new type errors.

## Scope

### In Scope (1 wave)

- Global stylesheet: design tokens, Google Fonts import, refined utilities,
  compat aliases (`shell-card`, `action-pill`, etc.).
- `DashboardLayout.astro`: fonts in `<head>`, unified max-width, footer block.
- New primitives under `components/ui/`: `PageHero`, `SectionHeader`,
  `DetailHeader`, `Toolbar`, `Breadcrumb`, `Footer`, `StatCard`, `Field`,
  `Input`, `Textarea`, `Select`, `Button`, `ResultCallout`, `GuideAside`,
  `FormStatus`.
- Refactor shells to consume primitives: ClientRegistry, ClientDetail,
  WorkflowRegistry, WorkflowDetail, SkillRegistry, MemoryRegistry,
  PromptRegistry, RepositoryRegistry, Observability, UserManagement,
  plus the hero of RepositoryGraphExplorer.
- Refactor top-level pages: `pages/index.astro`, `pages/login.astro`,
  `pages/setup.astro` (hero + form use primitives).

### Out of Scope

- Palette change (keep warm amber/stone tones).
- Backend / API changes.
- `scripts/*-page.ts` behavior changes.
- Graph canvas internals inside `RepositoryGraphExplorerShell.astro`
  (command bar, canvas controls, tabs, right sidebar) — only the hero area
  is touched.
- New pages, new routes, new endpoints.
- Any test infrastructure beyond what already exists.

## Technical Constraints

- Framework: Astro 6 + Tailwind v4 (via `@tailwindcss/vite`).
- Package manager: `bun` (do not introduce npm/yarn).
- Preserve every DOM ID in existing shells; scripts reference them.
- Preserve utility class names used by JS-injected HTML:
  `shell-card`, `eyebrow`, `action-pill`, `primary-pill`, `session-badge`,
  `tab-btn`, `tab-btn-active`, `snippet-pre`, `graph-ctrl-btn`, `nav-link`.
- Google Fonts loaded via `<link rel="preconnect">` + `<link rel="stylesheet">`
  in the layout head.
- No new runtime JS dependencies; Tailwind utilities + minimal CSS only.

## Design Decisions

### Palette (kept)

Warm amber + stone tones (`amber-700/800` as primary, `stone-*` neutrals).
Background retains the subtle warm radial gradient.

### Typography

- `--font-display: "Fraunces", "Iowan Old Style", Georgia, serif` — hero h1/h2.
- `--font-sans: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif` — body, forms, tables, buttons.
- `--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace` — code, snippets.
- Scale: `display-xl=2.25rem`, `display-lg=1.875rem`, `heading-lg=1.25rem`, `heading-md=1rem`, `body-md=0.875rem`, `eyebrow=0.6875rem/600/uppercase/tracking-[0.2em]`.

### Spacing / radius

- Radii tokens: `--r-sm=6px --r-md=10px --r-lg=14px --r-xl=20px --r-2xl=26px`.
- Sidebar column width: **380px** across all shells.
- Page content max width: **1440px**.
- Section gap: 24px (`gap-6`).

### Footer (new)

```
© 2026 Minder · v{version} · API {health-dot + label} · Docs · GitHub
```
- Single row, `text-xs text-stone-500`, `border-t border-stone-200 pt-4`.
- API health dot only populated when `sessionControls` is true and `session-header.ts` updates it.

## Edge Cases

- Login and setup pages have no nav and no session controls — footer still renders, API health dot hidden.
- Dashboard home page has its own session bootstrap; primitives must not render the Home hero twice.
- RepositoryGraphExplorerShell keeps its graph-specific DOM intact; only the top hero row is primitives-driven.

## Behavior Contract

- Every existing `id="…"` in `.astro` files is preserved verbatim.
- Every `data-*` attribute used by scripts is preserved.
- JS-injected class names remain valid (retain `.shell-card`, `.action-pill`, etc.).
- No script under `src/dashboard/src/scripts/` is modified.
