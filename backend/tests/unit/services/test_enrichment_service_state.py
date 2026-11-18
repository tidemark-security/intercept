from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services.enrichment.service import EnrichmentService


def test_clear_state_reports_explicit_null_fields_as_changes() -> None:
    item = {
        "enrichment_status": None,
        "enrichment_task_id": None,
        "enrichment_request_id": "request-1",
        "enrichments": {},
    }

    assert EnrichmentService()._clear_item_enrichment_state(item) is True
    assert item == {"enrichments": {}}


def test_clear_error_reports_explicit_null_system_entry_as_change() -> None:
    item = {"enrichments": {"system": None}}

    assert EnrichmentService()._clear_item_enrichment_error(item) is True
    assert item == {"enrichments": {}}


def test_failure_state_replaces_explicit_null_system_entry() -> None:
    item = {
        "enrichment_status": "failed",
        "enrichment_task_id": None,
        "enrichment_request_id": "request-1",
        "enrichments": {"system": None},
    }

    assert EnrichmentService()._set_item_enrichment_failed(
        item,
        error_message="provider failed",
    ) is True
    assert item == {
        "enrichment_status": "failed",
        "enrichments": {"system": {"error": "provider failed"}},
    }


def test_request_token_rejects_a_superseded_or_unversioned_task() -> None:
    service = EnrichmentService()
    item = {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
    }

    assert service._matches_enrichment_request(
        item,
        task_id="task-old",
        enrichment_request_id="request-old",
    ) is False
    assert service._matches_enrichment_request(
        item,
        task_id="task-old",
        enrichment_request_id=None,
    ) is False
    assert service._matches_enrichment_request(
        item,
        task_id="task-new",
        enrichment_request_id="request-new",
    ) is True


def test_legacy_task_only_matches_an_active_legacy_state() -> None:
    service = EnrichmentService()

    assert service._matches_enrichment_request(
        {"enrichment_status": "pending"},
        task_id="queued-task",
        enrichment_request_id=None,
    ) is True
    assert service._matches_enrichment_request(
        {
            "enrichment_status": "in_progress",
            "enrichment_task_id": "queued-task",
        },
        task_id="queued-task",
        enrichment_request_id=None,
    ) is True
    assert service._matches_enrichment_request(
        {"enrichment_status": "complete"},
        task_id="queued-task",
        enrichment_request_id=None,
    ) is False
    assert service._matches_enrichment_request(
        {"enrichment_status": "pending"},
        task_id="queued-task",
        enrichment_request_id="request-new",
    ) is False


def test_reconciliation_ignores_a_job_from_an_older_request() -> None:
    service = EnrichmentService()
    item = {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
        "enrichments": {},
    }
    old_job = SimpleNamespace(
        id="task-old",
        status="picked",
        payload={"enrichment_request_id": "request-old"},
    )

    assert service._reconcile_item_with_job(item, old_job) is False
    assert item == {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
        "enrichments": {},
    }


def test_successful_reconciliation_clears_the_finished_request_identity() -> None:
    service = EnrichmentService()
    item = {
        "enrichment_status": "in_progress",
        "enrichment_task_id": "task-current",
        "enrichment_request_id": "request-current",
    }
    current_job = SimpleNamespace(
        id="task-current",
        status="successful",
        payload=None,
    )

    assert service._reconcile_item_with_job(item, current_job) is True
    assert item == {"enrichment_status": "complete"}


