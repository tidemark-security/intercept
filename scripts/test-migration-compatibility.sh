#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_PREFIX="${IMAGE_PREFIX:-ghcr.io/tidemark-security}"
N_MINUS_1_TAG="${N_MINUS_1_TAG:?Set N_MINUS_1_TAG to the previous released image tag, e.g. 0.4.0}"
CANDIDATE_BACKEND_IMAGE="${CANDIDATE_BACKEND_IMAGE:-intercept-backend:migration-candidate}"
POSTGRES_DB="${POSTGRES_DB:-intercept_case_db}"
POSTGRES_USER="${POSTGRES_USER:-intercept_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-intercept_password}"
SECRET_KEY="${SECRET_KEY:-migration-compatibility-secret-key}"
BACKEND_PORT="${BACKEND_PORT:-18000}"
RUN_ROLLBACK_SMOKE="${RUN_ROLLBACK_SMOKE:-false}"
ROLLBACK_SKIP_MIGRATIONS="${ROLLBACK_SKIP_MIGRATIONS:-true}"

PREVIOUS_POSTGRES_IMAGE="${IMAGE_PREFIX}/intercept-postgres:${N_MINUS_1_TAG}"
PREVIOUS_BACKEND_IMAGE="${IMAGE_PREFIX}/intercept-backend:${N_MINUS_1_TAG}"
PREVIOUS_FRONTEND_IMAGE="${IMAGE_PREFIX}/intercept-frontend:${N_MINUS_1_TAG}"
PREVIOUS_WORKER_IMAGE="${IMAGE_PREFIX}/intercept-worker:${N_MINUS_1_TAG}"

RUN_SUFFIX="${GITHUB_RUN_ID:-local}-$$"
NETWORK_NAME="migration-compat-${RUN_SUFFIX}"
POSTGRES_CONTAINER="migration-compat-postgres-${RUN_SUFFIX}"
CANDIDATE_BACKEND_CONTAINER="migration-compat-backend-${RUN_SUFFIX}"
ROLLBACK_BACKEND_CONTAINER="migration-compat-rollback-backend-${RUN_SUFFIX}"
ROLLBACK_FRONTEND_CONTAINER="migration-compat-rollback-frontend-${RUN_SUFFIX}"
ROLLBACK_WORKER_CONTAINER="migration-compat-rollback-worker-${RUN_SUFFIX}"
INIT_EXTRACT_CONTAINER="migration-compat-init-extract-${RUN_SUFFIX}"
POSTGRES_VOLUME="migration-compat-postgres-data-${RUN_SUFFIX}"
TMP_DIR="$(mktemp -d)"

DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_CONTAINER}:5432/${POSTGRES_DB}"

log() {
    printf '\n==> %s\n' "$*"
}

