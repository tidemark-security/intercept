from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.queue_status_service import QueueStatusService


@pytest.mark.asyncio
async def test_get_enrichment_jobs_matches_active_rows_by_payload() -> None:
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=SimpleNamespace(
            fetchall=lambda: [
                SimpleNamespace(
                    id=101,
                    entrypoint="enrich_item",
                    status="queued",
                    priority=0,
                    payload=json.dumps(
                        {
                            "entity_type": "case",
                            "entity_id": 1,
                            "item_id": "item-active-1",
                        }
                    ).encode("utf-8"),
                    created=None,
                    updated=None,
                    picked_at=None,
                    finished_at=None,
                    duration_ms=None,
                    traceback=None,
                )
            ]
        )
    )

    service = QueueStatusService(mock_db)
    service._has_pgqueuer_tables = AsyncMock(return_value=True)  # type: ignore[method-assign]

    jobs = await service.get_enrichment_jobs_for_entity(
        entity_type="case",
        entity_id=1,
        item_ids=["item-active-1"],
        linked_task_ids_by_item_id={"item-active-1": "101"},
    )

    assert list(jobs) == ["item-active-1"]
    assert jobs["item-active-1"].id == 101
    assert jobs["item-active-1"].status == "queued"
    assert jobs["item-active-1"].payload == {
        "entity_type": "case",
        "entity_id": 1,
        "item_id": "item-active-1",
    }


@pytest.mark.asyncio
async def test_get_enrichment_jobs_matches_terminal_log_rows_by_linked_task_id() -> None:
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=SimpleNamespace(
            fetchall=lambda: [
                SimpleNamespace(
                    id=202,
                    entrypoint="enrich_item",
                    status="exception",
                    priority=0,
                    payload=None,
                    created=None,
                    updated=None,
                    picked_at=None,
                    finished_at=None,
                    duration_ms=None,
                    traceback='{"exception_type": "RuntimeError"}',
                )
            ]
        )
    )

    service = QueueStatusService(mock_db)
    service._has_pgqueuer_tables = AsyncMock(return_value=True)  # type: ignore[method-assign]

    jobs = await service.get_enrichment_jobs_for_entity(
        entity_type="case",
        entity_id=1,
        item_ids=["item-log-1"],
        linked_task_ids_by_item_id={"item-log-1": "202"},
    )

    assert list(jobs) == ["item-log-1"]
    assert jobs["item-log-1"].id == 202
    assert jobs["item-log-1"].status == "exception"
    assert jobs["item-log-1"].payload is None