from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pgqueuer.errors import DuplicateJobError, MaxRetriesExceeded, MaxTimeExceeded
from pgqueuer.executors import EntrypointExecutorParameters
from pgqueuer.models import Job

from app.services import task_queue_service as task_queue_module
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


class _FailingTask:
    def __init__(self, error_message: str) -> None:
        self.cancelled = False
        self.error_message = error_message

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.cancelled = True

    def __await__(self):
        async def fail() -> None:
            raise RuntimeError(self.error_message)

        return fail().__await__()


def _job(entrypoint: str, *, payload: bytes = b"{}") -> Job:
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
        payload=payload,
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
async def test_enqueue_returns_existing_job_id_for_dedupe_conflict() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    driver = SimpleNamespace(fetch=AsyncMock(return_value=[{"id": 73}]))
    service.queries = SimpleNamespace(
        enqueue=AsyncMock(side_effect=DuplicateJobError(["enrich_item:alert:1:item-1"])),
        driver=driver,
        qbe=SimpleNamespace(settings=SimpleNamespace(queue_table="pgqueuer")),
    )

    task_id = await service.enqueue(
        task_name="enrich_item",
        payload={"entity_type": "alert", "entity_id": 1, "item_id": "item-1"},
        dedupe_key="enrich_item:alert:1:item-1",
    )

    assert task_id == "73"
    driver.fetch.assert_awaited_once()
    assert driver.fetch.await_args.args[1:] == (
        "enrich_item",
        "enrich_item:alert:1:item-1",
    )


@pytest.mark.asyncio
async def test_enqueue_retries_once_when_conflicting_job_has_finished() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    enqueue = AsyncMock(
        side_effect=[
            DuplicateJobError(["enrich_item:alert:1:item-1"]),
            [91],
        ]
    )
    service.queries = SimpleNamespace(
        enqueue=enqueue,
        driver=SimpleNamespace(fetch=AsyncMock(return_value=[])),
        qbe=SimpleNamespace(settings=SimpleNamespace(queue_table="pgqueuer")),
    )

    task_id = await service.enqueue(
        task_name="enrich_item",
        payload={"entity_type": "alert", "entity_id": 1, "item_id": "item-1"},
        dedupe_key="enrich_item:alert:1:item-1",
    )

    assert task_id == "91"
    assert enqueue.await_count == 2


@pytest.mark.asyncio
async def test_enqueue_surfaces_second_vanished_dedupe_conflict() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    duplicate = DuplicateJobError(["enrich_item:alert:1:item-1"])
    enqueue = AsyncMock(side_effect=[duplicate, duplicate])
    service.queries = SimpleNamespace(
        enqueue=enqueue,
        driver=SimpleNamespace(fetch=AsyncMock(return_value=[])),
        qbe=SimpleNamespace(settings=SimpleNamespace(queue_table="pgqueuer")),
    )

    with pytest.raises(DuplicateJobError):
        await service.enqueue(
            task_name="enrich_item",
            payload={"entity_type": "alert", "entity_id": 1, "item_id": "item-1"},
            dedupe_key="enrich_item:alert:1:item-1",
        )

    assert enqueue.await_count == 2


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
async def test_execution_timeout_runs_terminal_failure_hook() -> None:
    terminal_errors: list[Exception] = []

    async def slow_handler(_job: Job) -> None:
        await asyncio.sleep(0.05)

    async def terminal_hook(_payload: dict[str, object], error: Exception) -> None:
        terminal_errors.append(error)

    executor = RetryWithTerminalFailureHookExecutor(
        parameters=_executor_parameters(slow_handler),
        task_runtime_config=WorkerTaskRuntimeConfig(
            WorkerTaskRuntimeSnapshot(default_execution_timeout_seconds=0.001)
        ),
        max_attempts=1,
        on_terminal_failure=terminal_hook,
    )

    with pytest.raises(MaxTimeExceeded) as error_info:
        await executor.execute(_job("triage_alert"), context=None)

    assert terminal_errors == [error_info.value]


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
async def test_executor_does_not_retry_deterministic_input_errors() -> None:
    attempts = 0
    terminal_errors: list[Exception] = []

    async def handler(_job: Job) -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid payload")

    async def terminal_hook(_payload: dict[str, object], error: Exception) -> None:
        terminal_errors.append(error)

    config = WorkerTaskRuntimeConfig(
        WorkerTaskRuntimeSnapshot(
            retry_initial_delay_seconds=0,
            retry_max_delay_seconds=0,
        )
    )
    executor = RetryWithTerminalFailureHookExecutor(
        parameters=_executor_parameters(handler),
        task_runtime_config=config,
        max_attempts=3,
        on_terminal_failure=terminal_hook,
        jitter=lambda: 0,
    )

    with pytest.raises(ValueError, match="invalid payload"):
        await executor.execute(_job("triage_alert"), context=None)

    assert attempts == 1
    assert len(terminal_errors) == 1
    assert isinstance(terminal_errors[0], ValueError)


