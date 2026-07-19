#!/usr/bin/env python3
"""
Standalone pgqueuer worker with health checks and metrics.

This worker runs as a separate container from the FastAPI application,
processing background tasks from the PostgreSQL queue.

Usage:
    python worker.py

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (required)
    WORKER_CONCURRENCY: Number of concurrent tasks (default: 20)
    HEALTH_PORT: Port for health/metrics server (default: 8001)
    WORKER_ID: Optional worker identifier (default: hostname)
"""
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from aiohttp import web

# Configure logging before imports
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import app modules after logging is configured
from app.core.settings_registry import get_local
from app.core.database import async_session_factory
from app.core.security import initialize_encryption_service
from app.services.enrichment.providers import register_providers
from app.services.enrichment.bulk_sync_schedule_sync import sync_bulk_sync_schedules
from app.services.maxmind_service import maxmind_service
from app.services.task_queue_service import (
    initialize_task_queue_service,
    shutdown_task_queue_service,
    get_task_queue_service,
)
from app.services.tasks import register_task_handlers


def _resolve_worker_id() -> str:
    """Return the explicit worker ID, hostname fallback, or final default."""
    return os.getenv("WORKER_ID") or os.getenv("HOSTNAME") or "worker-unknown"


def _escape_prometheus_label(value: str) -> str:
    """Escape a label value according to Prometheus text exposition rules."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


# Global metrics
class WorkerMetrics:
    """Track worker metrics for monitoring."""
    
    def __init__(self) -> None:
        self.started_at: Optional[datetime] = None
        self.worker_id: str = _resolve_worker_id()
    
    def uptime_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()


METRICS = WorkerMetrics()


class WorkerHealthServer:
    """
    Simple HTTP server for health checks and Prometheus metrics.
    
    Endpoints:
        GET /health - Liveness probe (is the process alive?)
        GET /ready  - Readiness probe (is the worker ready to process?)
        GET /metrics - Prometheus-format metrics
    """
    
    def __init__(self, port: int = 8001) -> None:
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/ready", self.ready)
        self.app.router.add_get("/metrics", self.metrics)
        self.runner: Optional[web.AppRunner] = None
    
    async def health(self, _request: web.Request) -> web.Response:
        """
        Liveness probe - is the worker process alive?
        
        Returns 200 if the process is running.
        Used by container orchestrators to detect crashed workers.
        """
        return web.json_response({
            "status": "healthy",
            "worker_id": METRICS.worker_id,
            "uptime_seconds": METRICS.uptime_seconds(),
        })
    
    async def ready(self, _request: web.Request) -> web.Response:
        """
        Readiness probe - is the worker ready to process tasks?
        
        Returns 200 if connected to database and queue manager is running.
        Used by load balancers to know when to route traffic.
        """
        try:
            service = get_task_queue_service()

            ready, reason = service.get_worker_readiness()
            if ready:
                return web.json_response({
                    "status": "ready",
                    "worker_id": METRICS.worker_id,
                    "pool_size": service.get_pool_size(),
                })

            logger.debug("Worker readiness unavailable: %s", reason)
            return web.json_response(
                {
                    "status": "not ready",
                    "worker_id": METRICS.worker_id,
                    "reason": "worker unavailable",
                },
                status=503,
            )
        except RuntimeError:
            logger.debug("Worker readiness requested before queue initialization")
        except Exception as e:
            logger.warning("Readiness check failed: %s", e)
        
        return web.json_response(
            {
                "status": "not ready",
                "worker_id": METRICS.worker_id,
                "reason": "worker unavailable",
            },
            status=503
        )
    
    async def metrics(self, _request: web.Request) -> web.Response:
        """
        Prometheus-format metrics endpoint.
        
        Exposes:
            - worker_uptime_seconds: How long the worker has been running
            - worker_queue_size: Current number of pending jobs
            - worker_info: Worker metadata (labels)
        """
        queue_size = 0
        
        try:
            service = get_task_queue_service()
            if service.queries:
                result = await service.queries.queue_size()
                queue_size = result if result else 0
        except Exception as exc:
            logger.debug("Could not get queue size: %s", exc)
        
        # Build Prometheus-format output
        lines = [
            "# HELP worker_info Worker information",
            "# TYPE worker_info gauge",
            f'worker_info{{worker_id="{_escape_prometheus_label(METRICS.worker_id)}"}} 1',
            "",
            "# HELP worker_uptime_seconds Worker uptime in seconds",
            "# TYPE worker_uptime_seconds gauge",
            f"worker_uptime_seconds {METRICS.uptime_seconds():.2f}",
            "",
            "# HELP worker_queue_size Current number of pending jobs in the queue",
            "# TYPE worker_queue_size gauge",
            f"worker_queue_size {queue_size}",
            "",
        ]
        
        return web.Response(
            text="\n".join(lines),
            content_type="text/plain",
            charset="utf-8",
        )
    
    async def start(self) -> None:
        """Start the health server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("Health server running on http://0.0.0.0:%s", self.port)
        logger.info("  - GET /health  (liveness probe)")
        logger.info("  - GET /ready   (readiness probe)")
        logger.info("  - GET /metrics (Prometheus metrics)")
    
    async def stop(self) -> None:
        """Stop the health server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health server stopped")


async def _wait_for_shutdown_or_worker_failure(
    stop_event: asyncio.Event,
    worker_task: asyncio.Task[None],
) -> None:
    """Wait for shutdown while surfacing a failed queue worker to the process."""
    shutdown_task = asyncio.create_task(stop_event.wait(), name="worker-shutdown-wait")
    try:
        done, _ = await asyncio.wait(
            {shutdown_task, worker_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if worker_task in done:
            await worker_task
    finally:
        if not shutdown_task.done():
            shutdown_task.cancel()
            try:
                await shutdown_task
            except asyncio.CancelledError:
                pass


async def run_worker() -> None:
    """
    Main worker entry point.
    
    1. Starts health server for container orchestration
    2. Initializes database connection
    3. Registers task handlers
    4. Runs the queue manager until shutdown signal
    """
    # Configuration from environment
    concurrency = int(get_local("worker.concurrency"))
    health_port = int(get_local("worker.health_port"))
    
    METRICS.started_at = datetime.now(timezone.utc)
    METRICS.worker_id = _resolve_worker_id()
    
    logger.info("=" * 60)
    logger.info("Starting pgqueuer worker")
    logger.info("  Worker ID:    %s", METRICS.worker_id)
    logger.info("  Concurrency:  %s", concurrency)
    logger.info("  Health Port:  %s", health_port)
    logger.info("=" * 60)
    
    # Start health server first (so container shows as starting)
    health_server = WorkerHealthServer(port=health_port)
    await health_server.start()
    
    try:
        # Initialize encryption service (needed for some operations)
        logger.info("Initializing encryption service...")
        initialize_encryption_service(get_local("secret_key").encode())
        
        # Initialize task queue service
        logger.info("Connecting to task queue...")
        service = await initialize_task_queue_service(get_local("database.url"))

        register_providers()
        
        # Register all task handlers
        logger.info("Registering task handlers...")
        await register_task_handlers()

        logger.info("Syncing bulk sync schedules...")
        async with async_session_factory() as db:
            await sync_bulk_sync_schedules(db)
        
        # Start processing jobs
        logger.info("Starting job processing (concurrency=%s)...", concurrency)
        worker_task = await service.start_worker(concurrency=concurrency)
        
        logger.info("✅ Worker is ready and processing tasks")
        
        # Set up graceful shutdown
        stop_event = asyncio.Event()
        
        def handle_shutdown_signal() -> None:
            logger.info("Shutdown signal received, stopping gracefully...")
            stop_event.set()
        
        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_shutdown_signal)
        
        # Wait until shutdown signal
        await _wait_for_shutdown_or_worker_failure(stop_event, worker_task)
        
    except Exception:
        logger.exception("Worker failed to start")
        raise
    
    finally:
        # Cleanup
        logger.info("Shutting down worker...")
        
        try:
            await shutdown_task_queue_service()
        except Exception:
            logger.exception("Error during task queue shutdown")

        try:
            await maxmind_service.close_readers()
        except Exception:
            logger.exception("Error closing MaxMind readers")

        try:
            await health_server.stop()
        except Exception:
            logger.exception("Error stopping health server")
        
        logger.info("Worker stopped")


def main() -> None:
    """Entry point for the worker process."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception:
        logger.exception("Worker crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
