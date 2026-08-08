from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pgqueuer.errors import MaxRetriesExceeded

from app.models.enums import TaskStatus
from app.services import tasks
from app.services.task_service import _task_status_description
from app.services.timeline_service import timeline_service


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (TaskStatus.TODO, "Task status changed to To Do"),
        (TaskStatus.IN_PROGRESS, "Task status changed to In Progress"),
        (TaskStatus.DONE, "Task marked as Done"),
    ],
)
def test_task_status_description(status: TaskStatus, expected: str) -> None:
    assert _task_status_description(status) == expected


def test_add_task_agent_note_has_only_required_input(monkeypatch) -> None:
    add_timeline_item = Mock()
    monkeypatch.setattr(timeline_service, "add_timeline_item", add_timeline_item)
    task = SimpleNamespace()

    tasks._add_task_agent_note(
        task,
        "agent-user",
        "Autonomous task execution started.",
        ["ai-agent", "automation-started"],
    )

    args, kwargs = add_timeline_item.call_args
    assert args[0] is task
    assert kwargs == {"created_by": "agent-user"}
    item = args[1]
    assert "id" not in item
    assert item["created_at"] == item["timestamp"]
    assert item["created_by"] == "agent-user"
    assert item["tags"] == ["ai-agent", "automation-started"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("postgresql://user:secret@internal/db"), "Background task failed"),
        (TimeoutError("https://internal-provider/token?secret=value"), "Background task timed out"),
        (ConnectionError("10.0.0.12:8443 refused"), "External service unavailable"),
    ],
)
def test_terminal_failure_messages_do_not_persist_internal_exception_text(
    error: Exception,
    expected: str,
) -> None:
    assert tasks._format_terminal_failure_message(error) == expected


def test_retry_exhaustion_hides_wrapped_root_cause() -> None:
    root_cause = RuntimeError("API key secret-value rejected by internal host")
    try:
        raise MaxRetriesExceeded(4) from root_cause
    except MaxRetriesExceeded as error:
        message = tasks._format_terminal_failure_message(error)

    assert message == "Retries exhausted"
    assert "secret-value" not in message


@pytest.mark.asyncio
async def test_enrichment_handler_passes_request_identity_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()

    @asynccontextmanager
    async def session_factory():
        yield db

    run_item_enrichment = AsyncMock()
    monkeypatch.setattr(tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(
        tasks.enrichment_service,
        "run_item_enrichment",
        run_item_enrichment,
    )

    await tasks.handle_enrich_item(
        {
            "entity_type": "alert",
            "entity_id": 42,
            "item_id": "item-1",
            "enrichment_request_id": " request-1 ",
        },
        task_id="task-1",
    )

    run_item_enrichment.assert_awaited_once_with(
        db,
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        task_id="task-1",
        enrichment_request_id="request-1",
    )


@pytest.mark.asyncio
async def test_enrichment_terminal_hook_passes_request_identity_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()

    @asynccontextmanager
    async def session_factory():
        yield db

    mark_failed = AsyncMock()
    monkeypatch.setattr(tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(
        tasks.enrichment_service,
        "mark_item_enrichment_failed",
        mark_failed,
    )

    await tasks._handle_enrich_item_terminal_failure(
        {
            "entity_type": "case",
            "entity_id": 7,
            "item_id": "item-2",
            "enrichment_request_id": "request-2",
        },
        RuntimeError("provider failed"),
        task_id="task-2",
    )

    mark_failed.assert_awaited_once_with(
        db,
        entity_type="case",
        entity_id=7,
        item_id="item-2",
        error_message="Background task failed",
        task_id="task-2",
        enrichment_request_id="request-2",
    )
