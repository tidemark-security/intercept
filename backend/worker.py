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
import signal
import os
from datetime import datetime, timezone
from typing import Optional

from aiohttp import web

# Configure logging before imports
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import app modules after logging is configured
from app.core.settings_registry import get_local
from app.core.security import initialize_encryption_service
from app.services.enrichment.providers import register_providers
from app.services.task_queue_service import (
    initialize_task_queue_service,
    shutdown_task_queue_service,
    get_task_queue_service,
)
from app.services.tasks import register_task_handlers


# Global metrics
class WorkerMetrics:
    """Track worker metrics for monitoring."""
    
    def __init__(self):
        self.started_at: Optional[datetime] = None
        self.tasks_processed: int = 0
        self.tasks_failed: int = 0
        self.last_task_at: Optional[datetime] = None
        self.worker_id: str = os.getenv("HOSTNAME", os.getenv("WORKER_ID", "worker-unknown"))
    
    def record_success(self):
        self.tasks_processed += 1
        self.last_task_at = datetime.now(timezone.utc)
    
    def record_failure(self):
        self.tasks_failed += 1
        self.last_task_at = datetime.now(timezone.utc)
    
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
    
    def __init__(self, port: int = 8001):
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/ready", self.ready)
        self.app.router.add_get("/metrics", self.metrics)
        self.runner: Optional[web.AppRunner] = None
    
    async def health(self, request: web.Request) -> web.Response:
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
    
    async def ready(self, request: web.Request) -> web.Response:
        """
        Readiness probe - is the worker ready to process tasks?
        
        Returns 200 if connected to database and queue manager is running.
        Used by load balancers to know when to route traffic.
        """
        try:
            service = get_task_queue_service()
            
            # Check if queue manager and pool are valid
            if service.queue_manager and service._pool:
                # Check pool health by getting size
                pool_size = service._pool.get_size()
                if pool_size > 0:
                    return web.json_response({
                        "status": "ready",
                        "worker_id": METRICS.worker_id,
                        "pool_size": pool_size,
                    })
        except RuntimeError:
            pass
        except Exception as e:
            logger.warning(f"Readiness check failed: {e}")
        
        return web.json_response(
            {"status": "not ready", "worker_id": METRICS.worker_id},
            status=503
        )
    
    async def metrics(self, request: web.Request) -> web.Response:
        """
        Prometheus-format metrics endpoint.
        
        Exposes:
            - worker_uptime_seconds: How long the worker has been running
            - worker_tasks_processed_total: Counter of successful tasks
            - worker_tasks_failed_total: Counter of failed tasks
            - worker_queue_size: Current number of pending jobs
            - worker_info: Worker metadata (labels)
        """
        queue_size = 0
        
        try:
            service = get_task_queue_service()
            if service.queries:
                result = await service.queries.queue_size()
                queue_size = result if result else 0
        except Exception as e:
            logger.debug(f"Could not get queue size: {e}")
        
        # Build Prometheus-format output
        lines = [
            "# HELP worker_info Worker information",
            "# TYPE worker_info gauge",
            f'worker_info{{worker_id="{METRICS.worker_id}"}} 1',
            "",
            "# HELP worker_uptime_seconds Worker uptime in seconds",
            "# TYPE worker_uptime_seconds gauge",
            f"worker_uptime_seconds {METRICS.uptime_seconds():.2f}",
            "",
            "# HELP worker_tasks_processed_total Total number of tasks processed successfully",
            "# TYPE worker_tasks_processed_total counter",
            f"worker_tasks_processed_total {METRICS.tasks_processed}",
            "",
            "# HELP worker_tasks_failed_total Total number of tasks that failed",
            "# TYPE worker_tasks_failed_total counter",
            f"worker_tasks_failed_total {METRICS.tasks_failed}",
            "",
            "# HELP worker_queue_size Current number of pending jobs in the queue",
            "# TYPE worker_queue_size gauge",
            f"worker_queue_size {queue_size}",
            "",
        ]
        
        # Add last task timestamp if available
        if METRICS.last_task_at:
            lines.extend([
                "# HELP worker_last_task_timestamp_seconds Unix timestamp of last processed task",
                "# TYPE worker_last_task_timestamp_seconds gauge",
                f"worker_last_task_timestamp_seconds {METRICS.last_task_at.timestamp():.0f}",
                "",
            ])
        
        return web.Response(
            text="\n".join(lines),
            content_type="text/plain",
            charset="utf-8",
        )
    
    async def start(self):
        """Start the health server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"Health server running on http://0.0.0.0:{self.port}")
        logger.info(f"  - GET /health  (liveness probe)")
        logger.info(f"  - GET /ready   (readiness probe)")
        logger.info(f"  - GET /metrics (Prometheus metrics)")
    
    async def stop(self):
        """Stop the health server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health server stopped")


async def run_worker():
    """
    Main worker entry point.
    
    1. Starts health server for container orchestration
    2. Initializes database connection
    3. Registers task handlers
    4. Runs the queue manager until shutdown signal
    """
    # Configuration from environment
    concurrency = int(os.getenv("WORKER_CONCURRENCY", "20"))
    health_port = int(os.getenv("HEALTH_PORT", "8001"))
    
    METRICS.started_at = datetime.now(timezone.utc)
    METRICS.worker_id = os.getenv("HOSTNAME", os.getenv("WORKER_ID", "worker-unknown"))
    
    logger.info("=" * 60)
    logger.info(f"Starting pgqueuer worker")
    logger.info(f"  Worker ID:    {METRICS.worker_id}")
    logger.info(f"  Concurrency:  {concurrency}")
    logger.info(f"  Health Port:  {health_port}")
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
        register_task_handlers()
        
        # Start processing jobs
        logger.info(f"Starting job processing (concurrency={concurrency})...")
        await service.start_worker(concurrency=concurrency)
        
        logger.info("✅ Worker is ready and processing tasks")
        
        # Set up graceful shutdown
        stop_event = asyncio.Event()
        
        def handle_shutdown_signal():
            logger.info("Shutdown signal received, stopping gracefully...")
            stop_event.set()
        
        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_shutdown_signal)
        
        # Wait until shutdown signal
        await stop_event.wait()
        
    except Exception as e:
        logger.error(f"Worker failed to start: {e}", exc_info=True)
        raise
    
    finally:
        # Cleanup
        logger.info("Shutting down worker...")
        
        try:
            await shutdown_task_queue_service()
        except Exception as e:
            logger.warning(f"Error during task queue shutdown: {e}")
        
        await health_server.stop()
        
        logger.info(f"Worker stopped. Processed {METRICS.tasks_processed} tasks, {METRICS.tasks_failed} failures.")


def main():
    """Entry point for the worker process."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
