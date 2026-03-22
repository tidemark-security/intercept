# Tailwind / Theming

## Theme architecture (source of truth)

- Theme preference is local only: `system | dark | light`.
- Preference is persisted in localStorage key `intercept.theme-preference`.
- Effective theme is applied to `document.documentElement` as `data-theme="dark" | "light"`.
- Runtime theme context lives in `src/contexts/ThemeContext.tsx`.
- Theme preference utilities live in `src/utils/themePreference.ts`.

## CSS token model

- Global theme tokens are defined in `src/index.css`.
- Use `:root` for dark defaults.
- Use `:root[data-theme="light"]` for explicit light mode values.
- Keep `@media (prefers-color-scheme: light) :root:not([data-theme])` aligned with light defaults for system mode behavior.
- Semantic app colors should come from CSS variables (for example, default font/background, subtext, border).

### Important rule

- Do not hardcode light/dark text colors in component markup when semantic tokens exist.
- Prefer token-based classes first (`text-default-font`, `text-subtext-color`, `bg-default-background`, `border-neutral-border`).

## Per-component overrides (when tokens are not enough)

Use per-component overrides only for elements that intentionally use accent/brand colors and fail contrast in light mode.

### Pattern

1. Read resolved theme from `useTheme()`.
2. Compute `isDarkTheme`.
3. Branch only the risky color classes with `cn(...)`.
4. Preserve dark mode styling unless the task explicitly changes dark mode.

Example pattern:

```tsx
const { resolvedTheme } = useTheme();
const isDarkTheme = resolvedTheme === "dark";

<span
	className={cn(
		"text-body font-body",
		isDarkTheme ? "text-brand-primary" : "text-brand-800"
	)}
/>
```

## Where to apply overrides first

- Entity titles, subtitles, and links in detail/list headers.
- Toggle selected-state text/icons.
- Metadata microtext (timestamps, IDs, secondary labels).
- Badge text on vivid backgrounds (verify contrast for normal text size).

## WCAG checks (minimum)

- Normal text: target >= 4.5:1.
- Large text (or bold large): target >= 3:1.
- Non-text UI boundaries/focus indicators: target >= 3:1 where applicable.

## Agent workflow for theme-related edits

1. Implement token-first change.
2. Add theme-aware override only where needed.
3. Verify both themes on affected views (light + dark).
4. Validate focus visibility and hover states in both themes.
5. Avoid global token changes when a local component override solves the issue.

## Guardrails

- Do not change persistence behavior (must remain local-only).
- Do not remove system-mode live OS sync.
- Do not introduce one-off hex colors for theme logic if an existing token or palette class can be used.
- Do not regress dark mode while fixing light mode contrast.

