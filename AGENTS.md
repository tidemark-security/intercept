# Agent Instructions

## Development Environment

Use the `intercept` Conda environment for repository commands.

```bash
conda activate intercept
```

If `conda` is not on `PATH` in a non-interactive shell, initialize it first:

```bash
eval "$(~/miniconda3/bin/conda shell.bash hook)"
conda activate intercept
```

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
2. Creates a git commit (`release: v{new_version}`)
3. Does **not** create a git tag. The GitHub Release workflow creates `v{new_version}` after the version bump commit is merged to `main`.

### When to bump

- **After** all code changes for the release are committed on the release branch
- **Before** merging the release branch to `main`
- Bump should be the final commit on the release branch before merge
- After the merge reaches `main`, `.github/workflows/release.yml` creates the `v{new_version}` tag from `VERSION` and runs the release

### Adding new versioned files

If a new file contains the version string and should be updated on bump, add a `[[tool.bumpversion.files]]` entry to `.bumpversion.toml`. Commit the config change before running the bump.

### Important

- The working directory must be clean (no uncommitted changes) before running `bump-my-version`
- If you need to fix something after bumping but before merging to `main`, reset the bump commit (`git reset --soft HEAD~1`), make your fix, commit it, then re-run `bump-my-version bump <part>`
- Do not create or push release tags manually; release tags are owned by `.github/workflows/release.yml`
