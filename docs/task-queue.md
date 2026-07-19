# Task Queue System

Intercept uses **pgqueuer** for background job processing, leveraging PostgreSQL as the job queue backend. This provides reliable, transactional task execution without requiring additional infrastructure like Redis or RabbitMQ.

## Overview

The task queue system enables:

- **Asynchronous task execution** - Offload long-running operations from HTTP requests
- **Scheduled tasks** - Execute tasks at a specified future time
- **Automatic retries** - Failed tasks are retried in-worker with configurable backoff
- **Priority-based processing** - Higher priority tasks are processed first
- **Transactional guarantees** - Jobs are stored in PostgreSQL with ACID properties
- **Standalone workers** - Workers run in separate containers for horizontal scaling
- **Connection pooling** - Robust database connections for long-running workers

## Architecture

The system separates the API (producer) from workers (consumers):

```
┌─────────────────┐                         ┌─────────────────┐
│   FastAPI App   │─────── enqueue ────────▶│   PostgreSQL    │
│   (Producer)    │                         │   (pgqueuer)    │
│   Port 8000     │                         └─────────────────┘
└─────────────────┘                                │
                                                   │
                                   ┌───────────────┼───────────────┐
                                   ▼               ▼               ▼
                            ┌──────────┐    ┌──────────┐    ┌──────────┐
                            │ Worker 1 │    │ Worker 2 │    │ Worker N │
                            │ :8001    │    │ :8001    │    │ :8001    │
                            │ /health  │    │ /health  │    │ /health  │
                            │ /metrics │    │ /metrics │    │ /metrics │
                            └──────────┘    └──────────┘    └──────────┘
```

### Deployment Model

| Container | Role | Description |
|-----------|------|-------------|
| `backend` | Producer | FastAPI API that enqueues tasks |
| `worker` | Consumer | Standalone process that executes tasks |
| `postgres` | Queue Store | PostgreSQL database with pgqueuer tables |

### Components

| Component | Description |
|-----------|-------------|
| `TaskQueueService` | Main service class managing queue operations |
| `QueueManager` | pgqueuer component that processes jobs |
| `Queries` | pgqueuer component for database operations |
| `AsyncpgPoolDriver` | Connection pool driver for robust long-running connections |
| Task Handlers | Async functions that process specific task types |
| `worker.py` | Standalone worker entry point with health server |

## Running Workers

### Docker Compose

Workers run as a separate service in `dev/docker-compose.yml`:

```yaml
worker:
  build:
    context: ./backend
    dockerfile: Dockerfile.dev
  environment:
    DATABASE_URL: postgresql+asyncpg://user:pass@postgres:5432/db
    WORKER_CONCURRENCY: "20"
    HEALTH_PORT: "8001"
    LOG_LEVEL: "INFO"
  ports:
    - "8001:8001"  # Health/metrics endpoint
  command: ["python", "worker.py"]
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8001/ready"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `WORKER_CONCURRENCY` | `20` | Number of concurrent tasks |
| `HEALTH_PORT` | `8001` | Port for health/metrics server |
| `WORKER_DATABASE_COMMAND_TIMEOUT_SECONDS` | `60` | asyncpg command timeout for queue database operations |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `WORKER_ID` | hostname | Identifier for metrics/logging |
| `SECRET_KEY` | required | Encryption key (same as backend) |

### Scaling Workers

Scale horizontally by running multiple worker containers:

```bash
# Docker Compose (from dev/ directory)
docker compose up -d --scale worker=3

# Kubernetes
kubectl scale deployment worker --replicas=3
```

### Health Endpoints

Each worker exposes HTTP endpoints on the configured `HEALTH_PORT`:

| Endpoint | Description | Use Case |
|----------|-------------|----------|
| `GET /health` | Liveness probe | Container orchestrator crash detection |
| `GET /ready` | Readiness probe | Load balancer routing decisions |
| `GET /metrics` | Prometheus metrics | Monitoring and alerting |

#### Health Endpoint Responses

```json
// GET /health
{"status": "healthy", "worker_id": "container-id", "uptime_seconds": 3600.0}

