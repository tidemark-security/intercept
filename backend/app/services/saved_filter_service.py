"""Persistence for personal and organization-wide queue filters."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.models import SavedQueueFilter
from app.models.saved_filter_schemas import (
    SavedFilterCreate,
    SavedFilterQueue,
    SavedFilterRead,
    SavedFilterScope,
)


def _visible_to(user_id: UUID):
    owner_id = col(SavedQueueFilter.owner_id)
    return or_(owner_id.is_(None), owner_id == user_id)


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
    db: AsyncSession, payload: SavedFilterCreate, user_id: UUID
) -> SavedFilterRead:
    saved_filter = SavedQueueFilter(
        queue=payload.queue.value,
        name=payload.name,
        scope=payload.scope.value,
        owner_id=user_id if payload.scope == SavedFilterScope.PERSONAL else None,
        filters=payload.filters.model_dump(mode="json"),
    )
    db.add(saved_filter)
    result = SavedFilterRead.model_validate(saved_filter)
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
    db: AsyncSession, saved_filter: SavedQueueFilter, name: str
) -> SavedFilterRead:
    saved_filter.name = name
    result = SavedFilterRead.model_validate(saved_filter)
    await db.commit()
    return result


async def delete_saved_filter(db: AsyncSession, saved_filter: SavedQueueFilter) -> None:
    await db.delete(saved_filter)
    await db.commit()
