#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

git -C "$repo_root" config core.hooksPath .githooks

echo "Configured git hooks path to .githooks"
echo "Pre-commit hook is now active for this clone."