# Task Queue System

Intercept uses **pgqueuer** for background job processing, leveraging PostgreSQL as the job queue backend. This provides reliable, transactional task execution without requiring additional infrastructure like Redis or RabbitMQ.

## Overview

The task queue system enables:

- **Asynchronous task execution** - Offload long-running operations from HTTP requests
- **Scheduled tasks** - Execute tasks at a specified future time
- **Automatic retries** - Failed tasks are retried with configurable backoff
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

Workers run as a separate service in docker-compose.yml:

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
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `WORKER_ID` | hostname | Identifier for metrics/logging |
| `SECRET_KEY` | required | Encryption key (same as backend) |

### Scaling Workers

Scale horizontally by running multiple worker containers:

```bash
# Docker Compose
docker-compose up -d --scale worker=3

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
# Worker uptime
worker_uptime_seconds 3600.00

# Task counters
worker_tasks_processed_total 1542
worker_tasks_failed_total 23

# Queue status
worker_queue_size 15

# Last activity
worker_last_task_timestamp_seconds 1703875200
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
- **Command timeout**: 60 seconds
- **Auto-reconnection**: Pool handles connection failures automatically

This prevents "connection is closed" errors that occur with single connections in long-running worker processes.

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

def register_task_handlers():
    """Register all task handlers during app startup."""
    task_queue = get_task_queue_service()
    
    task_queue.register_handler(
        task_name="my_task",
        handler=handle_my_task,
        max_retries=3,  # Retry up to 3 times on failure
    )
```

This is called automatically in `main.py`:

```python
# In app/main.py lifespan
await initialize_task_queue_service(get_local("database.url"))
register_task_handlers()
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

## Error Handling & Retries

When a task handler raises an exception:

1. The error is logged with task details
2. pgqueuer automatically schedules a retry based on `retry_timer` (default: 5 seconds)
3. Retries continue until `max_retries` is exhausted
4. Failed tasks remain in the queue for inspection

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
        # Log but don't retry for validation errors
        logger.error(f"Validation failed: {e}")
        # Don't re-raise - task completes (with failure logged)
```

## Monitoring

### Logging

All task operations are logged:

```
INFO - Enqueued task: langflow_chat (task_id=123, priority=0)
INFO - Processing task: langflow_chat (task_id=123)
INFO - Completed task: langflow_chat (task_id=123)
ERROR - Task failed: langflow_chat (task_id=123, error=...)
```

### Database Queries

Check queue status directly in PostgreSQL:

```sql
-- View pending jobs
SELECT * FROM pgqueuer WHERE status = 'queued' ORDER BY priority DESC, created_at;

-- View recent job history
SELECT * FROM pgqueuer_log ORDER BY created_at DESC LIMIT 100;

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
docker-compose up -d worker

# View worker logs
docker-compose logs -f worker

# Scale to multiple workers
docker-compose up -d --scale worker=3
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

Set reasonable timeouts for external operations:

```python
async def handle_external_call(payload: Dict[str, Any]):
    async with asyncio.timeout(30):  # 30 second timeout
        await external_service.call(payload["data"])
```

## Troubleshooting

### Tasks Not Processing

1. Check if workers are running:
   ```bash
   docker-compose ps worker
   docker-compose logs worker --tail=50
   ```

2. Check worker readiness:
   ```bash
   curl http://localhost:8001/ready
   ```

3. Verify handlers are registered:
   ```bash
   docker-compose logs worker | grep "Registered handler"
   ```

4. Check for database connection issues:
   ```sql
   SELECT * FROM pgqueuer WHERE status = 'queued';
   ```

### Tasks Failing Repeatedly

1. Check the error logs for the task
2. Verify the payload is valid JSON
3. Check if external dependencies are available
4. Review retry count vs max_retries setting

### Queue Building Up

1. Increase worker concurrency (`WORKER_CONCURRENCY`)
2. Scale workers horizontally (`--scale worker=N`)
3. Check for slow handlers (add timing logs)
4. Review priority settings to ensure critical tasks process first

### Worker Not Starting

1. Check database connectivity:
   ```bash
   docker-compose logs worker | grep "database"
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
| `register_handler(task_name, handler, max_retries)` | Register a task handler |
| `start_worker(concurrency)` | Start processing tasks |
| `stop_worker()` | Stop processing tasks |

### Global Functions

| Function | Description |
|----------|-------------|
| `get_task_queue_service()` | Get the initialized service instance |
| `initialize_task_queue_service(conn_string)` | Initialize the global service |
| `shutdown_task_queue_service()` | Shutdown the global service |
