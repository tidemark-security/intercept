from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pgqueuer.errors import MaxTimeExceeded
from pgqueuer.executors import EntrypointExecutorParameters
from pgqueuer.models import Job

from app.services.task_queue_service import RetryWithTerminalFailureHookExecutor, TaskQueueService
from app.services.worker_task_runtime_config import WorkerTaskRuntimeConfig, WorkerTaskRuntimeSnapshot


class _StubSettings:
    def __init__(self, values: dict[str, object]):
        self.values = values

    async def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)


class _FakePool:
    def __init__(self, size: int = 1):
        self._size = size

    def get_size(self) -> int:
        return self._size


def _job(entrypoint: str) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=1,
        priority=0,
        created=now,
        updated=now,
        heartbeat=now,
        execute_after=now,
        status="picked",
        entrypoint=entrypoint,
        payload=b"{}",
        queue_manager_id=None,
        headers=None,
    )


def _executor_parameters(func: Any) -> EntrypointExecutorParameters:
    return EntrypointExecutorParameters(
        func=func,
        requests_per_second=float("inf"),
        retry_timer=timedelta(seconds=1),
        serialized_dispatch=False,
        concurrency_limit=0,
    )


@pytest.mark.asyncio
async def test_executor_enforces_configured_execution_timeout() -> None:
    async def slow_handler(_job: Job) -> None:
        await asyncio.sleep(0.05)

    config = WorkerTaskRuntimeConfig(
        WorkerTaskRuntimeSnapshot(default_execution_timeout_seconds=0.001)
    )
    executor = RetryWithTerminalFailureHookExecutor(
        parameters=_executor_parameters(slow_handler),
        task_runtime_config=config,
        max_attempts=1,
    )

    with pytest.raises(MaxTimeExceeded):
        await executor.execute(_job("triage_alert"), context=None)


@pytest.mark.asyncio
async def test_executor_uses_refreshed_config_on_retry() -> None:
    attempts = 0
    settings = _StubSettings({"worker.tasks.default.execution_timeout_seconds": 1})
    config = WorkerTaskRuntimeConfig(
        WorkerTaskRuntimeSnapshot(
            default_execution_timeout_seconds=0.001,
            retry_initial_delay_seconds=0,
            retry_max_delay_seconds=0,
        )
    )

    async def handler(_job: Job) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await config.refresh(settings)
            raise RuntimeError("retry me")
        await asyncio.sleep(0.01)

    executor = RetryWithTerminalFailureHookExecutor(
        parameters=_executor_parameters(handler),
        task_runtime_config=config,
        max_attempts=2,
        jitter=lambda: 0,
    )

    await executor.execute(_job("triage_alert"), context=None)

    assert attempts == 2


@pytest.mark.asyncio
async def test_refresh_task_runtime_config_only_increases_live_retry_timer() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    parameters = SimpleNamespace(retry_timer=timedelta(seconds=100))
    service._dynamic_retry_timer_parameters["triage_alert"] = parameters

    await service.refresh_task_runtime_config(
        _StubSettings(
            {
                "worker.tasks.default.execution_timeout_seconds": 10,
                "worker.tasks.retry_timer_buffer_seconds": 10,
            }
        )
    )
    assert parameters.retry_timer == timedelta(seconds=100)

    await service.refresh_task_runtime_config(
        _StubSettings(
            {
                "worker.tasks.triage_alert.execution_timeout_seconds": 200,
                "worker.tasks.retry_timer_buffer_seconds": 10,
            }
        )
    )
    assert parameters.retry_timer == timedelta(seconds=210)


@pytest.mark.asyncio
async def test_start_worker_retries_after_queue_manager_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    run_gate = asyncio.Event()
    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    class FakeQueueManager:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, *, max_concurrent_tasks: int) -> None:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("poll timeout")
            await run_gate.wait()

    class FakeSchedulerManager:
        async def run(self) -> None:
            await run_gate.wait()

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("app.services.task_queue_service.asyncio.sleep", fake_sleep)

    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    fake_queue_manager = FakeQueueManager()
    service.pgqueuer = cast(Any, SimpleNamespace(qm=fake_queue_manager, sm=FakeSchedulerManager()))

    await service.start_worker(concurrency=3)

    for _ in range(100):
        if fake_queue_manager.calls >= 2:
            break
        await real_sleep(0)

    assert fake_queue_manager.calls >= 2
    assert sleep_calls == [5]
    assert service.get_worker_readiness()[0] is False

    run_gate.set()
    await service.stop_worker()


def test_get_worker_readiness_requires_healthy_background_task() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    service.queue_manager = object()  # type: ignore[assignment]
    service.queries = object()  # type: ignore[assignment]
    service._pool = cast(Any, _FakePool())
    service._running = True
    service._last_worker_error = "poll timeout"
    service._worker_task = SimpleNamespace(done=lambda: False)  # type: ignore[assignment]

    ready, reason = service.get_worker_readiness()

    assert ready is False
    assert reason == "poll timeout"