// GET /ready
{"status": "ready", "worker_id": "container-id", "pool_size": 4}
```

#### Metrics Available (Prometheus format)

```prometheus
# Worker identity
worker_info{worker_id="container-id"} 1

# Worker uptime
worker_uptime_seconds 3600.00

# Queue status
worker_queue_size 15
```

## Configuration

The task queue uses the same PostgreSQL database as the main application. Configuration is automatic via the `DATABASE_URL` environment variable.

```python
# Initialized during app startup in main.py
await initialize_task_queue_service(get_local("database.url"))
```

### Connection Pooling

The task queue uses `asyncpg` connection pooling for robust long-running workers:

- **Min connections**: 2 (always available)
- **Max connections**: 10 (scales with load)
- **Command timeout**: 60 seconds by default (`worker.database.command_timeout_seconds`, local-only)
- **Auto-reconnection**: Pool handles connection failures automatically

This prevents "connection is closed" errors that occur with single connections in long-running worker processes.

### Worker Task Runtime Settings

Task execution timeouts and retry backoff are declared in the settings registry. Running workers refresh DB-backed admin settings every `worker.task_settings_refresh_interval_seconds` seconds; environment variable changes still require a worker process restart.

How hot settings changes work:

1. The worker keeps an in-memory snapshot of task timeout and retry settings.
2. A background refresh loop reloads DB-backed settings on a timer.
3. Each new task attempt copies the latest snapshot before it starts.
4. A task that is already running keeps the snapshot it started with, so settings changes do not interrupt in-flight work.

| Setting | Default | Description |
|---------|---------|-------------|
| `worker.tasks.default.execution_timeout_seconds` | `600` | Default timeout for one task attempt |
| `worker.tasks.directory_sync.execution_timeout_seconds` | `3600` | Timeout for directory sync attempts, including Entra ID bulk sync |
| `worker.tasks.<task_name>.execution_timeout_seconds` | unset | Optional per-task override; unset inherits the default |
| `worker.tasks.retry_initial_delay_seconds` | `5` | Initial in-worker retry backoff |
| `worker.tasks.retry_max_delay_seconds` | `60` | Maximum in-worker retry backoff |
| `worker.tasks.retry_timer_buffer_seconds` | `300` | Extra stale-job lease time above the execution timeout |
| `worker.task_settings_refresh_interval_seconds` | `30` | Worker polling interval for hot-swappable task settings |

Hot-swap semantics:

- A running task attempt keeps the timeout snapshot it started with.
- Newly picked jobs and later in-worker retry attempts use the latest refreshed snapshot.
- pgqueuer stale-job leases only increase while a worker process is running. Lower lease values take full effect after a worker restart, which avoids duplicate execution caused by lowering a heartbeat lease under active jobs.
- Docker Compose healthcheck `timeout: 5s`, frontend/test timeouts, MCP Mermaid validation timeout, and provider HTTP request timeouts are separate from worker task execution timeouts.

For large Microsoft Entra ID tenants, tune both the task timeout and the Graph paging controls:

| Setting | Default | Description |
|---------|---------|-------------|
| `enrichment.entra_id.request_timeout_seconds` | `30` | Per-request timeout for Entra ID HTTP calls |
| `enrichment.entra_id.bulk_sync_page_size` | `999` | Graph users page size, clamped to 1-999 |
| `enrichment.entra_id.bulk_sync_max_records` | `0` | Maximum users processed per sync; `0` means unlimited |

### Database Schema

pgqueuer automatically creates these tables on first startup:

- `pgqueuer` - Main job queue table
- `pgqueuer_log` - Job execution history
- `pgqueuer_schedule` - Scheduled/recurring jobs
- `pgqueuer_statistics_log` - Performance metrics

## Usage

### Enqueueing Tasks

To enqueue a background task from anywhere in the application:

```python
from app.services.task_queue_service import get_task_queue_service
from datetime import datetime, timezone, timedelta

