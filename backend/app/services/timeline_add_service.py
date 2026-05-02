from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.enums import RealtimeEventType
from app.models.models import Alert, Case, Task
from app.services.audit_service import get_audit_service
from app.services.realtime_service import emit_event
from app.services.timeline_service import timeline_service


async def _load_entity_for_timeline_update(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: int,
) -> Any | None:
    normalized_type = entity_type.lower()
    if normalized_type == "case":
        stmt = select(Case).where(Case.id == entity_id).with_for_update()
    elif normalized_type == "alert":
        stmt = select(Alert).where(Alert.id == entity_id).with_for_update()
    elif normalized_type == "task":
        stmt = select(Task).where(Task.id == entity_id).with_for_update()
    else:
        raise ValueError(f"Unsupported entity type for timeline update: {entity_type}")

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def add_timeline_item_and_commit(
    db: AsyncSession,
    *,
    entity: Any,
    entity_id: int,
    entity_type: str,
    timeline_item: Any,
    performed_by: str,
    validate_item: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    entity = await _load_entity_for_timeline_update(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if entity is None:
        raise ValueError(f"{entity_type} {entity_id} not found")

    item_dict = timeline_item.model_dump(mode="json")

    if validate_item is not None:
        validate_item(item_dict)

    item_dict, enrichment_priority = await timeline_service.add_timeline_item_with_sync(
        db,
        entity,
        item_dict,
        performed_by,
        entity_id=entity_id,
        entity_type=entity_type,
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

    await get_audit_service(db).log_timeline_item_added(
        entity_type=entity_type,
        entity_id=entity_id,
        item_id=item_dict.get("id", ""),
        item_type=item_dict.get("type", "unknown"),
        user=performed_by,
        new_value=item_dict,
    )

    return item_dict


async def update_timeline_item_and_commit(
    db: AsyncSession,
    *,
    entity: Any,
    entity_id: int,
    entity_type: str,
    item_id: str,
    existing_item: dict[str, Any],
    timeline_item: Any,
    performed_by: str,
) -> Optional[dict[str, Any]]:
    entity = await _load_entity_for_timeline_update(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if entity is None:
        return None

    previous_item = deepcopy(existing_item)
    item_dict = timeline_item.model_dump(mode="json")

    result = await timeline_service.update_timeline_item_with_sync(
        db,
        entity,
        item_id,
        item_dict,
        performed_by,
    )
    if result is None:
        return None

    updated_item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id) or item_dict

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

    await db.commit()

    if enrichment_priority is not None:
        await enrichment_service.enqueue_prepared_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            priority=enrichment_priority,
            raise_on_error=False,
        )

    return updated_item