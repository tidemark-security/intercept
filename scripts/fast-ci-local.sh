#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/fast-ci-local.sh [--full] [--skip-images] [--base <ref>]

Runs the local equivalent of the Fast CI test jobs:
  - targeted backend pytest in the intercept Conda environment
  - frontend TypeScript typecheck
  - frontend Vitest suite

Use --full or FAST_CI_LOCAL_FULL=1 to run the complete backend suite.
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
  if [[ -n "${FAST_CI_LOCAL_CHANGED_FILES:-}" ]]; then
    printf '%s\n' "$FAST_CI_LOCAL_CHANGED_FILES"
    return
  fi

  if merge_base="$(git merge-base "$base_ref" HEAD 2>/dev/null)"; then
    git diff --name-only "$merge_base"...HEAD
  else
    git diff --name-only "$base_ref"...HEAD
  fi
  git diff --name-only
  git ls-files --others --exclude-standard
}

mapfile -t changed_file_list < <(changed_files | sed '/^$/d' | sort -u)

changed_files_output() {
  printf '%s\n' "${changed_file_list[@]}"
}

has_changed_build_input() {
  local pattern="$1"

  if [[ "$full" == "1" ]]; then
    return 0
  fi

  changed_files_output | grep -Eq "$pattern"
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

path_in_changed_files() {
  local candidate="$1"
  local existing

  for existing in "${backend_pytest_paths[@]}"; do
    if [[ "$existing" == "$candidate" ]]; then
      return 0
    fi
  done

  return 1
}

add_backend_pytest_path() {
  local candidate="$1"

  if ! path_in_changed_files "$candidate"; then
    backend_pytest_paths+=("$candidate")
  fi
}

mark_backend_unit_suite() {
  backend_unit_suite_needed=1
}

path_matches() {
  local path="$1"
  local pattern="$2"

  [[ "$path" =~ $pattern ]]
}

add_auth_backend_tests() {
  add_backend_pytest_path "tests/integration/auth"
}

add_api_key_backend_tests() {
  add_auth_backend_tests
  add_backend_pytest_path "tests/integration/mcp/test_mcp_authentication.py"
  add_backend_pytest_path "tests/integration/mcp/test_mcp_tool_execution.py"
}

add_alert_backend_tests() {
  add_backend_pytest_path "tests/integration/test_alert_create_api.py"
  add_backend_pytest_path "tests/integration/test_alert_bulk_actions_api.py"
  add_backend_pytest_path "tests/integration/test_alert_triage_api.py"
  add_backend_pytest_path "tests/integration/test_triage_recommendation_accept_api.py"
}

add_case_backend_tests() {
  add_backend_pytest_path "tests/integration/test_case_serialization_api.py"
  add_backend_pytest_path "tests/integration/test_case_timeline_items.py"
  add_backend_pytest_path "tests/integration/test_case_runbooks_api.py"
  add_backend_pytest_path "tests/integration/test_triage_recommendation_accept_api.py"
}

add_task_backend_tests() {
  add_backend_pytest_path "tests/integration/test_task_serialization_api.py"
  add_backend_pytest_path "tests/integration/test_task_timeline_items.py"
  add_backend_pytest_path "tests/integration/test_task_attachments_api.py"
}

add_timeline_backend_tests() {
  add_backend_pytest_path "tests/integration/test_alert_timeline_items.py"
  add_backend_pytest_path "tests/integration/test_case_timeline_items.py"
  add_backend_pytest_path "tests/integration/test_task_timeline_items.py"
  add_backend_pytest_path "tests/integration/test_timeline_graph_api.py"
}

add_langflow_backend_tests() {
  add_backend_pytest_path "tests/integration/test_langflow_chat_authorization.py"
  add_backend_pytest_path "tests/integration/test_langflow_connection_api.py"
  add_backend_pytest_path "tests/integration/test_langflow_service.py"
  add_backend_pytest_path "tests/integration/test_langflow_setup_api.py"
}

add_enrichment_backend_tests() {
  add_backend_pytest_path "tests/integration/test_enrichments_api.py"
  add_backend_pytest_path "tests/integration/test_maxmind_admin_api.py"
}

add_mcp_backend_tests() {
  add_backend_pytest_path "tests/unit/mcp"
  add_backend_pytest_path "tests/integration/mcp"
}

add_search_backend_tests() {
  add_backend_pytest_path "tests/integration/test_search_api.py"
}

add_smoke_backend_tests() {
  add_backend_pytest_path "tests/integration/auth/test_login_flow.py::test_login_success"
}

select_backend_pytest() {
  backend_pytest_paths=()
  backend_unit_suite_needed=0
  backend_pytest_mode="skip"
  backend_pytest_reason="no backend-relevant changes"

  if [[ "$full" == "1" ]]; then
    backend_pytest_mode="full"
    backend_pytest_reason="--full or FAST_CI_LOCAL_FULL=1 requested"
    return
  fi

  local saw_backend_relevant=0
  local saw_backend_app_or_script=0
  local saw_mapped_backend_app=0
  local file

  for file in "${changed_file_list[@]}"; do
    case "$file" in
      backend/requirements*.txt|backend/pytest.ini|backend/alembic.ini|backend/init*.sql|backend/Dockerfile*|backend/tests/conftest.py|backend/tests/fixtures/*|backend/tests/fixtures/**/*|backend/db_migrations/*|backend/db_migrations/**/*|backend/app/models/*|backend/app/models/**/*|backend/app/main.py|backend/app/api/route_utils.py|backend/app/api/routes/__init__.py|backend/app/core/database.py|backend/app/core/security.py|backend/app/core/settings_registry.py|backend/app/core/config.py|backend/app/core/csrf.py)
        backend_pytest_mode="full"
        backend_pytest_reason="broad-risk backend change: $file"
        return
        ;;
    esac

    if [[ "$file" == backend/tests/unit/test_database_safety.py ]]; then
      saw_backend_relevant=1
      add_backend_pytest_path "tests/unit/test_database_safety.py"
      continue
    fi

    if [[ "$file" == backend/tests/*.py || "$file" == backend/tests/**/*.py ]]; then
      saw_backend_relevant=1
      add_backend_pytest_path "${file#backend/}"
      continue
    fi

    if [[ "$file" == backend/app/*.py || "$file" == backend/app/**/*.py || "$file" == backend/scripts/*.py || "$file" == backend/scripts/**/*.py || "$file" == backend/worker.py ]]; then
      saw_backend_relevant=1
      saw_backend_app_or_script=1
      mark_backend_unit_suite
    else
      continue
    fi

    local lower_file="${file,,}"

    if path_matches "$lower_file" 'auth|admin_auth|oidc|passkey|csrf|security'; then
      add_auth_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'api_key'; then
      add_api_key_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'alert|triage_recommendation|triage_apply'; then
      add_alert_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'case|runbook'; then
      add_case_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'task|queue_status|task_queue|worker'; then
      add_task_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'timeline|normalization|observable'; then
      add_timeline_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'langflow'; then
      add_langflow_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'enrichment|entra|google_workspace|ldap|servicenow|service_now|maxmind'; then
      add_enrichment_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'mcp'; then
      add_mcp_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'search|similarity'; then
      add_search_backend_tests
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'setting'; then
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'link_template'; then
      add_backend_pytest_path "tests/integration/test_link_templates.py"
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'context'; then
      add_backend_pytest_path "tests/integration/test_context_entries.py"
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'dashboard'; then
      add_backend_pytest_path "tests/integration/test_dashboard_sidebar_counts_api.py"
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'metric|soc_metrics'; then
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'audit'; then
      add_backend_pytest_path "tests/integration/test_audit_api.py"
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'dummy_data'; then
      add_backend_pytest_path "tests/integration/test_dummy_data_api.py"
      saw_mapped_backend_app=1
    fi

    if path_matches "$lower_file" 'storage|attachment|email_evidence'; then
      add_backend_pytest_path "tests/integration/test_case_attachments_api.py"
      add_backend_pytest_path "tests/integration/test_task_attachments_api.py"
      saw_mapped_backend_app=1
    fi
  done

  if [[ "$saw_backend_relevant" == "0" ]]; then
    return
  fi

  if [[ "$backend_unit_suite_needed" == "1" ]]; then
    backend_pytest_paths=("tests/unit" "${backend_pytest_paths[@]}")
  fi

  if [[ "$saw_backend_app_or_script" == "1" && "$saw_mapped_backend_app" == "0" ]]; then
    add_smoke_backend_tests
    backend_pytest_reason="unknown backend app/script change; running unit suite plus login smoke"
  else
    backend_pytest_reason="targeted backend changes"
  fi

  backend_pytest_mode="targeted"
}

print_backend_pytest_command() {
  local display=("conda" "run" "-n" "intercept" "pytest")
  local path

  if [[ "$backend_pytest_mode" == "targeted" ]]; then
    for path in "${backend_pytest_paths[@]}"; do
      display+=("$path")
    done
  fi

  printf 'fast-ci-local: backend pytest command: (cd backend &&'
  printf ' %q' "${display[@]}"
  printf ')\n'
}

run_backend_pytest() {
  select_backend_pytest

  echo
  echo "fast-ci-local: backend pytest selection: $backend_pytest_reason"

  case "$backend_pytest_mode" in
    skip)
      echo "fast-ci-local: skipping backend pytest"
      ;;
    full)
      print_backend_pytest_command
      run_in_dir backend conda run -n intercept pytest
      ;;
    targeted)
      print_backend_pytest_command
      run_in_dir backend conda run -n intercept pytest "${backend_pytest_paths[@]}"
      ;;
    *)
      echo "fast-ci-local: unknown backend pytest mode: $backend_pytest_mode" >&2
      exit 2
      ;;
  esac
}

run_backend_pytest

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
