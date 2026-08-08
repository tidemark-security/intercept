from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Case, Task, TaskUpdate
from app.services import task_service as task_service_module
from app.services.case_service import case_service
from app.services.task_service import TaskValidationError, task_service


def test_task_timeline_validator_owns_domain_error() -> None:
    with pytest.raises(
        TaskValidationError,
        match="Task timeline items cannot be added to tasks",
    ):
        task_service._validate_task_timeline_item({"type": "task"})  # noqa: SLF001


@pytest.mark.asyncio
async def test_invalid_task_sort_raises_typed_validation_error() -> None:
    with pytest.raises(
        TaskValidationError,
        match="Unsupported task sort column: secret_field",
    ):
        await task_service.get_tasks(
            cast(AsyncSession, None),
            sort_by="secret_field",
        )


@pytest.mark.asyncio
async def test_update_task_returns_committed_model_after_response_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed_task = Task(id=5, title="Committed task", created_by="analyst")
    db = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        expunge_all=Mock(),
    )
    monkeypatch.setattr(
        task_service,
        "update_task_in_transaction",
        AsyncMock(return_value=(committed_task, None)),
    )
    monkeypatch.setattr(
        task_service,
        "get_task",
        AsyncMock(side_effect=RuntimeError("response SELECT failed")),
    )

    result = await task_service.update_task(
        db,  # type: ignore[arg-type]
        5,
        TaskUpdate(title="Committed task"),
        updated_by="analyst",
    )

    assert result is committed_task
    db.commit.assert_awaited_once_with()
    db.expunge_all.assert_called_once_with()
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_task_case_link_locks_parent_before_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = Task(id=5, title="Task", created_by="analyst")
    events: list[str] = []

    async def execute(_statement: object) -> SimpleNamespace:
        event = "task_exists" if not events else "task_lock"
        events.append(event)
        value = 5 if event == "task_exists" else task
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    async def lock_case(_db: object, case_id: int) -> Case:
        events.append("case_lock")
        return Case(id=case_id, title="Case", created_by="analyst")

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), flush=AsyncMock())
    audit_service = SimpleNamespace(log_entity_updated=AsyncMock())
    monkeypatch.setattr(
        case_service,
        "lock_case_for_update",
        AsyncMock(side_effect=lock_case),
    )
    monkeypatch.setattr(task_service_module, "emit_event", AsyncMock())
    monkeypatch.setattr(
        task_service_module,
        "get_audit_service",
        lambda _db: audit_service,
    )

    outcome = await task_service.update_task_in_transaction(
        db,  # type: ignore[arg-type]
        5,
        TaskUpdate(case_id=9),
        updated_by="analyst",
    )

    assert outcome is not None
    assert outcome[0].case_id == 9
    assert events == ["task_exists", "case_lock", "task_lock"]