# Get the task queue service
task_queue = get_task_queue_service()

# Enqueue a task for immediate execution
job_id = await task_queue.enqueue(
    task_name="langflow_chat",
    payload={
        "session_id": "uuid-string",
        "message": "Hello, AI!",
        "flow_id": "my-flow-id",
    },
)

# Enqueue a task with priority (higher = more important)
job_id = await task_queue.enqueue(
    task_name="langflow_chat",
    payload={"...": "..."},
    priority=10,  # Default is 0
)

# Schedule a task for future execution
job_id = await task_queue.enqueue(
    task_name="langflow_batch",
    payload={"...": "..."},
    schedule_at=datetime.now(timezone.utc) + timedelta(hours=1),
)
```

### Defining Task Handlers

Task handlers are async functions that process jobs:

```python
# In app/services/tasks.py

from typing import Dict, Any

async def handle_my_task(payload: Dict[str, Any]):
    """
    Process a background task.
    
    Args:
        payload: JSON-serializable dict passed when task was enqueued
    """
    item_id = payload["item_id"]
    action = payload["action"]
    
    # Do the work...
    result = await process_item(item_id, action)
    
    # If the handler raises an exception, the task will be retried
    if not result.success:
        raise RuntimeError(f"Processing failed: {result.error}")
```

### Registering Handlers

Handlers must be registered during application startup:

```python
# In app/services/tasks.py

async def register_task_handlers():
    """Register all task handlers during app startup."""
    task_queue = get_task_queue_service()
    async with async_session_factory() as db:
        await task_queue.refresh_task_runtime_config(SettingsService(db))
    
    task_queue.register_handler(
        task_name="my_task",
        handler=handle_my_task,
        max_retries=3,  # Retry up to 3 additional times after the initial attempt
    )
```

`register_handler()` uses a custom executor with settings-backed execution timeouts and in-worker retry/backoff behavior. The retry loop happens inside a single worker execution rather than by creating a new queue row for each attempt.

Current defaults in Intercept:

- `max_retries` means retries after the initial attempt
- Initial backoff delay: `worker.tasks.retry_initial_delay_seconds` (default 5 seconds)
- Maximum backoff delay: `worker.tasks.retry_max_delay_seconds` (default 60 seconds)
- Default task attempt timeout: `worker.tasks.default.execution_timeout_seconds` (default 10 minutes)
- Directory sync attempt timeout: `worker.tasks.directory_sync.execution_timeout_seconds` (default 60 minutes)
- Optional terminal failure hook: runs once after retries are exhausted

This is called automatically in `main.py`:

```python
# In app/main.py lifespan
await initialize_task_queue_service(get_local("database.url"))
await register_task_handlers()
```

## Built-in Task Types

### `langflow_chat`

Handles asynchronous LangFlow chat operations.

**Payload:**
```python
{
    "session_id": "uuid-string",  # Chat session ID
    "message": "User message",     # Message content
    "flow_id": "flow-identifier",  # LangFlow flow ID
    "context": {}                  # Optional context dict
}
```

### `langflow_batch`

Handles batch processing of multiple messages through LangFlow.

**Payload:**
```python
{
    "flow_id": "flow-identifier",
    "messages": [
        {"id": "msg-1", "content": "First message", "context": {}},
        {"id": "msg-2", "content": "Second message", "context": {}},
    ]
}
```

### `triage_alert`

Runs AI alert triage through LangFlow.

Failure behavior:

- The recommendation remains `QUEUED` during retry attempts
- The recommendation is marked `FAILED` only after retries are exhausted
- The final `error_message` records the terminal failure cause

### `enrich_item`

Runs provider enrichment for a timeline item.

Failure behavior:

- Timeline items remain `pending` during retry attempts
- On terminal failure, `enrichment_status` is cleared so the item is not left stuck in `pending`
- A system error payload is written into the item's `enrichments` map

## Error Handling & Retries

When a task handler raises an exception:

1. The error is logged with task details
2. The custom retry executor retries the handler in-process with exponential backoff and jitter
3. Retries continue until `max_retries` is exhausted; each attempt has its own configured execution timeout
4. If configured, a terminal failure hook runs once after retries are exhausted
5. The job ends in pgqueuer's terminal `exception` state and is written to `pgqueuer_log`

Important distinctions:

- `retry_timer` is still used by pgqueuer to recover stale `picked` jobs if a worker dies or stops heartbeating
- `retry_timer` is not the bounded retry policy for normal handler exceptions
- task execution timeouts are registry settings and are enforced by the Intercept executor
- Retry attempt counts are tracked in the running executor, not persisted on the job row

```python
# Handler that may fail and retry
async def handle_external_api_call(payload: Dict[str, Any]):
    try:
        response = await external_api.call(payload["endpoint"])
        return response
    except TimeoutError:
        # This will trigger a retry
        raise
    except ValidationError as e:
        # Log and complete without retrying
        logger.error(f"Validation failed: {e}")
        # Don't re-raise - task completes successfully from the queue's perspective
