# Agent Instructions

## Version Management

**All version bumps MUST use `bump-my-version`.** Never edit version strings manually.

```bash
conda activate intercept
bump-my-version bump patch   # 0.0.8 → 0.0.9
bump-my-version bump minor   # 0.0.8 → 0.1.0
bump-my-version bump major   # 0.0.8 → 1.0.0
```

### What it does

A single `bump-my-version bump <part>` command:

1. Updates version in all managed files (see `.bumpversion.toml`):
   - `VERSION`
   - `frontend/package.json`
   - `frontend/package-lock.json`
   - `docs/quickstart/docker-compose.yml` (image TAG defaults)
2. Creates a git commit (`release: v{new_version}`)
3. Creates a git tag (`v{new_version}`)

### When to bump

- **After** all code changes for the release are committed to `main`
- **Before** `git push origin main --tags` (the tag triggers the release workflow)
- Bump should be the final commit before pushing

### Adding new versioned files

If a new file contains the version string and should be updated on bump, add a `[[tool.bumpversion.files]]` entry to `.bumpversion.toml`. Commit the config change before running the bump.

### Important

- The working directory must be clean (no uncommitted changes) before running `bump-my-version`
- If you need to fix something after bumping, delete the tag (`git tag -d v{version}`), reset the commit (`git reset --soft HEAD~1`), make your fix, commit it, then re-run `bump-my-version bump <part>`
