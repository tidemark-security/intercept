"""Persistence for personal and organization-wide queue filters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.enums import AuditEventType, RealtimeEventType
from app.models.models import SavedQueueFilter, UserAccount
from app.models.saved_filter_schemas import (
    SavedFilterCreate,
    SavedFilterQueue,
    SavedFilterRead,
    SavedFilterScope,
)
from app.services.audit_service import AuditContext, get_audit_service
from app.services.realtime_service import emit_event


_NAVIGATION_ORDER_LOCK = 0x534156454450494E  # SAVEDPIN


class NavigationOrderConflict(Exception):
    """The requested order no longer matches the set of pinned filters."""


def _pinned_alert_filters_query():
    return (
        select(SavedQueueFilter)
        .where(col(SavedQueueFilter.navigation_position).is_not(None))
        .order_by(SavedQueueFilter.navigation_position)
    )


async def list_pinned_alert_filters(db: AsyncSession) -> Sequence[SavedQueueFilter]:
    return (await db.scalars(_pinned_alert_filters_query())).all()


async def _lock_navigation_order(db: AsyncSession) -> None:
    # Pinning and reordering must serialize, including when the pinned list is empty.
    await db.execute(select(func.pg_advisory_xact_lock(_NAVIGATION_ORDER_LOCK)))


async def _notify_navigation_change(db: AsyncSession, actor: UserAccount) -> None:
    await emit_event(
        db,
        entity_type="saved_filter_navigation",
        entity_id=0,  # The event invalidates the shared list, independent of any filter ID.
        event_type=RealtimeEventType.SAVED_FILTER_NAVIGATION_UPDATED,
        performed_by=actor.username,
    )


def _visible_to(user_id: UUID):
    owner_id = col(SavedQueueFilter.owner_id)
    return or_(owner_id.is_(None), owner_id == user_id)


def _audit_snapshot(saved_filter: SavedQueueFilter) -> dict[str, str | int]:
    # Filter criteria can contain sensitive search terms and investigation data.
    snapshot: dict[str, str | int] = {"name": saved_filter.name, "queue": saved_filter.queue, "scope": saved_filter.scope}
    if saved_filter.navigation_icon is not None:
        snapshot["navigation_icon"] = saved_filter.navigation_icon
    if saved_filter.navigation_position is not None:
        snapshot["navigation_position"] = saved_filter.navigation_position
    return snapshot


async def _audit_saved_filter_change(
    db: AsyncSession,
    saved_filter: SavedQueueFilter,
    event: AuditEventType,
    *,
    actor: UserAccount,
    context: AuditContext,
    before: dict[str, str | int] | None = None,
    after: dict[str, str | int] | None = None,
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
    if saved_filter.navigation_position is not None:
        await _notify_navigation_change(db, actor)
    await db.commit()
    return result


async def set_saved_filter_navigation(
    db: AsyncSession,
    filter_id: UUID,
    icon_name: str | None,
    *,
    actor: UserAccount,
    audit_context: AuditContext,
) -> SavedFilterRead | None:
    await _lock_navigation_order(db)
    saved_filter = await get_visible_saved_filter_for_update(db, filter_id, actor.id)
    if (
        saved_filter is None
        or saved_filter.scope != SavedFilterScope.ORGANIZATION
        or saved_filter.queue != SavedFilterQueue.ALERTS
    ):
        return None
    if saved_filter.navigation_icon == icon_name:
        return SavedFilterRead.model_validate(saved_filter)
    before = _audit_snapshot(saved_filter)
    if icon_name is None:
        saved_filter.navigation_position = None
    elif saved_filter.navigation_position is None:
        last_position = await db.scalar(select(func.max(SavedQueueFilter.navigation_position)))
        saved_filter.navigation_position = 0 if last_position is None else last_position + 1
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
    await _notify_navigation_change(db, actor)
    await db.commit()
    return result


async def set_navigation_order(
    db: AsyncSession,
    filter_ids: list[UUID],
    *,
    actor: UserAccount,
    audit_context: AuditContext,
) -> None:
    await _lock_navigation_order(db)
    pinned = (await db.scalars(_pinned_alert_filters_query().with_for_update())).all()
    by_id = {entry.id: entry for entry in pinned}
    if len(filter_ids) != len(by_id) or set(filter_ids) != by_id.keys():
        raise NavigationOrderConflict
    if list(by_id) == filter_ids:
        return

    # Keep the current position slots even if unpinning or deleting left gaps.
    positions = [entry.navigation_position for entry in pinned]
    for filter_id, position in zip(filter_ids, positions, strict=True):
        entry = by_id[filter_id]
        if entry.navigation_position == position:
            continue
        before = _audit_snapshot(entry)
        entry.navigation_position = position
        await _audit_saved_filter_change(
            db,
            entry,
            AuditEventType.SAVED_FILTER_NAVIGATION_UPDATED,
            actor=actor,
            context=audit_context,
            before=before,
            after=_audit_snapshot(entry),
        )
    await _notify_navigation_change(db, actor)
    await db.commit()


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
    if saved_filter.navigation_position is not None:
        await _notify_navigation_change(db, actor)
    await db.commit()
