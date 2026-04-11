#!/usr/bin/env bash
# Called by bump-my-version as a pre_commit_hook.
# Regenerates package-lock.json after package.json version bump and stages it.
set -euo pipefail
cd frontend
npm install --package-lock-only
git add package-lock.json