```

## Monitoring

### Logging

All task operations are logged:

```
INFO - Enqueued task: langflow_chat (task_id=123, priority=0)
INFO - Processing task: langflow_chat (task_id=123)
INFO - Completed task: langflow_chat (task_id=123)
ERROR - Task failed: langflow_chat (task_id=123, error=...)
ERROR - Exception while processing entrypoint/job-id: langflow_chat/123
```

### Database Queries

Check queue status directly in PostgreSQL:

```sql
-- View pending jobs
SELECT * FROM pgqueuer WHERE status = 'queued' ORDER BY priority DESC, created_at;

-- View recent job history, including terminal exceptions
SELECT * FROM pgqueuer_log ORDER BY created_at DESC LIMIT 100;

-- View recent failed jobs
SELECT * FROM pgqueuer_log WHERE status = 'exception' ORDER BY created_at DESC LIMIT 100;

-- Queue statistics
SELECT entrypoint, status, COUNT(*) 
FROM pgqueuer 
GROUP BY entrypoint, status;
```

## Worker Management

Workers run as **standalone containers** separate from the FastAPI API process. The API only enqueues tasks; workers process them.

### Architecture

- **Backend container**: Initializes task queue in "enqueue-only" mode
- **Worker container(s)**: Run `worker.py` to process tasks from the queue

### Starting Workers

```bash
# Start worker container
docker compose -f dev/docker-compose.yml up -d worker

# View worker logs
docker compose -f dev/docker-compose.yml logs -f worker

# Scale to multiple workers
docker compose -f dev/docker-compose.yml up -d --scale worker=3
```

### Concurrency

The `max_concurrent_tasks` parameter controls how many tasks can be processed simultaneously per worker. Default is 20 (configurable via `WORKER_CONCURRENCY` env var).

- Higher `WORKER_CONCURRENCY` = more throughput but more resource usage
- Lower `WORKER_CONCURRENCY` = less resource usage but slower processing
- For I/O-bound tasks (API calls), higher concurrency is beneficial (20-50)
- For CPU-bound tasks, match to available CPU cores (2-4)
- Scale horizontally with multiple worker containers for high throughput

## Best Practices

### 1. Keep Payloads Small

Store minimal data in the payload; fetch full data from the database in the handler:

```python
# ✅ Good - minimal payload
await task_queue.enqueue("process_alert", {"alert_id": 123})

