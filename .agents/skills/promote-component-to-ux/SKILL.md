---
name: promote-component-to-ux
description: Promote an Intercept-local React component into the sibling Tidemark UX package and migrate Intercept to consume the UX export. Use when moving, deduplicating, or replacing local Intercept UI components with components from @tidemark-security/ux.
---

# Promote Component To UX

## Assumption

This workflow assumes the Intercept and UX repositories are checked out side by side on disk:

- Intercept: `/home/tidemark/projects/intercept`
- UX: `/home/tidemark/projects/ux`

Run repository commands through the `intercept` Conda environment unless a project-specific instruction says otherwise.

## Quick Workflow

1. Inspect the Intercept local component and all usages.
   - Use `rg "ComponentName" frontend/src`.
   - Read the local component, nearby barrel exports, and the consuming page/component.
   - Preserve unrelated user changes in touched files.

2. Inspect the UX package implementation.
   - Check `src/components/<area>/ComponentName.tsx`.
   - Check the component folder barrel export and `src/index.ts`.
   - Check stories for intended API and visual usage.
   - Prefer matching the UX API rather than adding an Intercept adapter.

3. If UX needs the component added or updated, make that change in `/home/tidemark/projects/ux`.
   - Add the component to the appropriate `src/components/<area>/` folder.
   - Export it from the component area barrel.
   - Confirm `src/index.ts` already exports the area, or add the export if needed.
   - Add or update Storybook stories for the component. Every promoted component must be integrated into Storybook with one or more stories showing how to use it.

4. Create or update the Storybook story.
   - Place stories under `/home/tidemark/projects/ux/stories/<area>/ComponentName.stories.tsx`.
   - Import the component and any exported types from `../../src`.
   - Include `Meta` and `StoryObj` from `@storybook/react-vite`.
   - Add at least one usage-focused story that renders the component in a realistic state.
   - Add additional stories for important variants, sizes, states, controlled behavior, empty/loading/error states, or composition examples.
   - Prefer interactive stories with local `useState` when the component has controlled props.
   - Keep story examples close to how Intercept will consume the component so future migrations have a working reference.
   - Ensure the component appears in the appropriate Storybook category, such as `Actions`, `Cards`, `Data Display`, `Forms`, `Layout`, `Navigation`, `Overlays`, or `Status`.

5. Rebuild UX before migrating Intercept.
   - From `/home/tidemark/projects/ux`, run `conda run -n intercept npm run build`.
   - If the sandbox blocks writes under UX, rerun with escalation and explain that the sibling repo build writes outside the Intercept writable root.

6. Refresh Intercept's installed UX package for local verification.
   - From `/home/tidemark/projects/intercept/frontend`, run `conda run -n intercept npm install --no-save /home/tidemark/projects/ux`.
   - Check `git status` after install. Do not keep accidental `package.json` or `package-lock.json` changes unless the user asked to update the dependency pin.

7. Swap Intercept to consume the UX component.
   - Import from `@tidemark-security/ux`.
   - Pass styling through supported props such as `className`.
   - Delete the local duplicate component only after the UX build exposes the replacement.
   - Remove any now-unused barrel export.

8. Verify.
   - Run `conda run -n intercept npm run build` from `/home/tidemark/projects/intercept/frontend`.
   - Search for old imports/usages with `rg`.
   - Report any persistent Vite chunk warnings separately from build failures.

## Guardrails

- Never manually edit version strings. Use the repository's version-management instructions when a release bump is requested.
- Do not promote a component without Storybook coverage in UX.
- Do not revert unrelated user changes. If a file already has user edits, make the narrowest compatible change.
- Do not leave Intercept depending on a component that exists only in UX source; the built package must expose it.
- Keep API compatibility clear: if the UX component name or props differ from the local copy, update call sites deliberately and mention the differences.
