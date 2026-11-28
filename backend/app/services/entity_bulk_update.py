from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Alert, Case, Task
from app.services.audit_service import get_audit_service
from app.services.timeline_service import timeline_service


class BulkEntityNotFoundError(ValueError):
    """The batch contains an entity that no longer exists."""


async def add_bulk_analyst_note(
    db: AsyncSession,
    entity: Alert | Case | Task,
    entity_type: Literal["alert", "case", "task"],
    note: str,
    user: str,
) -> None:
    assert entity.id is not None
    now = datetime.now(timezone.utc)
    item = timeline_service.build_note_item(
        description=note, created_by=user, timestamp=now, tags=["bulk-action"]
    )
    timeline_service.add_timeline_item(entity, item, created_by=user)
    await get_audit_service(db).log_timeline_item_added(
        entity_type=entity_type,
        entity_id=entity.id,
        item_id=item["id"],
        item_type="note",
        user=user,
        new_value=item,
    )


async def run_bulk_update(
    db: AsyncSession,
    entity_ids: Iterable[int],
    entity_type: Literal["case", "task"],
    note: str | None,
    user: str,
    update: Callable[[int], Awaitable[Case | Task | None]],
    *,
    prepare: Callable[[list[int]], Awaitable[None]] | None = None,
) -> int:
    ids = sorted(set(entity_ids))
    text = (note or "").strip()
    try:
        if prepare is not None:
            await prepare(ids)
        # Acquire locks in the same order for overlapping batches.
        for entity_id in ids:
            entity = await update(entity_id)
            if entity is None:
                raise BulkEntityNotFoundError(f"{entity_type.capitalize()} {entity_id} not found")
            if text:
                await add_bulk_analyst_note(db, entity, entity_type, text, user)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return len(ids)
