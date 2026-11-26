"""Persistence for personal and organization-wide queue filters."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.enums import AuditEventType
from app.models.models import SavedQueueFilter, UserAccount
from app.models.saved_filter_schemas import (
    SavedFilterCreate,
    SavedFilterQueue,
    SavedFilterRead,
    SavedFilterScope,
)
from app.services.audit_service import AuditContext, get_audit_service


def _visible_to(user_id: UUID):
    owner_id = col(SavedQueueFilter.owner_id)
    return or_(owner_id.is_(None), owner_id == user_id)


def _audit_snapshot(saved_filter: SavedQueueFilter) -> dict[str, str]:
    # Filter criteria can contain sensitive search terms and investigation data.
    snapshot = {"name": saved_filter.name, "queue": saved_filter.queue, "scope": saved_filter.scope}
    if saved_filter.navigation_icon is not None:
        snapshot["navigation_icon"] = saved_filter.navigation_icon
    return snapshot


async def _audit_saved_filter_change(
    db: AsyncSession,
    saved_filter: SavedQueueFilter,
    event: AuditEventType,
    *,
    actor: UserAccount,
    context: AuditContext,
    before: dict[str, str] | None = None,
    after: dict[str, str] | None = None,
) -> None:
    # Audit records have narrower columns than usernames and request headers.
    actor_name = actor.username if len(actor.username) <= 100 else str(actor.id)
    if context.correlation_id is not None and len(context.correlation_id) > 255:
        context = replace(context, correlation_id=context.correlation_id[:255])
    await get_audit_service(db).log_event(
        event_type=event.value,
        entity_type="saved_filter",
        entity_id=str(saved_filter.id),
        description=f"Saved filter {event.value.rsplit('.', 1)[-1]}",
        old_value=before,
        new_value=after,
        performed_by=actor_name,
        context=context,
    )


async def list_saved_filters(
    db: AsyncSession, queue: SavedFilterQueue, user_id: UUID
) -> list[SavedFilterRead]:
    result = await db.scalars(
        select(SavedQueueFilter)
        .where(SavedQueueFilter.queue == queue.value, _visible_to(user_id))
        .order_by(SavedQueueFilter.name, SavedQueueFilter.id)
    )
    return [SavedFilterRead.model_validate(saved_filter) for saved_filter in result]


async def create_saved_filter(
    db: AsyncSession,
    payload: SavedFilterCreate,
    *,
    actor: UserAccount,
    audit_context: AuditContext,
) -> SavedFilterRead:
    saved_filter = SavedQueueFilter(
        queue=payload.queue.value,
        name=payload.name,
        scope=payload.scope.value,
        owner_id=actor.id if payload.scope == SavedFilterScope.PERSONAL else None,
        filters=payload.filters.model_dump(mode="json"),
    )
    db.add(saved_filter)
    result = SavedFilterRead.model_validate(saved_filter)
    await _audit_saved_filter_change(
        db,
        saved_filter,
        AuditEventType.SAVED_FILTER_CREATED,
        actor=actor,
        context=audit_context,
        after=_audit_snapshot(saved_filter),
    )
    await db.commit()
    return result


async def get_visible_saved_filter_for_update(
    db: AsyncSession, filter_id: UUID, user_id: UUID
) -> SavedQueueFilter | None:
    return await db.scalar(
        select(SavedQueueFilter)
        .where(SavedQueueFilter.id == filter_id, _visible_to(user_id))
        .with_for_update()
    )


async def rename_saved_filter(
    db: AsyncSession,
    saved_filter: SavedQueueFilter,
    name: str,
    *,
    actor: UserAccount,
    audit_context: AuditContext,
) -> SavedFilterRead:
    if saved_filter.name == name:
        return SavedFilterRead.model_validate(saved_filter)
    before = _audit_snapshot(saved_filter)
    saved_filter.name = name
    result = SavedFilterRead.model_validate(saved_filter)
    await _audit_saved_filter_change(
        db,
        saved_filter,
        AuditEventType.SAVED_FILTER_RENAMED,
        actor=actor,
        context=audit_context,
        before=before,
        after=_audit_snapshot(saved_filter),
    )
    await db.commit()
    return result


async def set_saved_filter_navigation(
    db: AsyncSession,
    saved_filter: SavedQueueFilter,
    icon_name: str | None,
    *,
    actor: UserAccount,
    audit_context: AuditContext,
) -> SavedFilterRead:
    if saved_filter.navigation_icon == icon_name:
        return SavedFilterRead.model_validate(saved_filter)
    before = _audit_snapshot(saved_filter)
    saved_filter.navigation_icon = icon_name
    result = SavedFilterRead.model_validate(saved_filter)
    await _audit_saved_filter_change(
        db,
        saved_filter,
        AuditEventType.SAVED_FILTER_NAVIGATION_UPDATED,
        actor=actor,
        context=audit_context,
        before=before,
        after=_audit_snapshot(saved_filter),
    )
    await db.commit()
    return result


async def delete_saved_filter(
    db: AsyncSession,
    saved_filter: SavedQueueFilter,
    *,
    actor: UserAccount,
    audit_context: AuditContext,
) -> None:
    await db.delete(saved_filter)
    await _audit_saved_filter_change(
        db,
        saved_filter,
        AuditEventType.SAVED_FILTER_DELETED,
        actor=actor,
        context=audit_context,
        before=_audit_snapshot(saved_filter),
    )
    await db.commit()