@pytest.mark.asyncio
async def test_malformed_job_payload_does_not_mask_terminal_handler_failure() -> None:
    terminal_calls: list[tuple[dict[str, object], Exception]] = []

    async def handler(_job: Job) -> None:
        raise RuntimeError("handler failed")

    async def terminal_hook(payload: dict[str, object], error: Exception) -> None:
        terminal_calls.append((payload, error))

    executor = RetryWithTerminalFailureHookExecutor(
        parameters=_executor_parameters(handler),
        task_runtime_config=WorkerTaskRuntimeConfig(),
        max_attempts=1,
        on_terminal_failure=terminal_hook,
    )

    with pytest.raises(MaxRetriesExceeded) as error_info:
        await executor.execute(
            _job("triage_alert", payload=b"{not-json"),
            context=None,
        )

    assert isinstance(error_info.value.__cause__, RuntimeError)
    assert len(terminal_calls) == 1
    payload, error = terminal_calls[0]
    assert payload == {}
    assert error is error_info.value


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
async def test_runtime_config_refresh_loop_surfaces_programming_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    service._running = True
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        service,
        "refresh_task_runtime_config",
        AsyncMock(side_effect=TypeError("refresh integration bug")),
    )

    with pytest.raises(TypeError, match="refresh integration bug"):
        await service._runtime_config_refresh_loop()


@pytest.mark.asyncio
async def test_runtime_config_refresh_loop_retries_database_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []

    class UnavailableSessionContext:
        async def __aenter__(self) -> object:
            raise ConnectionError("database unavailable")

        async def __aexit__(self, *args: object) -> None:
            return None

    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    service._running = True

    async def stop_after_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        service._running = False

    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: UnavailableSessionContext(),
    )
    monkeypatch.setattr("app.services.task_queue_service.asyncio.sleep", stop_after_sleep)

    await service._runtime_config_refresh_loop()

    assert sleep_calls == [service.task_runtime_config.snapshot.refresh_interval_seconds]


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
    await service.shutdown()


@pytest.mark.asyncio
async def test_start_worker_does_not_restart_after_programming_error() -> None:
    run_gate = asyncio.Event()

    class FakeQueueManager:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, *, max_concurrent_tasks: int) -> None:
            self.calls += 1
            if self.calls == 1:
                raise TypeError("queue integration bug")
            await run_gate.wait()

    class FakeSchedulerManager:
        async def run(self) -> None:
            await run_gate.wait()

    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    fake_queue_manager = FakeQueueManager()
    service.pgqueuer = cast(Any, SimpleNamespace(qm=fake_queue_manager, sm=FakeSchedulerManager()))

    await service.start_worker(concurrency=3)

    try:
        for _ in range(100):
            worker_task = service._worker_task
            if fake_queue_manager.calls >= 2 or (worker_task is not None and worker_task.done()):
                break
            await asyncio.sleep(0)

        assert fake_queue_manager.calls == 1
        assert service._worker_task is not None
        assert service._worker_task.done()
        with pytest.raises(TypeError, match="queue integration bug"):
            await service._worker_task
    finally:
        run_gate.set()
        await service.shutdown()


