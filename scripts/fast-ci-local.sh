#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/fast-ci-local.sh [--full] [--skip-images] [--base <ref>]

Runs the local equivalent of the Fast CI test jobs:
  - backend pytest in the intercept Conda environment
  - frontend TypeScript typecheck
  - frontend Vitest suite

Docker image builds run when relevant build inputs changed, or when --full
or FAST_CI_LOCAL_FULL=1 is set.
USAGE
}

repo_root="$(git rev-parse --show-toplevel)"
base_ref=""
full="${FAST_CI_LOCAL_FULL:-0}"
skip_images="${FAST_CI_LOCAL_SKIP_IMAGES:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)
      full=1
      shift
      ;;
    --skip-images)
      skip_images=1
      shift
      ;;
    --base)
      if [[ $# -lt 2 ]]; then
        echo "fast-ci-local: --base requires a ref" >&2
        exit 2
      fi
      base_ref="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "fast-ci-local: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$repo_root"

if [[ -z "$base_ref" ]]; then
  if upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null)"; then
    base_ref="$upstream"
  else
    base_ref="HEAD~1"
  fi
fi

changed_files() {
  if merge_base="$(git merge-base "$base_ref" HEAD 2>/dev/null)"; then
    git diff --name-only "$merge_base"...HEAD
  else
    git diff --name-only "$base_ref"...HEAD
  fi
  git diff --name-only
}

has_changed_build_input() {
  local pattern="$1"

  if [[ "$full" == "1" ]]; then
    return 0
  fi

  changed_files | grep -Eq "$pattern"
}

run_step() {
  echo
  echo "fast-ci-local: $*"
  "$@"
}

run_in_dir() {
  local dir="$1"
  shift

  echo
  echo "fast-ci-local: (cd $dir && $*)"
  (cd "$dir" && "$@")
}

run_in_dir backend conda run -n intercept pytest

if [[ "${FAST_CI_LOCAL_INSTALL:-0}" == "1" || ! -d frontend/node_modules ]]; then
  run_step npm --prefix frontend install --no-audit --no-fund
fi

run_in_dir frontend npx tsc --noEmit
run_in_dir frontend npm test

if [[ "$skip_images" == "1" ]]; then
  echo
  echo "fast-ci-local: skipping Docker image builds"
  exit 0
fi

if has_changed_build_input '^(backend/Dockerfile|backend/Dockerfile\.worker|backend/requirements[^/]*\.txt|backend/\.dockerignore)$'; then
  run_step docker build -f backend/Dockerfile backend
  run_step docker build -f backend/Dockerfile.worker backend
else
  echo
  echo "fast-ci-local: backend image inputs unchanged; skipping backend image builds"
fi

if has_changed_build_input '^(frontend/Dockerfile|frontend/package\.json|frontend/package-lock\.json|frontend/\.dockerignore)$'; then
  run_step docker build -f frontend/Dockerfile frontend
else
  echo
  echo "fast-ci-local: frontend image inputs unchanged; skipping frontend image build"
fi

echo
echo "fast-ci-local: passed"
