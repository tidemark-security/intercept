"""
Task queue service using pgqueuer for background job processing.

Provides asynchronous task execution for:
- Long-running LangFlow operations
- Background data processing
- Scheduled tasks
- In-worker retry logic with exponential backoff and terminal failure hooks
"""
import json
import logging
import asyncio
import dataclasses
import contextlib
import random
from inspect import signature
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timezone, timedelta

import asyncpg
from pgqueuer import PgQueuer
from pgqueuer.db import AsyncpgPoolDriver
from pgqueuer.errors import MaxRetriesExceeded, MaxTimeExceeded
from pgqueuer.executors import EntrypointExecutor
from pgqueuer.qm import QueueManager
from pgqueuer.queries import Queries
from pgqueuer.models import Job

from app.core.settings_registry import get_local
from app.services.worker_task_runtime_config import (
    WorkerTaskRuntimeConfig,
    WorkerTaskRuntimeSnapshot,
)

logger = logging.getLogger(__name__)


TerminalFailureHandler = Callable[..., Awaitable[None]]
TaskHandler = Callable[..., Awaitable[None]]


@dataclasses.dataclass
class RetryWithTerminalFailureHookExecutor(EntrypointExecutor):
    """Retry a job with backoff, then run a terminal failure hook once.

    Retry attempts are handled inside the running worker process. If retries are
    exhausted or a task attempt exceeds its configured execution timeout, the
    optional terminal failure hook is invoked once before the exception is
    surfaced back to pgqueuer.
    """

    on_terminal_failure: Optional[TerminalFailureHandler] = dataclasses.field(default=None)
    task_runtime_config: WorkerTaskRuntimeConfig = dataclasses.field(
        default_factory=WorkerTaskRuntimeConfig,
    )
    max_attempts: int | None = dataclasses.field(default=4)
    backoff_multiplier: float = dataclasses.field(default=2.0)
    jitter: Callable[[], float] = dataclasses.field(default=lambda: random.uniform(0, 1))

    async def execute(self, job: Job, context: Any) -> None:
        try:
            await self._execute_with_retries(job, context)
        except (MaxRetriesExceeded, MaxTimeExceeded) as exc:
            if self.on_terminal_failure is not None:
                payload: Dict[str, Any] = {}
                if job.payload:
                    payload = json.loads(job.payload.decode("utf-8"))

                try:
                    failure_signature = signature(self.on_terminal_failure)
                    if "task_id" in failure_signature.parameters:
                        await self.on_terminal_failure(payload, exc, task_id=str(job.id))
                    else:
                        await self.on_terminal_failure(payload, exc)
                except Exception:
                    logger.exception(
                        "Terminal failure hook failed for task",
                        extra={"task_id": str(job.id), "task_name": job.entrypoint},
                    )
            raise

    def exponential_delay(self, attempt: int, snapshot: WorkerTaskRuntimeSnapshot) -> float:
        delay = snapshot.retry_initial_delay_seconds * (self.backoff_multiplier**attempt) / 2
        jitter = self.jitter() * snapshot.retry_initial_delay_seconds / 2
        return delay + jitter

    async def _execute_with_retries(self, job: Job, context: Any) -> None:
        attempt = 0
        while True:
            snapshot = self.task_runtime_config.snapshot
            try:
                return await self._execute_once(job, context, snapshot)
            except MaxTimeExceeded:
                attempt += 1
                if self.max_attempts and attempt >= self.max_attempts:
                    raise
                await self._sleep_before_retry(attempt, snapshot)
            except Exception as exc:
                attempt += 1
                if self.max_attempts and attempt >= self.max_attempts:
                    raise MaxRetriesExceeded(self.max_attempts) from exc
                await self._sleep_before_retry(attempt, snapshot)

    async def _execute_once(
        self,
        job: Job,
        context: Any,
        snapshot: WorkerTaskRuntimeSnapshot,
    ) -> None:
        timeout_seconds = snapshot.execution_timeout_for(job.entrypoint)
        timeout_delta = timedelta(seconds=timeout_seconds)
        timeout_cm: asyncio.Timeout | None = None
        try:
            async with asyncio.timeout(timeout_seconds) as timeout_cm:
                await super().execute(job, context)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            if timeout_cm is not None and timeout_cm.expired():
                raise MaxTimeExceeded(timeout_delta) from exc
            raise

    async def _sleep_before_retry(
        self,
        attempt: int,
        snapshot: WorkerTaskRuntimeSnapshot,
    ) -> None:
        await asyncio.sleep(
            min(self.exponential_delay(attempt, snapshot), snapshot.retry_max_delay_seconds)
        )