@pytest.mark.asyncio
async def test_shutdown_attempts_every_cleanup_after_earlier_failures() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    worker_task = _FailingTask("worker cleanup failed")
    runtime_listener_task = _FailingTask("listener cleanup failed")
    connection = object()
    pool = SimpleNamespace(
        release=AsyncMock(side_effect=RuntimeError("connection cleanup failed")),
        close=AsyncMock(),
    )
    service._worker_task = cast(Any, worker_task)
    service._runtime_config_refresh_task = cast(Any, runtime_listener_task)
    service._connection = connection
    service._pool = cast(Any, pool)
    service._running = True

    await service.shutdown()

    assert worker_task.cancelled is True
    assert runtime_listener_task.cancelled is True
    pool.release.assert_awaited_once_with(connection)
    pool.close.assert_awaited_once_with()
    assert service._running is False
    assert service._worker_task is None
    assert service._runtime_config_refresh_task is None
    assert service._connection is None
    assert service._pool is None


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
    assert reason == "queue worker unavailable"


def test_get_worker_readiness_rejects_failed_runtime_config_task_without_leaking_error() -> None:
    service = TaskQueueService("postgresql+asyncpg://user:pass@localhost/db")
    service.queue_manager = object()  # type: ignore[assignment]
    service.queries = object()  # type: ignore[assignment]
    service._pool = cast(Any, _FakePool())
    service._running = True
    service._worker_task = SimpleNamespace(done=lambda: False)  # type: ignore[assignment]
    service._runtime_config_refresh_task = SimpleNamespace(
        done=lambda: True,
        exception=lambda: TypeError("secret implementation detail"),
    )  # type: ignore[assignment]

    ready, reason = service.get_worker_readiness()

    assert ready is False
    assert reason == "runtime configuration unavailable"
    assert "secret implementation detail" not in reason


@pytest.mark.asyncio
async def test_global_queue_service_is_published_after_successful_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_queue_module, "_task_queue_service", None)

    async def initialize_candidate() -> None:
        with pytest.raises(RuntimeError, match="Task queue service not initialized"):
            task_queue_module.get_task_queue_service()

    candidate = SimpleNamespace(
        initialize=AsyncMock(side_effect=initialize_candidate),
        shutdown=AsyncMock(),
    )
    monkeypatch.setattr(task_queue_module, "TaskQueueService", lambda _connection_string: candidate)

    result = await task_queue_module.initialize_task_queue_service("postgresql://queue")

    assert result is candidate
    assert task_queue_module.get_task_queue_service() is candidate
    candidate.initialize.assert_awaited_once_with()
    candidate.shutdown.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_global_queue_initialization_cleans_up_without_publishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = SimpleNamespace(
        initialize=AsyncMock(side_effect=RuntimeError("database unavailable")),
        shutdown=AsyncMock(),
    )
    monkeypatch.setattr(task_queue_module, "_task_queue_service", None)
    monkeypatch.setattr(task_queue_module, "TaskQueueService", lambda _connection_string: candidate)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await task_queue_module.initialize_task_queue_service("postgresql://queue")

    candidate.shutdown.assert_awaited_once_with()
    with pytest.raises(RuntimeError, match="Task queue service not initialized"):
        task_queue_module.get_task_queue_service()


@pytest.mark.asyncio
async def test_global_queue_initialization_can_retry_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_candidate = SimpleNamespace(
        initialize=AsyncMock(side_effect=RuntimeError("first attempt failed")),
        shutdown=AsyncMock(),
    )
    successful_candidate = SimpleNamespace(initialize=AsyncMock(), shutdown=AsyncMock())
    candidates = iter((failed_candidate, successful_candidate))
    monkeypatch.setattr(task_queue_module, "_task_queue_service", None)
    monkeypatch.setattr(task_queue_module, "TaskQueueService", lambda _connection_string: next(candidates))

    with pytest.raises(RuntimeError, match="first attempt failed"):
        await task_queue_module.initialize_task_queue_service("postgresql://queue")

    result = await task_queue_module.initialize_task_queue_service("postgresql://queue")

    failed_candidate.shutdown.assert_awaited_once_with()
    successful_candidate.initialize.assert_awaited_once_with()
    assert result is successful_candidate
    assert task_queue_module.get_task_queue_service() is successful_candidate