@pytest.mark.asyncio
async def test_preparing_enrichment_assigns_a_server_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    entity = SimpleNamespace(priority=None, timeline_items={})
    item = {"id": "item-1", "type": "observable"}
    monkeypatch.setattr(
        "app.services.enrichment.service.flag_modified",
        lambda *_: None,
    )
    monkeypatch.setattr(
        service,
        "_should_ignore_item_enrichment",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(service, "_get_provider_item", AsyncMock(return_value=item))
    monkeypatch.setattr(
        service,
        "get_matching_enabled_providers",
        AsyncMock(return_value=[object()]),
    )

    priority = await service.prepare_item_enrichment_enqueue(
        object(),  # type: ignore[arg-type]
        entity=entity,
        item=item,
    )

    assert priority == 0
    assert item["enrichment_status"] == "pending"
    UUID(item["enrichment_request_id"])


@pytest.mark.asyncio
async def test_identity_update_rotates_request_and_clears_old_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    entity = SimpleNamespace(priority=None, timeline_items={})
    previous_item = {"id": "item-1", "type": "observable", "value": "old"}
    updated_item = {
        "id": "item-1",
        "type": "observable",
        "value": "new",
        "enrichment_status": "in_progress",
        "enrichment_task_id": "task-old",
        "enrichment_request_id": "request-old",
        "enrichments": {"provider": {"value": "old"}},
    }
    monkeypatch.setattr(
        "app.services.enrichment.service.flag_modified",
        lambda *_: None,
    )
    monkeypatch.setattr(
        service,
        "_should_ignore_item_enrichment",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        service,
        "_get_provider_signatures",
        AsyncMock(
            side_effect=[
                [("provider", "old")],
                [("provider", "new")],
                [("provider", "new")],
            ]
        ),
    )

    priority = await service.prepare_updated_item_enrichment(
        object(),  # type: ignore[arg-type]
        entity=entity,
        previous_item=previous_item,
        updated_item=updated_item,
    )

    assert priority == 0
    assert updated_item["enrichment_status"] == "pending"
    assert "enrichment_task_id" not in updated_item
    assert updated_item["enrichments"] == {}
    assert updated_item["enrichment_request_id"] != "request-old"
    UUID(updated_item["enrichment_request_id"])


@pytest.mark.asyncio
async def test_enqueue_guard_rejects_a_request_replaced_before_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    item = {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
    }
    entity = SimpleNamespace(timeline_items={"item-1": item})
    db = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(
        service,
        "_load_timeline_item_for_update",
        AsyncMock(return_value=(entity, item)),
    )

    request_id = await service._get_enrichment_request_for_enqueue(
        db,  # type: ignore[arg-type]
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        expected_request_id="request-old",
    )

    assert request_id is None
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_worker_start_rejects_a_superseded_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    item = {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
    }
    entity = SimpleNamespace(timeline_items={"item-1": item})
    db = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(
        service,
        "_load_timeline_item_for_update",
        AsyncMock(return_value=(entity, item)),
    )

    await service.run_item_enrichment(
        db,  # type: ignore[arg-type]
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        task_id="task-old",
        enrichment_request_id="request-old",
    )

    assert item["enrichment_status"] == "pending"
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_terminal_failure_rejects_a_superseded_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    item = {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
        "enrichments": {},
    }
    entity = SimpleNamespace(timeline_items={"item-1": item})
    db = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(
        service,
        "_load_timeline_item_for_update",
        AsyncMock(return_value=(entity, item)),
    )

    await service.mark_item_enrichment_failed(
        db,  # type: ignore[arg-type]
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        task_id="task-old",
        enrichment_request_id="request-old",
        error_message="old task failed",
    )

    assert item == {
        "enrichment_status": "pending",
        "enrichment_request_id": "request-new",
        "enrichments": {},
    }
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_enqueue_link_failure_rolls_back_before_guarded_compensation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    enqueue = AsyncMock(return_value="queued-task-1")
    persist_link = AsyncMock(side_effect=RuntimeError("link commit failed"))
    mark_failed = AsyncMock()
    db = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(
        service,
        "_get_enrichment_request_for_enqueue",
        AsyncMock(return_value="request-1"),
    )
    monkeypatch.setattr(service, "_enqueue_item_task", enqueue)
    monkeypatch.setattr(service, "_persist_enrichment_task_link", persist_link)
    monkeypatch.setattr(service, "_mark_item_enrichment_failed", mark_failed)

    result = await service.enqueue_prepared_item_enrichment(
        db,  # type: ignore[arg-type]
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        priority=50,
        raise_on_error=False,
    )

    assert result is None
    db.rollback.assert_awaited_once_with()
    enqueue.assert_awaited_once_with(
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        priority=50,
        enrichment_request_id="request-1",
    )
    persist_link.assert_awaited_once_with(
        db,
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        task_id="queued-task-1",
        enrichment_request_id="request-1",
    )
    mark_failed.assert_awaited_once_with(
        db,
        entity_type="alert",
        entity_id=42,
        item_id="item-1",
        error_message="Enrichment task could not be queued",
        task_id="queued-task-1",
        enrichment_request_id="request-1",
    )


@pytest.mark.asyncio
async def test_failed_compensation_does_not_escape_best_effort_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    monkeypatch.setattr(
        service,
        "_enqueue_item_task",
        AsyncMock(side_effect=RuntimeError("queue unavailable")),
    )
    monkeypatch.setattr(
        service,
        "_get_enrichment_request_for_enqueue",
        AsyncMock(return_value="request-2"),
    )
    monkeypatch.setattr(
        service,
        "_mark_item_enrichment_failed",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    db = SimpleNamespace(rollback=AsyncMock())

    result = await service.enqueue_prepared_item_enrichment(
        db,  # type: ignore[arg-type]
        entity_type="case",
        entity_id=7,
        item_id="item-2",
        priority=25,
        raise_on_error=False,
    )

    assert result is None


@pytest.mark.asyncio
async def test_queue_payload_and_dedupe_key_include_the_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EnrichmentService()
    queue = SimpleNamespace(enqueue=AsyncMock(return_value="task-1"))
    monkeypatch.setattr(
        "app.services.enrichment.service.get_task_queue_service",
        lambda: queue,
    )

    task_id = await service._enqueue_item_task(
        entity_type="Alert",
        entity_id=42,
        item_id="item-1",
        priority=50,
        enrichment_request_id="request-1",
    )

    assert task_id == "task-1"
    queue.enqueue.assert_awaited_once_with(
        task_name="enrich_item",
        payload={
            "entity_type": "Alert",
            "entity_id": 42,
            "item_id": "item-1",
            "enrichment_request_id": "request-1",
        },
        priority=50,
        dedupe_key="enrich_item:alert:42:item-1:request-1",
    )
