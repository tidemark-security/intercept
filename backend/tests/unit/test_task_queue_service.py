from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.services.task_queue_service import TaskQueueService


class _FakePool:
    def __init__(self, size: int = 1):
        self._size = size

    def get_size(self) -> int:
        return self._size


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