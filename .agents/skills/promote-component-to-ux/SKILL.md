---
name: promote-component-to-ux
description: Promote an Intercept-local React component into the sibling Tidemark UX package and migrate Intercept to consume the UX export. Use when moving, deduplicating, or replacing local Intercept UI components with components from @tidemark-security/ux.
---

# Promote Component To UX

## Repository Discovery

This workflow assumes the current working directory is inside the Intercept repository, and that the UX repository is either checked out next to Intercept or provided via `UX_REPO_DIR`.

Resolve paths before acting:

```bash
INTERCEPT_REPO="$(git rev-parse --show-toplevel)"
UX_REPO="${UX_REPO_DIR:-"$(dirname "$INTERCEPT_REPO")/ux"}"
```

If `"$UX_REPO/package.json"` does not exist, ask for the UX checkout location instead of assuming a user-specific home directory.

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

3. If UX needs the component added or updated, make that change in `UX_REPO`.
   - Add the component to the appropriate `src/components/<area>/` folder.
   - Export it from the component area barrel.
   - Confirm `src/index.ts` already exports the area, or add the export if needed.
   - Add or update Storybook stories for the component. Every promoted component must be integrated into Storybook with one or more stories showing how to use it.

4. Create or update the Storybook story.
   - Place stories under `UX_REPO/stories/<area>/ComponentName.stories.tsx`.
   - Import the component and any exported types from `../../src`.
   - Include `Meta` and `StoryObj` from `@storybook/react-vite`.
   - Add at least one usage-focused story that renders the component in a realistic state.
   - Add additional stories for important variants, sizes, states, controlled behavior, empty/loading/error states, or composition examples.
   - Prefer interactive stories with local `useState` when the component has controlled props.
   - Keep story examples close to how Intercept will consume the component so future migrations have a working reference.
   - Ensure the component appears in the appropriate Storybook category, such as `Actions`, `Cards`, `Data Display`, `Forms`, `Layout`, `Navigation`, `Overlays`, or `Status`.

5. Verify and rebuild UX before migrating Intercept.
   - From `UX_REPO`, run `conda run -n intercept npm run typecheck`.
   - From `UX_REPO`, run `conda run -n intercept npm run build`.
   - If the sandbox blocks writes under UX, rerun with escalation and explain that the sibling repo build writes outside the Intercept writable root.

6. Refresh Intercept's installed UX package for local smoke verification when useful.
   - From `INTERCEPT_REPO/frontend`, run `conda run -n intercept npm install --no-save "$UX_REPO"`.
   - Check `git status` after install. Do not keep accidental `package.json` or `package-lock.json` changes unless the user asked to update the dependency pin.
   - Treat this as local smoke verification only. It does not prove GitHub CI will pass because Intercept CI installs the tagged GitHub dependency, not the sibling checkout.

7. Swap Intercept to consume the UX component.
   - Import from `@tidemark-security/ux`.
   - Pass styling through supported props such as `className`.
   - Delete the local duplicate component only after the UX build exposes the replacement.
   - Remove any now-unused barrel export.

8. Release UX when Intercept will depend on the new or changed API.
   - Bump the UX package version in `UX_REPO` using the package's established versioning command or `npm version <part> --no-git-tag-version` if no stricter project instruction exists.
   - Commit the UX version metadata and tag the commit as `vX.Y.Z`.
   - Push the UX commit and tag to `tidemark-security/ux`.
   - In Intercept, update `frontend/package.json` to `github:tidemark-security/ux#vX.Y.Z`.
   - From `INTERCEPT_REPO/frontend`, run `npm install --no-audit --no-fund` or an explicit `npm install github:tidemark-security/ux#vX.Y.Z --save --no-audit --no-fund` if npm leaves the lockfile on the old commit.
   - Confirm `frontend/package-lock.json` resolves `node_modules/@tidemark-security/ux` to the new version and tag commit.

9. Verify Intercept against the dependency shape CI will use.
   - Run `npx tsc --noEmit` from `INTERCEPT_REPO/frontend`.
   - Run `npm test` from `INTERCEPT_REPO/frontend`.
   - If the local test runner resolves `../../ux/node_modules/react` and reports invalid hook calls, configure Vitest to use the installed UX package rather than the sibling UX source for tests.
   - Run `conda run -n intercept npm run build` from `INTERCEPT_REPO/frontend` when the migration affects bundling, assets, or package exports.
   - Search for old imports/usages with `rg`.
   - Report any persistent Vite chunk warnings separately from build failures.

## Guardrails

- Never manually edit version strings. Use the repository's version-management instructions when a release bump is requested.
- Do not promote a component without Storybook coverage in UX.
- Do not revert unrelated user changes. If a file already has user edits, make the narrowest compatible change.
- Do not leave Intercept depending on a component that exists only in UX source; the built package must expose it.
- Do not rely on Intercept's local `tsconfig`/Vite alias to prove CI compatibility. Check the released package declarations under `frontend/node_modules/@tidemark-security/ux/dist` after updating the dependency tag.
- Do not leave `frontend/package-lock.json` pointing at an old UX commit after changing `frontend/package.json`; npm can appear "up to date" while `node_modules/@tidemark-security/ux` still contains the previous package.
- Keep API compatibility clear: if the UX component name or props differ from the local copy, update call sites deliberately and mention the differences.
