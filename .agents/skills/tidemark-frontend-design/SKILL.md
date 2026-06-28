---
name: tidemark-frontend-design
description: Build frontend pages and components that match Tidemark Security apps, including Tidemark Intercept, using the internal Radix-based UX package, Tailwind tokens, cyberpunk visual language, and established React component organization. Use when creating, changing, reviewing, or redesigning Tidemark Security React UI, Intercept pages, dashboards, entity details, AI chat, timelines, forms, tables, cards, navigation, or design-system components.
---

# Tidemark Frontend Design

## Workflow

1. Inspect nearby app code before designing. Prefer the consuming app's existing components and folder conventions over inventing local variants.
2. Import components from the Tidemark UX package as-is wherever possible: buttons, forms, feedback, data-display, overlays, cards, navigation, layout, status, and AI components. Avoid wrapping UX components unless the wrapper adds Intercept-specific features or behavior that does not belong in UX.
3. When a required UX component API exists in the local `~/projects/ux` source but not in Intercept CI, release UX and update Intercept's dependency tag instead of vendoring or locally wrapping the missing API. Intercept CI installs the tagged GitHub dependency, while local typecheck may resolve the sibling UX source via tsconfig aliases.
4. Build dense operational screens, not marketing pages. Tidemark apps are security analyst tools: optimize for scanning, triage, comparison, assignment, and repeated action.
5. Use the cyberpunk aesthetic through tokens, typography, sharp geometry, subtle stripes, and neon accents. Keep the interface usable, high-contrast, and information-led.
6. Verify responsive behavior across mobile, tablet, desktop, and ultrawide when touching page layouts or multi-column surfaces.

## Load References

Read [references/design-system.md](references/design-system.md) when implementing or reviewing UI. It contains the concrete token names, component choices, layout patterns, Intercept-specific examples, and anti-patterns extracted from `~/projects/ux` and `~/projects/intercept/frontend`.

## Core Rules

- Use Saira typography classes (`text-body`, `text-heading-3`, etc.) and token colors (`bg-default-background`, `text-default-font`, `border-neutral-border`, `bg-brand-primary`) instead of raw CSS values.
- Prefer `DefaultPageLayout`, `ThreeColumnLayout`, `ColumnRail`, and `RightDock` for app shells and entity detail pages.
- Use UX components as-is where possible. Do not create local wrappers or mirrored primitives solely to rename imports, restyle defaults, or smooth over API differences; wrap only when adding Intercept-local features, composition, or behavior.
- Treat the UX package as a real shared dependency. If Intercept consumes new UX props, exports, styles, or behavior, ensure `~/projects/ux` has been built, versioned, committed, tagged, and pushed, then update `frontend/package.json` and `frontend/package-lock.json` to the new `github:tidemark-security/ux#vX.Y.Z` tag.
- Prefer existing primitives such as `Button`, `IconButton`, `TextField`, `Select`, `DateTimeManager`, `Table`, `Badge`, `State`, `Priority`, `Dialog`, `Drawer`, `Tooltip`, `DropdownMenu`, `DashboardCard`, and `BaseCard`.
- Use `lucide-react` icons wrapped with `IconWrapper`; use icon-only buttons where the command is familiar and label text where the action needs clarity.
- Keep cards purposeful: repeated items, dashboard modules, modals, and framed operational tools. Do not nest cards inside cards.
- Preserve dark-first behavior and light-mode contrast through token classes and `useTheme()` checks where components already follow that pattern.
- Add or update barrel exports when creating reusable components in component folders.

## Troubleshooting

- For GitHub frontend CI failures, inspect the exact job log and distinguish image builds, typecheck, and Vitest failures. The common drift pattern is: local Intercept resolves `@tidemark-security/ux` to sibling source, but CI installs the released UX tag.
- If `npx tsc --noEmit` fails in CI with missing UX props that exist locally, check `frontend/package-lock.json` and `frontend/node_modules/@tidemark-security/ux/dist/*.d.ts` against the published tag. Release UX rather than adding type casts or local compatibility shims.
- If local Vitest shows `Invalid hook call` or stack traces under `../../ux/node_modules/react`, suspect duplicate React from the sibling UX source alias. Tests should generally exercise the installed UX package unless the task is explicitly testing local UX source integration.
- After UX dependency changes in Intercept, verify at minimum `cd frontend && npx tsc --noEmit` and `cd frontend && npm test`. When hook behavior changes, run the local Fast CI script path too.

## Design Direction

Make Tidemark screens feel like a serious security console: black and charcoal surfaces, lime primary actions, cyan/magenta/orange severity accents, condensed headings, compact tables, bordered panels, bevels or small radii, and occasional masked diagonal stripe effects for priority or AI states. Avoid soft SaaS styling, pastel palettes, oversized hero sections, decorative gradients, and explanatory in-app copy.
