from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.queue_status_service import QueueStatusService


@pytest.mark.asyncio
async def test_get_jobs_excludes_collapsed_log_rows_for_active_job_ids() -> None:
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar=lambda: 1),
            SimpleNamespace(
                fetchall=lambda: [
                    SimpleNamespace(
                        id=101,
                        entrypoint="directory_sync",
                        status="queued",
                        priority=10,
                        payload=None,
                        created=datetime(2026, 3, 31, 11, 34, 14, tzinfo=timezone.utc),
                        updated=datetime(2026, 3, 31, 11, 34, 14, tzinfo=timezone.utc),
                        picked_at=None,
                        finished_at=None,
                        duration_ms=None,
                        traceback=None,
                    )
                ]
            ),
        ]
    )

    service = QueueStatusService(mock_db)
    service._has_pgqueuer_tables = AsyncMock(return_value=True)  # type: ignore[method-assign]

    page = await service.get_jobs(status="queued")

    assert page["total"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0].id == 101
    assert page["items"][0].status == "queued"

    count_sql = str(mock_db.execute.await_args_list[0].args[0])
    data_sql = str(mock_db.execute.await_args_list[1].args[0])
    assert "FROM collapsed_log log" in count_sql
    assert "WHERE NOT EXISTS" in count_sql
    assert "WHERE active.id = log.id" in count_sql
    assert "FROM collapsed_log log" in data_sql
    assert "WHERE NOT EXISTS" in data_sql
    assert "WHERE active.id = log.id" in data_sql


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


@pytest.mark.asyncio
async def test_get_enrichment_jobs_excludes_collapsed_log_rows_for_active_job_ids() -> None:
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=SimpleNamespace(
            fetchall=lambda: [
                SimpleNamespace(
                    id=303,
                    entrypoint="enrich_item",
                    status="queued",
                    priority=0,
                    payload=json.dumps(
                        {
                            "entity_type": "case",
                            "entity_id": 1,
                            "item_id": "item-active-303",
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
        item_ids=["item-active-303"],
        linked_task_ids_by_item_id={"item-active-303": "303"},
    )

    assert list(jobs) == ["item-active-303"]
    sql = str(mock_db.execute.await_args.args[0])
    assert "FROM collapsed_log log" in sql
    assert "WHERE NOT EXISTS" in sql
    assert "WHERE active.id = log.id" in sql