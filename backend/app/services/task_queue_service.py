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
from inspect import signature
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timezone, timedelta

import asyncpg
from pgqueuer import PgQueuer
from pgqueuer.db import AsyncpgDriver, AsyncpgPoolDriver
from pgqueuer.errors import MaxRetriesExceeded, MaxTimeExceeded
from pgqueuer.executors import RetryWithBackoffEntrypointExecutor
from pgqueuer.qm import QueueManager
from pgqueuer.queries import Queries
from pgqueuer.models import Job

logger = logging.getLogger(__name__)


TerminalFailureHandler = Callable[..., Awaitable[None]]
TaskHandler = Callable[..., Awaitable[None]]

RETRY_INITIAL_DELAY_SECONDS = 5.0
RETRY_MAX_DELAY = timedelta(seconds=60)
RETRY_MAX_TIME = timedelta(minutes=10)


@dataclasses.dataclass
class RetryWithTerminalFailureHookExecutor(RetryWithBackoffEntrypointExecutor):
    """Retry a job with backoff, then run a terminal failure hook once.

    Retry attempts are handled inside the running worker process. If retries are
    exhausted or the total retry window is exceeded, the optional terminal
    failure hook is invoked once before the exception is surfaced back to
    pgqueuer.
    """

    on_terminal_failure: Optional[TerminalFailureHandler] = dataclasses.field(default=None)

    async def execute(self, job: Job, context: Any) -> None:
        try:
            await super().execute(job, context)
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
        self._handlers: Dict[str, TaskHandler] = {}
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
            self._pool = await asyncpg.create_pool(
                asyncpg_conn_str,
                min_size=2,
                max_size=10,
                command_timeout=60,
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
            
            logger.info("Task queue service initialized successfully (using connection pool)")
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
    ):
        """
        Register a handler for a task type.
        
        Args:
            task_name: Name/type of task to handle
            handler: Async function to process the task
            max_retries: Number of retries after the initial attempt
            on_terminal_failure: Optional callback invoked once after retries are
                exhausted or the retry time limit is exceeded
        """
        if not self.pgqueuer:
            raise RuntimeError("Task queue not initialized")
        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")
        
        # Store handler info for later use
        self._handlers[task_name] = handler
        handler_signature = signature(handler)
        accepts_task_id = "task_id" in handler_signature.parameters
        def build_executor(parameters: Any) -> RetryWithTerminalFailureHookExecutor:
            return RetryWithTerminalFailureHookExecutor(
                parameters=parameters,
                on_terminal_failure=on_terminal_failure,
                max_attempts=max_retries + 1,
                initial_delay=RETRY_INITIAL_DELAY_SECONDS,
                max_delay=RETRY_MAX_DELAY,
                max_time=RETRY_MAX_TIME,
            )
        
        # Create a handler that parses JSON payload and register with entrypoint decorator
        @self.pgqueuer.entrypoint(
            task_name,
            retry_timer=timedelta(seconds=5),  # Base retry timer
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
        
        logger.info(f"Registered handler for task: {task_name}")
    
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
        
        async def worker_loop():
            """Main worker loop."""
            try:
                logger.info(f"Starting task queue worker (max_concurrent_tasks={concurrency})")
                pgqueuer = self.pgqueuer
                if pgqueuer is None:
                    raise RuntimeError("Task queue not initialized")
                
                while self._running:
                    try:
                        await pgqueuer.run(max_concurrent_tasks=concurrency)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Worker error: {e}")
                        await asyncio.sleep(5)  # Brief pause before retry
                
                logger.info("Task queue worker stopped")
                
            except asyncio.CancelledError:
                logger.info("Task queue worker cancelled")
        
        # Start worker in background
        self._worker_task = asyncio.create_task(worker_loop())
    
    async def stop_worker(self):
        """Stop the background worker process."""
        self._running = False
        
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
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
