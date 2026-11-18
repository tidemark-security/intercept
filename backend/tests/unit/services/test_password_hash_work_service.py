from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.password_hash_work_service import (
    PasswordHashWorkPolicy,
    PasswordHashWorkService,
)


@pytest.mark.asyncio
async def test_cancellation_waits_for_commit_then_cleans_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PasswordHashWorkService()
    db = AsyncMock(spec=AsyncSession)
    lease_id = uuid4()
    commit_started = asyncio.Event()
    allow_commit = asyncio.Event()
    released: list[Any] = []
    operation_called = False

    async def delayed_commit() -> None:
        commit_started.set()
        await allow_commit.wait()

    db.commit.side_effect = delayed_commit

    async def reserve(*_args: Any, **_kwargs: Any):
        return lease_id

    async def release(received_db: AsyncSession, *, lease_id: Any) -> None:
        assert received_db is db
        released.append(lease_id)

    def operation() -> None:
        nonlocal operation_called
        operation_called = True

    monkeypatch.setattr(service, "reserve", reserve)
    monkeypatch.setattr(service, "release", release)

    task = asyncio.create_task(
        service.reserve_commit_and_run(
            db,
            work_kind="login_verify",
            operation=operation,
        )
    )
    await commit_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert released == []
    assert operation_called is False

    allow_commit.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    db.rollback.assert_awaited_once_with()
    assert released == [lease_id]
    assert operation_called is False


@pytest.mark.asyncio
async def test_reservation_commit_exception_rolls_back_and_cleans_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PasswordHashWorkService()
    db = AsyncMock(spec=AsyncSession)
    commit_error = RuntimeError("commit failed")
    db.commit.side_effect = commit_error
    lease_id = uuid4()
    released: list[Any] = []

    async def reserve(*_args: Any, **_kwargs: Any):
        return lease_id

    async def release(_db: AsyncSession, *, lease_id: Any) -> None:
        released.append(lease_id)

    monkeypatch.setattr(service, "reserve", reserve)
    monkeypatch.setattr(service, "release", release)

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.reserve_commit_and_run(
            db,
            work_kind="password_reset",
            operation=lambda: None,
        )

    db.rollback.assert_awaited_once_with()
    assert released == [lease_id]


@pytest.mark.asyncio
async def test_committed_reservation_is_handed_directly_to_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PasswordHashWorkService()
    db = AsyncMock(spec=AsyncSession)
    lease_id = uuid4()
    events: list[str] = []

    async def reserve(*_args: Any, **_kwargs: Any):
        events.append("reserve")
        return lease_id

    async def run_reserved(
        received_db: AsyncSession,
        *,
        lease_id: Any,
        operation: Any,
    ) -> str:
        assert received_db is db
        assert lease_id == expected_lease_id
        assert db.commit.await_count == 1
        events.append("run")
        return operation()

    expected_lease_id = lease_id
    monkeypatch.setattr(service, "reserve", reserve)
    monkeypatch.setattr(service, "run_reserved", run_reserved)

    result = await service.reserve_commit_and_run(
        db,
        work_kind="password_change",
        operation=lambda: "complete",
    )

    assert result == "complete"
    assert events == ["reserve", "run"]


@pytest.mark.asyncio
async def test_cancellation_waits_for_worker_before_releasing_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PasswordHashWorkService()
    released = asyncio.Event()
    db = cast(AsyncSession, object())
    lease_id = uuid4()
    loop = asyncio.get_running_loop()
    worker_future: asyncio.Future[str] = loop.create_future()
    submitted_operations: list[Any] = []

    def held_operation() -> str:
        return "complete"

    def controlled_run_in_executor(
        executor: Any,
        operation: Any,
    ) -> asyncio.Future[str]:
        assert executor is None
        submitted_operations.append(operation)
        return worker_future

    async def record_release(
        received_db: AsyncSession,
        *,
        lease_id: Any,
    ) -> None:
        assert received_db is db
        assert lease_id == expected_lease_id
        released.set()

    expected_lease_id = lease_id
    monkeypatch.setattr(service, "release", record_release)
    monkeypatch.setattr(loop, "run_in_executor", controlled_run_in_executor)
    task = asyncio.create_task(
        service.run_reserved(
            db,
            lease_id=lease_id,
            operation=held_operation,
        )
    )
    await asyncio.sleep(0)
    assert submitted_operations == [held_operation]

    task.cancel()
    await asyncio.sleep(0)
    assert released.is_set() is False

    worker_future.set_result("complete")
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)
    assert released.is_set() is True


@pytest.mark.asyncio
async def test_local_semaphore_prevents_executor_queue_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PasswordHashWorkService()
    service._default_policy = PasswordHashWorkPolicy(  # noqa: SLF001
        max_concurrent=1,
        lease_seconds=900,
    )
    db = cast(AsyncSession, object())
    loop = asyncio.get_running_loop()
    worker_futures: list[asyncio.Future[None]] = [
        loop.create_future(),
        loop.create_future(),
    ]
    submitted_operations: list[Any] = []

    def first_operation() -> None:
        return None

    def second_operation() -> None:
        return None

    def controlled_run_in_executor(
        executor: Any,
        operation: Any,
    ) -> asyncio.Future[None]:
        assert executor is None
        submitted_operations.append(operation)
        return worker_futures[len(submitted_operations) - 1]

    async def ignore_release(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(service, "release", ignore_release)
    monkeypatch.setattr(loop, "run_in_executor", controlled_run_in_executor)
    first = asyncio.create_task(
        service.run_reserved(
            db,
            lease_id=uuid4(),
            operation=first_operation,
        )
    )
    await asyncio.sleep(0)
    assert submitted_operations == [first_operation]
    second = asyncio.create_task(
        service.run_reserved(
            db,
            lease_id=uuid4(),
            operation=second_operation,
        )
    )
    await asyncio.sleep(0)
    assert submitted_operations == [first_operation]

    worker_futures[0].set_result(None)
    for _ in range(10):
        await asyncio.sleep(0)
        if len(submitted_operations) == 2:
            break
    assert submitted_operations == [first_operation, second_operation]
    worker_futures[1].set_result(None)
    await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