class TaskQueueService:
    """
    Service for managing background task queue using pgqueuer.

    Handles:
    - Task enqueueing
    - Worker process management
    - In-worker retry/backoff policies per handler
    - Terminal failure callbacks after retry exhaustion
    - Task status tracking
    """
    
    def __init__(self, connection_string: str):
        """
        Initialize task queue service.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self._pool: Optional[asyncpg.Pool] = None
        self._connection: Optional[Any] = None  # For queries/enqueue
        self.driver: Optional[AsyncpgPoolDriver] = None
        self.pgqueuer: Optional[PgQueuer] = None
        self.queue_manager: Optional[QueueManager] = None
        self.queries: Optional[Queries] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_worker_error: Optional[str] = None
        self._handlers: Dict[str, TaskHandler] = {}
        self.task_runtime_config = WorkerTaskRuntimeConfig()
        self._dynamic_retry_timer_parameters: Dict[str, Any] = {}
        self._runtime_config_refresh_task: Optional[asyncio.Task] = None
        self.schedule_refresh_lock = asyncio.Lock()
    
    def _convert_connection_string(self, conn_str: str) -> str:
        """
        Convert SQLAlchemy connection string to asyncpg format.
        
        Args:
            conn_str: SQLAlchemy format connection string
            
        Returns:
            asyncpg compatible connection string
        """
        # Convert postgresql+asyncpg:// to postgresql://
        if conn_str.startswith("postgresql+asyncpg://"):
            return conn_str.replace("postgresql+asyncpg://", "postgresql://")
        return conn_str
    
    async def initialize(self):
        """Initialize the queue manager and database connection pool."""
        try:
            # Convert connection string for asyncpg
            asyncpg_conn_str = self._convert_connection_string(self.connection_string)
            
            # Create asyncpg connection pool for robust long-running workers
            command_timeout = float(get_local("worker.database.command_timeout_seconds"))
            self._pool = await asyncpg.create_pool(
                asyncpg_conn_str,
                min_size=2,
                max_size=10,
                command_timeout=command_timeout,
            )
            
            # Acquire a connection for schema operations and queries
            self._connection = await self._pool.acquire()
            
            # Create database driver with the pool (handles reconnection automatically)
            self.driver = AsyncpgPoolDriver(self._pool)
            self.pgqueuer = PgQueuer.from_asyncpg_pool(self._pool)
            
            # Create Queries instance for database operations
            self.queries = Queries.from_asyncpg_pool(self._pool)
            
            # Check if pgqueuer is already installed
            if await self.queries.has_table("pgqueuer"):
                # Run upgrade to ensure schema is up to date
                await self.queries.upgrade()
                logger.info("pgqueuer schema upgraded")
            else:
                # Fresh install
                await self.queries.install()
                logger.info("pgqueuer schema installed")
            
            # Initialize queue manager
            self.queue_manager = self.pgqueuer.qm
            
            logger.info(
                "Task queue service initialized successfully (using connection pool, command_timeout=%ss)",
                command_timeout,
            )
        except Exception as e:
            logger.error(f"Failed to initialize task queue service: {e}")
            raise
    
    async def shutdown(self):
        """Shutdown the queue manager and cleanup resources."""
        try:
            self._running = False
            
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass

            await self._stop_runtime_config_refresh()
            
            # Release connection back to pool before closing
            if self._connection and self._pool:
                try:
                    await self._pool.release(self._connection)
                except Exception:
                    pass  # Connection may already be released
                self._connection = None
            
            # Close the connection pool
            if self._pool:
                await self._pool.close()
                self._pool = None
            
            logger.info("Task queue service shut down successfully")
        except Exception as e:
            logger.error(f"Error shutting down task queue service: {e}")
    
    async def enqueue(
        self,
        task_name: str,
        payload: Dict[str, Any],
        priority: int = 0,
        schedule_at: Optional[datetime] = None,
        dedupe_key: Optional[str] = None,
    ) -> str:
        """
        Enqueue a background task.
        
        Args:
            task_name: Name/type of the task to execute
            payload: Task data/parameters
            priority: Task priority (higher = more important)
            schedule_at: Optional scheduled execution time
            dedupe_key: Optional deduplication key for queued/picked jobs
            
        Returns:
            Task ID
            
        Raises:
            RuntimeError: If queue manager not initialized
        """
        if not self.queries:
            raise RuntimeError("Task queue not initialized")
        
        try:
            # Serialize payload to bytes
            payload_bytes = json.dumps(payload).encode('utf-8')
            
            # Calculate execute_after if schedule_at is provided
            execute_after = None
            if schedule_at:
                now = datetime.now(timezone.utc)
                if schedule_at > now:
                    execute_after = schedule_at - now
            
            # Enqueue job using Queries
            job_ids = await self.queries.enqueue(
                entrypoint=task_name,
                payload=payload_bytes,
                priority=priority,
                execute_after=execute_after,
                dedupe_key=dedupe_key,
            )
            
            job_id = job_ids[0] if job_ids else None
            
            logger.info(
                f"Enqueued task: {task_name}",
                extra={
                    "task_id": str(job_id),
                    "task_name": task_name,
                    "priority": priority,
                    "dedupe_key": dedupe_key,
                }
            )
            
            return str(job_id) if job_id else ""
            
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_name}: {e}")
            raise
    
    def register_handler(
        self,
        task_name: str,
        handler: TaskHandler,
        max_retries: int = 3,
        on_terminal_failure: Optional[TerminalFailureHandler] = None,
        retry_timer: Optional[timedelta] = None,
    ):
        """
        Register a handler for a task type.

        Args:
            task_name: Name/type of task to handle
            handler: Async function to process the task
            max_retries: Number of retries after the initial attempt
            on_terminal_failure: Optional callback invoked once after retries are
                exhausted or the execution timeout is exceeded
            retry_timer: pgqueuer lease duration — jobs still in "picked" state
                after this long without heartbeats are assumed dead and
                re-enqueued. Defaults to the configured execution timeout plus
                worker.tasks.retry_timer_buffer_seconds.
        """
        if not self.pgqueuer:
            raise RuntimeError("Task queue not initialized")
        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")

        effective_retry_timer = (
            retry_timer
            if retry_timer is not None
            else self.task_runtime_config.snapshot.retry_timer_for(task_name)
        )

        # Store handler info for later use
        self._handlers[task_name] = handler
        handler_signature = signature(handler)
        accepts_task_id = "task_id" in handler_signature.parameters
        def build_executor(parameters: Any) -> RetryWithTerminalFailureHookExecutor:
            if retry_timer is None:
                self._dynamic_retry_timer_parameters[task_name] = parameters
            return RetryWithTerminalFailureHookExecutor(
                parameters=parameters,
                on_terminal_failure=on_terminal_failure,
                max_attempts=max_retries + 1,
                task_runtime_config=self.task_runtime_config,
            )

        # Create a handler that parses JSON payload and register with entrypoint decorator
        @self.pgqueuer.entrypoint(
            task_name,
            retry_timer=effective_retry_timer,
            executor_factory=build_executor,
        )
        async def entrypoint_handler(job: Job):
            """Wrapper to handle retries and logging."""
            try:
                # Parse the JSON payload
                payload = {}
                if job.payload:
                    payload = json.loads(job.payload.decode('utf-8'))
                
                logger.info(
                    f"Processing task: {task_name}",
                    extra={
                        "task_id": str(job.id),
                        "task_name": task_name,
                    }
                )
                
                # Execute handler
                if accepts_task_id:
                    await handler(payload, task_id=str(job.id))
                else:
                    await handler(payload)
                
                logger.info(
                    f"Completed task: {task_name}",
                    extra={
                        "task_id": str(job.id),
                        "task_name": task_name,
                    }
                )
                
            except Exception as e:
                logger.error(
                    f"Task failed: {task_name}",
                    extra={
                        "task_id": str(job.id),
                        "task_name": task_name,
                        "error": str(e),
                    }
                )
                raise  # Re-raise so the executor can retry or surface terminal failure
        
        logger.info(
            "Registered handler for task: %s (execution_timeout=%ss, retry_timer=%s)",
            task_name,
            self.task_runtime_config.snapshot.execution_timeout_for(task_name),
            effective_retry_timer,
        )

    async def refresh_task_runtime_config(self, settings: Any) -> bool:
        """Refresh task timeout settings and conservatively update live leases."""
        changed = await self.task_runtime_config.refresh(settings)
        snapshot = self.task_runtime_config.snapshot
        self._apply_runtime_retry_timers(snapshot)
        if changed:
            logger.info(
                "Worker task runtime config refreshed",
                extra={
                    "default_execution_timeout_seconds": snapshot.default_execution_timeout_seconds,
                    "task_execution_timeout_seconds": dict(snapshot.task_execution_timeout_seconds),
                    "retry_timer_buffer_seconds": snapshot.retry_timer_buffer_seconds,
                    "refresh_interval_seconds": snapshot.refresh_interval_seconds,
                },
            )
        return changed

    def _apply_runtime_retry_timers(self, snapshot: WorkerTaskRuntimeSnapshot) -> None:
        for task_name, parameters in self._dynamic_retry_timer_parameters.items():
            desired_retry_timer = snapshot.retry_timer_for(task_name)
            if desired_retry_timer > parameters.retry_timer:
                logger.info(
                    "Increasing pgqueuer retry lease for task %s from %s to %s",
                    task_name,
                    parameters.retry_timer,
                    desired_retry_timer,
                )
                parameters.retry_timer = desired_retry_timer

    async def _start_runtime_config_refresh(self) -> None:
        if self._runtime_config_refresh_task and not self._runtime_config_refresh_task.done():
            return

        self._runtime_config_refresh_task = asyncio.create_task(
            self._runtime_config_refresh_loop(),
            name="worker-task-runtime-config-refresh",
        )

    async def _stop_runtime_config_refresh(self) -> None:
        if not self._runtime_config_refresh_task:
            return

        if not self._runtime_config_refresh_task.done():
            self._runtime_config_refresh_task.cancel()
            try:
                await self._runtime_config_refresh_task
            except asyncio.CancelledError:
                pass
        self._runtime_config_refresh_task = None

    async def _runtime_config_refresh_loop(self) -> None:
        while self._running:
            try:
                from app.core.database import async_session_factory
                from app.services.settings_service import SettingsService

                async with async_session_factory() as db:
                    await self.refresh_task_runtime_config(SettingsService(db))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to refresh worker task runtime config")

            await asyncio.sleep(self.task_runtime_config.snapshot.refresh_interval_seconds)
    
    async def start_worker(self, concurrency: int = 10):
        """
        Start the background worker process.
        
        Args:
            concurrency: Number of concurrent tasks to process
        """
        if not self.pgqueuer:
            raise RuntimeError("Task queue not initialized")
        
        if self._running:
            logger.warning("Worker already running")
            return
        
        self._running = True
        self._last_worker_error = None
        if self.queries is not None and self._pool is not None:
            await self._start_runtime_config_refresh()
        
        async def worker_loop():
            """Main worker loop."""
            try:
                logger.info(f"Starting task queue worker (max_concurrent_tasks={concurrency})")
                if self.pgqueuer is None:
                    raise RuntimeError("Task queue not initialized")
                
                while self._running:
                    try:
                        self._last_worker_error = None
                        await self._run_pgqueuer_services(concurrency=concurrency)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        self._last_worker_error = str(e) or e.__class__.__name__
                        logger.exception("Worker error: %s", e)
                        if not self._running:
                            break
                        await asyncio.sleep(5)  # Brief pause before retry
                
                logger.info("Task queue worker stopped")
                
            except asyncio.CancelledError:
                logger.info("Task queue worker cancelled")
        
        # Start worker in background
        self._worker_task = asyncio.create_task(worker_loop())

    async def _run_pgqueuer_services(self, concurrency: int) -> None:
        if self.pgqueuer is None:
            raise RuntimeError("Task queue not initialized")

        queue_manager_task = asyncio.create_task(
            self.pgqueuer.qm.run(max_concurrent_tasks=concurrency),
            name="pgqueuer-queue-manager",
        )
        scheduler_manager_task = asyncio.create_task(
            self.pgqueuer.sm.run(),
            name="pgqueuer-scheduler-manager",
        )
        tasks = {queue_manager_task, scheduler_manager_task}

        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

            for task in done:
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc is not None:
                    raise exc

            if pending:
                completed_task = next(iter(done))
                raise RuntimeError(f"{completed_task.get_name()} stopped unexpectedly")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)

    def get_worker_readiness(self) -> tuple[bool, str]:
        if not self.queue_manager or not self.queries or not self._pool:
            return False, "task queue not initialized"

        if not self._running or self._worker_task is None:
            return False, "worker loop not started"

        if self._worker_task.done():
            try:
                worker_error = self._worker_task.exception()
            except asyncio.CancelledError:
                worker_error = None

            if worker_error is not None:
                return False, str(worker_error) or worker_error.__class__.__name__
            return False, "worker loop stopped"

        if self._last_worker_error:
            return False, self._last_worker_error

        try:
            if self._pool.get_size() <= 0:
                return False, "database pool not ready"
        except Exception as exc:
            return False, str(exc) or exc.__class__.__name__

        return True, ""

    def get_pool_size(self) -> int:
        if not self._pool:
            return 0
        return self._pool.get_size()
    
    async def stop_worker(self):
        """Stop the background worker process."""
        self._running = False
        
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        await self._stop_runtime_config_refresh()
        
        logger.info("Task queue worker stopped")


# Global task queue service instance
_task_queue_service: Optional[TaskQueueService] = None


def get_task_queue_service() -> TaskQueueService:
    """
    Get the global task queue service instance.
    
    Returns:
        TaskQueueService instance
        
    Raises:
        RuntimeError: If service not initialized
    """
    if _task_queue_service is None:
        raise RuntimeError(
            "Task queue service not initialized. "
            "Call initialize_task_queue_service() first."
        )
    return _task_queue_service


async def initialize_task_queue_service(connection_string: str) -> TaskQueueService:
    """
    Initialize the global task queue service.
    
    Args:
        connection_string: PostgreSQL connection string
        
    Returns:
        Initialized TaskQueueService
    """
    global _task_queue_service
    
    _task_queue_service = TaskQueueService(connection_string)
    await _task_queue_service.initialize()
    
    return _task_queue_service


async def shutdown_task_queue_service():
    """Shutdown the global task queue service."""
    global _task_queue_service
    
    if _task_queue_service:
        await _task_queue_service.shutdown()
        _task_queue_service = None
