# Tidemark Frontend Design Reference

## Source Context

- UX library: `~/projects/ux`
- Intercept frontend: `~/projects/intercept/frontend`
- Shared exports: `@tidemark-security/ux` exposes auth, ai, actions/buttons, cards, data-display, feedback, forms, layout, navigation, overlays, status, contexts, hooks, tokens, and utilities.
- Intercept local development may alias `@tidemark-security/ux` to `~/projects/ux/src` for app development. GitHub CI installs the GitHub tag from `frontend/package.json` and `frontend/package-lock.json`; always account for that difference when diagnosing typecheck failures.

## UX Package Release Workflow

- Prefer changing shared primitives in `~/projects/ux` when the behavior or API is generally reusable across Tidemark apps.
- Before Intercept consumes a new UX API, verify UX with `npm run typecheck` and `npm run build`.
- Release UX by bumping `package.json` and `package-lock.json`, committing, tagging `vX.Y.Z`, and pushing the commit and tag to `tidemark-security/ux`.
- In Intercept, update `frontend/package.json` to `github:tidemark-security/ux#vX.Y.Z`, then run `npm install` in `frontend` and confirm `frontend/package-lock.json` resolves `node_modules/@tidemark-security/ux` to the new version and tag commit.
- Do not rely only on local `tsconfig` aliases to prove CI will pass. Check the installed package declarations under `frontend/node_modules/@tidemark-security/ux/dist` when the failure involves exported component props or types.
- If local Vitest resolves `../../ux/node_modules/react` and reports invalid hook calls, the test runner is using sibling UX source with a second React instance. Prefer configuring tests to use the installed UX package while keeping local UX source aliases for normal development/build flows.

## Visual Language

- Dark-first operational UI. Main surfaces use `bg-default-background`; page chrome uses `bg-page-background`; root layouts often sit on `bg-p0`.
- Primary brand is neon lime: `brand-primary`, `brand-400`, `success-600` are all close to `rgb(208, 255, 0)`.
- Secondary accents: cyan `accent-1`, magenta/error `accent-2`, purple `accent-3`, orange `warning`, and priority colors `p0` through `p5`.
- Use borders and block shadows rather than soft elevation. Existing shadows are hard offsets: `shadow-sm`, `shadow-md`, `shadow-lg`, `shadow-accent-1-shadow-*`, `shadow-accent-2-shadow-*`, `shadow-error-shadow-*`, `shadow-success-shadow-*`.
- Geometry is compact and sharp: `rounded-md` is normal, bevel classes such as `bevel-tr-3xl` appear on major panels, and large pill-like controls should be avoided unless already present.
- Priority and AI treatments can use masked diagonal stripes. Existing patterns use CSS masks with `repeating-linear-gradient(135deg, transparent ... black ...)` plus a fading mask.

## Typography

- Use token classes from the Tailwind preset:
  - `text-caption font-caption`: 12/16 regular
  - `text-caption-bold font-caption-bold`: 12/16 medium
  - `text-body font-body`: 14/20 regular
  - `text-body-bold font-body-bold`: 14/20 medium
  - `text-heading-3 font-heading-3`: 16/20 semibold, Saira Condensed
  - `text-heading-2 font-heading-2`: 20/24 semibold, Saira Condensed
  - `text-heading-1 font-heading-1`: 30/36 semibold, Saira Condensed
  - `text-monospace-body font-monospace-body`: 14/20 Kode Mono
- Do not use viewport-scaled type or negative letter spacing. The preset uses `letterSpacing: 0em`.
- Reserve `heading-1` for true page titles. Use `heading-3` for panel/card titles and dense tool surfaces.

## Component Organization

Intercept uses a hybrid component structure:

- Generic primitives: `buttons`, `forms`, `feedback`, `data-display`, `overlays`, `cards`, `navigation`, `misc`, `layout`.
- Feature folders: `ai`, `auth`, `entities`, `search`, `timeline`, `triage`.

Place new reusable UI by primary purpose. Place one-feature components in that feature folder. Export reusable components from the folder `index.ts`.

## Preferred Components