cleanup() {
    set +e
    docker rm -f \
        "$INIT_EXTRACT_CONTAINER" \
        "$CANDIDATE_BACKEND_CONTAINER" \
        "$ROLLBACK_BACKEND_CONTAINER" \
        "$ROLLBACK_FRONTEND_CONTAINER" \
        "$ROLLBACK_WORKER_CONTAINER" \
        "$POSTGRES_CONTAINER" >/dev/null 2>&1
    docker volume rm "$POSTGRES_VOLUME" >/dev/null 2>&1
    docker network rm "$NETWORK_NAME" >/dev/null 2>&1
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

wait_for_postgres() {
    log "Waiting for PostgreSQL readiness"
    for _ in {1..60}; do
        if docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    docker logs "$POSTGRES_CONTAINER" || true
    echo "PostgreSQL did not become ready" >&2
    return 1
}

wait_for_http() {
    local url="$1"
    local container_name="$2"

    for _ in {1..60}; do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    docker logs "$container_name" || true
    echo "Timed out waiting for $url" >&2
    return 1
}

docker_run_backend_env=(
    -e "DATABASE_URL=${DATABASE_URL}"
    -e "SECRET_KEY=${SECRET_KEY}"
    -e "AUTO_SEED=false"
    -e "CSRF_ENABLED=false"
    -e "SESSION_COOKIE_SECURE=false"
    -e "LOG_LEVEL=INFO"
)

get_single_alembic_head() {
    local image="$1"
    local heads
    heads="$(docker run --rm --entrypoint alembic "$image" heads --resolve-dependencies | awk '{print $1}')"

    local head_count
    head_count="$(printf '%s\n' "$heads" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [[ "$head_count" != "1" ]]; then
        printf 'Expected exactly one Alembic head in %s, found %s:\n%s\n' "$image" "$head_count" "$heads" >&2
        return 1
    fi

    printf '%s\n' "$heads" | sed '/^$/d'
}

log "Pulling previous release images for ${N_MINUS_1_TAG}"
docker pull "$PREVIOUS_POSTGRES_IMAGE"
docker pull "$PREVIOUS_BACKEND_IMAGE"

if [[ "$RUN_ROLLBACK_SMOKE" == "true" ]]; then
    docker pull "$PREVIOUS_FRONTEND_IMAGE"
    docker pull "$PREVIOUS_WORKER_IMAGE"
fi

log "Resolving N-1 Alembic head"
PREVIOUS_ALEMBIC_HEAD="$(get_single_alembic_head "$PREVIOUS_BACKEND_IMAGE")"
echo "Using N-1 Alembic head: ${PREVIOUS_ALEMBIC_HEAD}"

log "Extracting N-1 database init scripts from previous backend image"
docker create --name "$INIT_EXTRACT_CONTAINER" "$PREVIOUS_BACKEND_IMAGE" >/dev/null
docker cp "$INIT_EXTRACT_CONTAINER:/app/init.sql" "$TMP_DIR/01-init.sql"
docker cp "$INIT_EXTRACT_CONTAINER:/app/init-pgcron.sql" "$TMP_DIR/02-init-pgcron.sql"
docker cp "$INIT_EXTRACT_CONTAINER:/app/init-pgvector.sql" "$TMP_DIR/03-init-pgvector.sql"
docker rm "$INIT_EXTRACT_CONTAINER" >/dev/null

log "Starting N-1 PostgreSQL image"
docker network create "$NETWORK_NAME" >/dev/null
docker volume create "$POSTGRES_VOLUME" >/dev/null
docker run -d \
    --name "$POSTGRES_CONTAINER" \
    --network "$NETWORK_NAME" \
    -e "POSTGRES_DB=${POSTGRES_DB}" \
    -e "POSTGRES_USER=${POSTGRES_USER}" \
    -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    -e "PGDATA=/var/lib/postgresql/data/pgdata" \
    -v "$POSTGRES_VOLUME:/var/lib/postgresql/data" \
    -v "$TMP_DIR/01-init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro" \
    -v "$TMP_DIR/02-init-pgcron.sql:/docker-entrypoint-initdb.d/02-init-pgcron.sql:ro" \
    -v "$TMP_DIR/03-init-pgvector.sql:/docker-entrypoint-initdb.d/03-init-pgvector.sql:ro" \
    "$PREVIOUS_POSTGRES_IMAGE" \
    postgres \
    -c shared_preload_libraries=pg_cron \
    -c cron.database_name=postgres >/dev/null
wait_for_postgres

log "Verifying required PostgreSQL extensions"
docker exec -e "PGPASSWORD=${POSTGRES_PASSWORD}" "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
    -c "SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pg_trgm', 'vector') ORDER BY extname;"
docker exec -e "PGPASSWORD=${POSTGRES_PASSWORD}" "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT extname FROM pg_extension WHERE extname = 'pg_cron';"

log "Bootstrapping database to N-1 Alembic head with candidate migration scripts"
docker run --rm \
    --name "migration-compat-n-minus-1-${RUN_SUFFIX}" \
    --network "$NETWORK_NAME" \
    "${docker_run_backend_env[@]}" \
    --entrypoint alembic \
    "$CANDIDATE_BACKEND_IMAGE" \
    upgrade "$PREVIOUS_ALEMBIC_HEAD"

log "N-1 Alembic revision"
docker exec -e "PGPASSWORD=${POSTGRES_PASSWORD}" "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
    -c "SELECT version_num FROM alembic_version;"

log "Upgrading database with candidate backend image"
docker run --rm \
    --name "migration-compat-candidate-upgrade-${RUN_SUFFIX}" \
    --network "$NETWORK_NAME" \
    "${docker_run_backend_env[@]}" \
    "$CANDIDATE_BACKEND_IMAGE" \
    python -c "print('Candidate migrations complete')"

log "Re-running candidate migrations and checking Alembic heads"
docker run --rm \
    --name "migration-compat-candidate-current-${RUN_SUFFIX}" \
    --network "$NETWORK_NAME" \
    "${docker_run_backend_env[@]}" \
    "$CANDIDATE_BACKEND_IMAGE" \
    alembic current --check-heads

log "Starting candidate backend smoke test"
docker run -d \
    --name "$CANDIDATE_BACKEND_CONTAINER" \
    --network "$NETWORK_NAME" \
    -p "127.0.0.1:${BACKEND_PORT}:8000" \
    "${docker_run_backend_env[@]}" \
    "$CANDIDATE_BACKEND_IMAGE" >/dev/null
wait_for_http "http://127.0.0.1:${BACKEND_PORT}/health" "$CANDIDATE_BACKEND_CONTAINER"
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health"
docker rm -f "$CANDIDATE_BACKEND_CONTAINER" >/dev/null

if [[ "$RUN_ROLLBACK_SMOKE" == "true" ]]; then
    log "Starting optional N-1 app rollback smoke test"
    if [[ "$ROLLBACK_SKIP_MIGRATIONS" == "true" ]]; then
        docker run -d \
            --name "$ROLLBACK_BACKEND_CONTAINER" \
            --network "$NETWORK_NAME" \
            -p "127.0.0.1:$((BACKEND_PORT + 1)):8000" \
            --entrypoint uvicorn \
            "${docker_run_backend_env[@]}" \
            "$PREVIOUS_BACKEND_IMAGE" \
            app.main:app --host 0.0.0.0 --port 8000 >/dev/null
    else
        docker run -d \
            --name "$ROLLBACK_BACKEND_CONTAINER" \
            --network "$NETWORK_NAME" \
            -p "127.0.0.1:$((BACKEND_PORT + 1)):8000" \
            "${docker_run_backend_env[@]}" \
            "$PREVIOUS_BACKEND_IMAGE" >/dev/null
    fi
    wait_for_http "http://127.0.0.1:$((BACKEND_PORT + 1))/health" "$ROLLBACK_BACKEND_CONTAINER"

    docker run -d \
        --name "$ROLLBACK_WORKER_CONTAINER" \
        --network "$NETWORK_NAME" \
        -p "127.0.0.1:$((BACKEND_PORT + 2)):8001" \
        "${docker_run_backend_env[@]}" \
        -e "WORKER_CONCURRENCY=1" \
        -e "HEALTH_PORT=8001" \
        "$PREVIOUS_WORKER_IMAGE" >/dev/null
    wait_for_http "http://127.0.0.1:$((BACKEND_PORT + 2))/ready" "$ROLLBACK_WORKER_CONTAINER"

    docker run -d \
        --name "$ROLLBACK_FRONTEND_CONTAINER" \
        --network "$NETWORK_NAME" \
        -p "127.0.0.1:18080:80" \
        "$PREVIOUS_FRONTEND_IMAGE" >/dev/null
    wait_for_http "http://127.0.0.1:18080/" "$ROLLBACK_FRONTEND_CONTAINER"
fi

log "Migration compatibility check completed"