# ❌ Bad - large payload
await task_queue.enqueue("process_alert", {"alert": full_alert_object})
```

### 2. Make Handlers Idempotent

Handlers may be executed more than once (retries). Design for idempotency:

```python
async def handle_send_notification(payload: Dict[str, Any]):
    notification_id = payload["notification_id"]
    
    # Check if already processed
    existing = await db.get_notification(notification_id)
    if existing.sent_at:
        logger.info(f"Notification {notification_id} already sent, skipping")
        return
    
    # Process and mark as sent atomically
    await send_and_mark_sent(notification_id)
```

### 3. Use Appropriate Priorities

Reserve high priorities for time-sensitive tasks:

```python
PRIORITY_LOW = 0       # Batch processing, reports
PRIORITY_NORMAL = 5    # Standard operations
PRIORITY_HIGH = 10     # User-initiated actions
PRIORITY_CRITICAL = 20 # Security alerts
```

### 4. Handle Timeouts

Set reasonable timeouts for external operations. These are request-level limits inside a task, separate from `worker.tasks.*.execution_timeout_seconds`:

```python
async def handle_external_call(payload: Dict[str, Any]):
    async with asyncio.timeout(30):  # 30 second timeout
        await external_service.call(payload["data"])
```

## Troubleshooting

### Tasks Not Processing

1. Check if workers are running:
   ```bash
   docker compose -f dev/docker-compose.yml ps worker
   docker compose -f dev/docker-compose.yml logs worker --tail=50
   ```

2. Check worker readiness:
   ```bash
   curl http://localhost:8001/ready
   ```

3. Verify handlers are registered:
   ```bash
   docker compose -f dev/docker-compose.yml logs worker | grep "Registered handler"
   ```

4. Check for database connection issues:
   ```sql
   SELECT * FROM pgqueuer WHERE status = 'queued';
   ```

### Tasks Failing Repeatedly

1. Check the error logs for the task
2. Verify the payload is valid JSON
3. Check if external dependencies are available
4. Review `max_retries`, backoff timing, and any task-specific terminal failure hook
5. Check `pgqueuer_log` for the final terminal exception after retries are exhausted

### Queue Building Up

1. Increase worker concurrency (`WORKER_CONCURRENCY`)
2. Scale workers horizontally (`--scale worker=N`)
3. Check for slow handlers (add timing logs)
4. Review priority settings to ensure critical tasks process first

### Worker Not Starting

1. Check database connectivity:
   ```bash
   docker compose -f dev/docker-compose.yml logs worker | grep "database"
   ```

2. Verify pgqueuer tables exist:
   ```sql
   SELECT table_name FROM information_schema.tables 
   WHERE table_name LIKE 'pgqueuer%';
   ```

3. Check health endpoint:
   ```bash
   curl http://localhost:8001/health
   ```

### Connection Errors

If you see "connection is closed" errors:

1. Verify connection pool is being used (look for "using connection pool" in logs)
2. Check pool status via ready endpoint:
   ```bash
   curl http://localhost:8001/ready
   # Should show: {"pool_size": 4, ...}
   ```
3. Ensure `DATABASE_URL` is correctly formatted
4. Check PostgreSQL max_connections setting if running many workers

## API Reference

### `TaskQueueService`

| Method | Description |
|--------|-------------|
| `initialize()` | Connect to database and setup pgqueuer schema |
| `shutdown()` | Gracefully shutdown workers and connections |
| `enqueue(task_name, payload, priority, schedule_at)` | Add a task to the queue |
| `register_handler(task_name, handler, max_retries, on_terminal_failure=None)` | Register a task handler with retry/backoff behavior |
| `start_worker(concurrency)` | Start processing tasks |

### Global Functions

| Function | Description |
|----------|-------------|
| `get_task_queue_service()` | Get the initialized service instance |
| `initialize_task_queue_service(conn_string)` | Initialize the global service |
| `shutdown_task_queue_service()` | Shutdown the global service |
