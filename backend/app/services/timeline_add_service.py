from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.enums import RealtimeEventType
from app.models.models import Alert, Case, Task
from app.services.audit_service import get_audit_service
from app.services.realtime_service import emit_event
from app.services.timeline_service import timeline_service

logger = logging.getLogger(__name__)

_TIMELINE_ENTITY_MODELS = {
    "alert": Alert,
    "case": Case,
    "task": Task,
}


@dataclass(frozen=True)
class TimelineItemAddResult:
    item: dict[str, Any]
    created: bool


class TimelineItemConflict(ValueError):
    """The locked timeline item no longer matches the caller's snapshot."""


def _dump_timeline_item(timeline_item: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    item_dict = timeline_item.model_dump(mode="json", exclude_unset=exclude_unset)
    if item_dict.get("created_at") is None:
        item_dict.pop("created_at", None)
    return item_dict


async def _delete_storage_object_after_commit(
    storage_key: str,
    *,
    action: str,
) -> None:
    from app.services.storage_service import storage_service

    try:
        await storage_service.delete_file(storage_key)
    except Exception:
        # The database mutation is already committed. An orphaned object is
        # safer than reporting the committed mutation as though it failed.
        logger.exception("Could not delete storage object %s after %s", storage_key, action)


async def _load_entity_for_timeline_update(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: int,
) -> Any | None:
    normalized_type = entity_type.lower()
    model = _TIMELINE_ENTITY_MODELS.get(normalized_type)
    if model is None:
        raise ValueError(f"Unsupported entity type for timeline update: {entity_type}")

    stmt = (
        select(model)
        .where(model.id == entity_id)
        .with_for_update()
        # A caller may already have loaded the entity in this session. Refresh
        # it from the row-locked SELECT so a stale identity-map value cannot
        # overwrite a timeline mutation committed by another transaction.
        .execution_options(populate_existing=True)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _load_timeline_item_for_update(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: int,
    item_id: str,
) -> Optional[tuple[Any, dict[str, Any]]]:
    entity = await _load_entity_for_timeline_update(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if entity is None:
        return None

    existing_item = timeline_service.find_item_by_id(
        getattr(entity, "timeline_items", None) or {},
        item_id,
    )
    if existing_item is None:
        return None
    return entity, existing_item


async def add_timeline_item_and_commit(
    db: AsyncSession,
    *,
    entity_id: int,
    entity_type: str,
    timeline_item: Any,
    performed_by: str,
    validate_item: Optional[Callable[[dict[str, Any]], None]] = None,
    created_at_override: Optional[datetime] = None,
    preserve_item_id: bool = False,
    idempotent: bool = False,
) -> Optional[TimelineItemAddResult]:
    entity = await _load_entity_for_timeline_update(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if entity is None:
        return None

    item_dict = _dump_timeline_item(timeline_item)
    if created_at_override is not None:
        item_dict["created_at"] = created_at_override.isoformat()

    if validate_item is not None:
        validate_item(item_dict)

    if idempotent:
        if not preserve_item_id:
            raise ValueError("Idempotent timeline additions must preserve the item ID")
        item_id = item_dict.get("id")
        if not item_id:
            raise ValueError("Idempotent timeline additions require an item ID")

        existing_item = timeline_service.find_item_by_id(
            getattr(entity, "timeline_items", None) or {},
            item_id,
        )
        if existing_item is not None:
            # This read-only commit releases the entity row lock while preserving
            # the same transaction ownership contract as a successful addition.
            await db.commit()
            return TimelineItemAddResult(item=deepcopy(existing_item), created=False)

    item_dict, enrichment_priority = await timeline_service.add_timeline_item_with_sync(
        db,
        entity,
        item_dict,
        performed_by,
        entity_id=entity_id,
        entity_type=entity_type,
        preserve_item_id=preserve_item_id,
    )

    await emit_event(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=RealtimeEventType.TIMELINE_ITEM_ADDED,
        performed_by=performed_by,
        item_id=item_dict.get("id"),
        item_type=item_dict.get("type"),
    )

    await get_audit_service(db).log_timeline_item_added(
        entity_type=entity_type,
        entity_id=entity_id,
        item_id=item_dict.get("id", ""),
        item_type=item_dict.get("type", "unknown"),
        user=performed_by,
        new_value=item_dict,
    )

    await db.commit()

    if enrichment_priority is not None:
        from app.services.enrichment.service import enrichment_service

        await enrichment_service.enqueue_prepared_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_dict["id"],
            priority=enrichment_priority,
            raise_on_error=False,
        )

    return TimelineItemAddResult(item=item_dict, created=True)


async def update_timeline_item_and_commit(
    db: AsyncSession,
    *,
    entity_id: int,
    entity_type: str,
    item_id: str,
    timeline_item: Any,
    performed_by: str,
    companion_timeline_item: Any | None = None,
    expected_item_fields: dict[str, Any] | None = None,
) -> Optional[dict[str, Any]]:
    """Update an item and optionally add a companion item in one transaction."""
    locked_item = await _load_timeline_item_for_update(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        item_id=item_id,
    )
    if locked_item is None:
        return None
    entity, existing_item = locked_item

    if expected_item_fields is not None and any(
        existing_item.get(field) != expected
        for field, expected in expected_item_fields.items()
    ):
        raise TimelineItemConflict("Timeline item changed while the update was in progress")

    previous_item = deepcopy(existing_item)
    item_dict = _dump_timeline_item(
        timeline_item,
        # Attachment API conversion strips server-owned storage metadata. Dumping
        # model defaults here would add those fields back as null/default values
        # and overwrite the existing attachment during a metadata-only edit.
        exclude_unset=existing_item.get("type") == "attachment",
    )

    sync_result = await timeline_service.update_timeline_item_with_sync(
        db,
        entity,
        item_id,
        item_dict,
        performed_by,
    )
    if sync_result is None:
        return None
    updated_item = sync_result.item

    stored_item = timeline_service.find_item_by_id(
        getattr(entity, "timeline_items", None) or {},
        item_id,
    )
    if stored_item is not None:
        updated_item = stored_item

    staged_storage_key_to_delete: str | None = None
    if (
        previous_item.get("type") == "attachment"
        and updated_item.get("upload_storage_key") is None
    ):
        candidate = previous_item.get("upload_storage_key")
        if isinstance(candidate, str) and candidate:
            staged_storage_key_to_delete = candidate

    from app.services.enrichment.service import enrichment_service

    enrichment_priority = await enrichment_service.prepare_updated_item_enrichment(
        db,
        entity=entity,
        previous_item=previous_item,
        updated_item=updated_item,
    )

    await get_audit_service(db).log_timeline_edit(
        entity_type=entity_type,
        entity_id=entity_id,
        item_id=item_id,
        item_type=updated_item.get("type", previous_item.get("type", "unknown")),
        before=previous_item,
        after=updated_item,
        user=performed_by,
    )

    await emit_event(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=RealtimeEventType.TIMELINE_ITEM_UPDATED,
        performed_by=performed_by,
        item_id=item_id,
        item_type=updated_item.get("type", previous_item.get("type")),
    )

    companion_item: dict[str, Any] | None = None
    companion_enrichment_priority: int | None = None
    if companion_timeline_item is not None:
        companion_item, companion_enrichment_priority = (
            await timeline_service.add_timeline_item_with_sync(
                db,
                entity,
                _dump_timeline_item(companion_timeline_item),
                performed_by,
                entity_id=entity_id,
                entity_type=entity_type,
            )
        )
        await get_audit_service(db).log_timeline_item_added(
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=companion_item.get("id", ""),
            item_type=companion_item.get("type", "unknown"),
            user=performed_by,
            new_value=companion_item,
        )
        await emit_event(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=RealtimeEventType.TIMELINE_ITEM_ADDED,
            performed_by=performed_by,
            item_id=companion_item.get("id"),
            item_type=companion_item.get("type"),
        )

    await db.commit()

    if staged_storage_key_to_delete is not None:
        await _delete_storage_object_after_commit(
            staged_storage_key_to_delete,
            action=f"completing {entity_type} attachment {item_id}",
        )

    if sync_result.autonomous_task_enqueue is not None:
        from app.services.task_service import task_service

        await task_service.enqueue_autonomous_task_after_commit(
            db,
            task_id=sync_result.autonomous_task_enqueue.task_id,
            assignee=sync_result.autonomous_task_enqueue.assignee,
        )

    if enrichment_priority is not None:
        await enrichment_service.enqueue_prepared_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            priority=enrichment_priority,
            raise_on_error=False,
        )

    if companion_item is not None and companion_enrichment_priority is not None:
        await enrichment_service.enqueue_prepared_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=companion_item["id"],
            priority=companion_enrichment_priority,
            raise_on_error=False,
        )

    return updated_item


async def remove_timeline_item_and_commit(
    db: AsyncSession,
    *,
    entity_id: int,
    entity_type: str,
    item_id: str,
    performed_by: str,
) -> Optional[dict[str, Any]]:
    """Remove one timeline item while holding the owning entity's row lock."""
    locked_item = await _load_timeline_item_for_update(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        item_id=item_id,
    )
    if locked_item is None:
        return None
    entity, existing_item = locked_item

    previous_item = deepcopy(existing_item)
    cleanup = await timeline_service.remove_timeline_item_with_cleanup(
        db,
        entity,
        item_id,
        performed_by,
    )
    if cleanup is None:
        return None

    await get_audit_service(db).log_timeline_item_deleted(
        entity_type=entity_type,
        entity_id=entity_id,
        item_id=item_id,
        item_type=previous_item.get("type", "unknown"),
        user=performed_by,
        old_value=previous_item,
    )

    await emit_event(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=RealtimeEventType.TIMELINE_ITEM_DELETED,
        performed_by=performed_by,
        item_id=item_id,
        item_type=previous_item.get("type"),
    )

    await db.commit()

    if cleanup.storage_key is not None:
        await _delete_storage_object_after_commit(
            cleanup.storage_key,
            action=f"removing {entity_type} timeline item {item_id}",
        )

    return previous_item