- Actions: `Button`, `IconButton`, `LinkButton`, `ToggleGroup`. Variants include brand, neutral, and destructive primary/secondary/tertiary. Sizes are small, medium, and large.
- Forms: `TextField`, `TextArea`, `Select`, `RadioGroup`, `RadioCardGroup`, `Switch`, `Slider`, `DateTimeManager`, `DateRangePicker`, `MarkdownInput`, `TagsManager`, `TagInput`, `AssigneeSelector`.
- Display: `Table`, `Badge`, `Tag`, `Avatar`, `RelativeTime`, `MarkdownContent`, `TreeView`, chart components.
- Status: `State` and `Priority` for entity states and severity. Map API enum strings into these components rather than showing raw enum text.
- Feedback: `Loader`, `Progress`, `SkeletonText`, `SkeletonCircle`, `Toast`, `Alert`.
- Overlays: `Dialog`, `Drawer`, `DropdownMenu`, `Tooltip`, `Accordion`; keep z-index behavior aligned with token variables.
- Cards: `DashboardCard`, `MenuCardBase`, Intercept `BaseCard`, `EntityMetadataCard`, `StatCard`.
- Layout: `DefaultPageLayout`, `AdminPageLayout`, `ThreeColumnLayout`, `ColumnRail`, `RightDock`, app sidebars.
- AI: `AiChat`, `ChatInput`, message components, `ToolApprovalCard`, `SuggestedPrompts`, scanline loading states.

Use `cn()` for conditional classes and `IconWrapper` around lucide icons so icon sizing tracks text.

## Layout Patterns

- Standard pages use `DefaultPageLayout withContainer`. Page content commonly starts with a full-width flex column and `gap-8 py-8`.
- Detail workflows use `ThreeColumnLayout`:
  - Left: AI/chat or contextual rail.
  - Center: primary entity timeline/content.
  - Right: `RightDock` editor/details panel.
  - Mobile shows one column at a time; tablet/desktop/ultrawide adjust visible columns.
- Use `ColumnRail` when the left pane is collapsible/resizable and persist width/collapsed state when matching existing detail pages.
- Use dense tables for queues and worklists. Rows should be clickable when they navigate; include stable identifiers, title, type, state, priority, assignee, and time columns where relevant.
- Use right docks or drawers for edits that should not destroy analyst context. Use dialogs for blocking confirmations or short creation flows.

## Interactions

- Primary action: lime brand button. Secondary actions: bordered brand or neutral. Destructive actions: destructive variants.
- Familiar tool commands should be icon buttons with tooltips. Ambiguous or risky commands should include text labels.
- Use optimistic or inline feedback where existing hooks already do; otherwise show `Loader`, `Skeleton*`, or concise error states.
- Preserve keyboard and screen-reader behavior from Radix-based primitives. Do not replace them with custom div controls.
- For copy interactions, follow `BaseCard`: reserve icon space, swap to copy/check on hover/success, prevent propagation, and reset success state after a short timeout.

## Cyberpunk Details To Reuse

- Condensed headings on compact surfaces.
- Thin neutral borders and lime hover/focus affordances.
- Hard offset shadows for selected, hover, or overlay states.
- Priority stripes for severe or urgent content.
- `ai-scanline-track` and `ai-scanline` classes for AI loading/progress visuals.
- Entity cards with base icon, accent icon/text, stacked metadata lines, optional action buttons, and copyable values.

## Accessibility And Responsiveness

- Keep contrast high in both dark and light theme. If using `useTheme()`, follow existing light-mode overrides: darker brand/error colors in light mode.
- Ensure text wraps or truncates intentionally with `line-clamp`, `truncate`, stable widths, or responsive grids.
- Verify mobile breakpoints for `ThreeColumnLayout` and page containers. Mobile should not show squeezed three-panel layouts.
- Preserve visible focus states using token borders/shadows.
- Avoid hover-only access to required actions; hover can reveal convenience affordances but core actions must remain discoverable.

## Anti-Patterns

- Do not create marketing hero pages for app workflows.
- Do not use generic shadcn-style white cards, rounded 2xl panels, pastel gradients, beige themes, or soft SaaS dashboard visuals.
- Do not introduce raw colors, ad hoc fonts, random border radii, or custom icon sizing outside tokens/utilities.
- Do not hand-roll components that already exist in UX or Intercept.
- Do not hide domain identifiers, status, priority, timestamps, or assignee metadata when building security workflows.
- Do not add instructional in-app copy explaining how the UI was designed. Keep copy operational.
