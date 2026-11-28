from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.enums import AlertStatus, CaseStatus, Priority, TaskStatus
from app.models.models import Alert, Case, Task
from app.services.dashboard_service import DashboardService


class _ScalarResult:
    def __init__(self, values: list[Alert | Case | Task]) -> None:
        self._values = values

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[Alert | Case | Task]:
        return self._values


def _dashboard_db(*result_sets: list[Alert | Case | Task]) -> SimpleNamespace:
    return SimpleNamespace(
        execute=AsyncMock(side_effect=[_ScalarResult(values) for values in result_sets]),
    )


@pytest.mark.asyncio
async def test_recent_items_preserve_entity_specific_response_mapping() -> None:
    alert = Alert(
        id=7,
        title="Recent alert",
        priority=Priority.HIGH,
        status=AlertStatus.ESCALATED,
        updated_at=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
    )
    case = Case(
        id=8,
        title="Recent case",
        created_by="analyst",
        priority=Priority.CRITICAL,
        updated_at=datetime(2026, 7, 19, 14, tzinfo=timezone.utc),
    )
    case.status = None  # type: ignore[assignment]
    task = Task(
        id=9,
        title="Recent task",
        created_by="analyst",
        priority=Priority.MEDIUM,
        updated_at=datetime(2026, 7, 19, 13, tzinfo=timezone.utc),
    )
    task.status = None  # type: ignore[assignment]
    db = _dashboard_db([alert], [case], [task])

    items = await DashboardService().get_recent_items(db, limit=3)

    assert items == [
        {
            "id": 8,
            "human_id": "CAS-0000008",
            "title": "Recent case",
            "item_type": "case",
            "priority": Priority.CRITICAL,
            "status": "NEW",
            "updated_at": datetime(2026, 7, 19, 14, tzinfo=timezone.utc),
        },
        {
            "id": 9,
            "human_id": "TSK-0000009",
            "title": "Recent task",
            "item_type": "task",
            "priority": Priority.MEDIUM,
            "status": "TODO",
            "updated_at": datetime(2026, 7, 19, 13, tzinfo=timezone.utc),
        },
        {
            "id": 7,
            "human_id": "ALT-0000007",
            "title": "Recent alert",
            "item_type": "alert",
            "priority": Priority.HIGH,
            "status": "ESCALATED",
            "updated_at": datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
        },
    ]


@pytest.mark.asyncio
async def test_priority_items_preserve_mapping_sorting_and_truncation() -> None:
    alert = Alert(
        id=17,
        title="Priority alert",
        priority=Priority.HIGH,
        status=AlertStatus.IN_PROGRESS,
        updated_at=datetime(2026, 7, 19, 15, tzinfo=timezone.utc),
    )
    case = Case(
        id=18,
        title="Priority case",
        created_by="analyst",
        priority=Priority.EXTREME,
        status=CaseStatus.IN_PROGRESS,
        updated_at=datetime(2026, 7, 19, 14, tzinfo=timezone.utc),
    )
    task = Task(
        id=19,
        title="Priority task",
        created_by="analyst",
        priority=Priority.EXTREME,
        status=TaskStatus.IN_PROGRESS,
        updated_at=datetime(2026, 7, 19, 13, tzinfo=timezone.utc),
    )
    db = _dashboard_db([alert], [case], [task])

    items, truncated = await DashboardService().get_priority_items(
        db,
        username="analyst",
        limit=2,
    )

    assert truncated is True
    assert items == [
        {
            "id": 19,
            "human_id": "TSK-0000019",
            "title": "Priority task",
            "item_type": "task",
            "priority": Priority.EXTREME,
            "status": "IN_PROGRESS",
            "updated_at": datetime(2026, 7, 19, 13, tzinfo=timezone.utc),
        },
        {
            "id": 18,
            "human_id": "CAS-0000018",
            "title": "Priority case",
            "item_type": "case",
            "priority": Priority.EXTREME,
            "status": "IN_PROGRESS",
            "updated_at": datetime(2026, 7, 19, 14, tzinfo=timezone.utc),
        },
    ]


@pytest.mark.asyncio
async def test_priority_items_rank_each_partition_before_limiting() -> None:
    older_extreme = Alert(
        id=27,
        title="Older extreme alert",
        priority=Priority.EXTREME,
        status=AlertStatus.NEW,
        updated_at=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
    )
    newer_low = Alert(
        id=28,
        title="Newer low alert",
        priority=Priority.LOW,
        status=AlertStatus.NEW,
        updated_at=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
    )
    db = _dashboard_db([older_extreme, newer_low], [], [])

    items, truncated = await DashboardService().get_priority_items(
        db,
        username="analyst",
        limit=1,
    )

    assert [item["id"] for item in items] == [27]
    assert truncated is True
    for call in db.execute.await_args_list:
        query_text = str(call.args[0])
        assert "ORDER BY CASE" in query_text
        assert query_text.index("ORDER BY CASE") < query_text.index("updated_at DESC")
