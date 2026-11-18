from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.routes import enrichments
from app.services.enrichment.service import (
    EnrichmentNotFoundError,
    EnrichmentValidationError,
)
from app.services.maxmind_service import MaxMindConfigurationError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (EnrichmentNotFoundError("Timeline item item-1 not found"), 404),
        (EnrichmentValidationError("No provider matched"), 400),
    ],
)
async def test_enqueue_item_maps_only_expected_enrichment_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    monkeypatch.setattr(
        enrichments.enrichment_service,
        "enqueue_item_enrichment",
        AsyncMock(side_effect=error),
    )
    db = SimpleNamespace(rollback=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await enrichments.enqueue_item_enrichment(
            entity_type="alert",
            entity_id=1,
            item_id="item-1",
            db=db,
            _current_user=SimpleNamespace(),
        )

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == str(error)
    db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_enqueue_item_does_not_mask_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unexpected = ValueError("implementation defect")
    monkeypatch.setattr(
        enrichments.enrichment_service,
        "enqueue_item_enrichment",
        AsyncMock(side_effect=unexpected),
    )
    db = SimpleNamespace(rollback=AsyncMock())

    with pytest.raises(ValueError, match="implementation defect"):
        await enrichments.enqueue_item_enrichment(
            entity_type="alert",
            entity_id=1,
            item_id="item-1",
            db=db,
            _current_user=SimpleNamespace(),
        )

    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_directory_sync_does_not_relabel_queue_defects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = SimpleNamespace(
        enqueue=AsyncMock(side_effect=ValueError("queue implementation defect"))
    )
    monkeypatch.setattr(
        enrichments.enrichment_registry,
        "get",
        lambda _provider_id: SimpleNamespace(supports_bulk_sync=True),
    )
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: queue,
    )

    with pytest.raises(ValueError, match="queue implementation defect"):
        await enrichments.enqueue_directory_sync(provider_id="ldap", db=None)


@pytest.mark.asyncio
async def test_maxmind_update_maps_only_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        enrichments.maxmind_service,
        "enqueue_update",
        AsyncMock(side_effect=MaxMindConfigurationError("not configured")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await enrichments.trigger_maxmind_update(db=None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "not configured"


@pytest.mark.asyncio
async def test_maxmind_update_does_not_mask_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        enrichments.maxmind_service,
        "enqueue_update",
        AsyncMock(side_effect=ValueError("implementation defect")),
    )

    with pytest.raises(ValueError, match="implementation defect"):
        await enrichments.trigger_maxmind_update(db=None)
