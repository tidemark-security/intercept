from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertStatus, Priority, RecommendationStatus
from app.models.models import Alert, TriageRecommendation
from app.services import triage_recommendation_service as service
from app.services.task_queue_service import TaskQueueNotInitializedError


@pytest.mark.asyncio
async def test_enqueue_returns_committed_snapshot_when_compensation_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recommendation: TriageRecommendation | None = None
    commit_count = 0
    rollback_count = 0

    def add(instance: object) -> None:
        nonlocal recommendation
        if isinstance(instance, TriageRecommendation):
            recommendation = instance

    async def flush() -> None:
        assert recommendation is not None
        recommendation.id = 73

    async def commit() -> None:
        nonlocal commit_count
        commit_count += 1

    async def rollback() -> None:
        nonlocal rollback_count
        rollback_count += 1

    db = cast(
        AsyncSession,
        SimpleNamespace(
            add=add,
            flush=flush,
            commit=commit,
            rollback=rollback,
        ),
    )
    alert = Alert(
        id=9,
        title="Queued triage",
        status=AlertStatus.NEW,
        priority=Priority.MEDIUM,
    )

    async def get_setting(_self: object, key: str) -> str:
        assert key == "langflow.alert_triage_flow_id"
        return "flow-1"

    monkeypatch.setattr("app.services.settings_service.SettingsService.get", get_setting)
    monkeypatch.setattr(service, "_lock_alert", AsyncMock(return_value=alert))
    monkeypatch.setattr(
        service,
        "get_by_alert_id",
        AsyncMock(side_effect=[None, RuntimeError("response SELECT failed")]),
    )
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: SimpleNamespace(
            enqueue=AsyncMock(
                side_effect=TaskQueueNotInitializedError("queue unavailable")
            )
        ),
    )

    result = await service.enqueue_triage(db, alert.id, enqueued_by="analyst")

    assert result.id == 73
    assert result.status == RecommendationStatus.QUEUED
    assert result.created_by == "analyst"
    assert commit_count == 1
    assert rollback_count == 1
