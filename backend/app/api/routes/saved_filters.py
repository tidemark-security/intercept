"""Manage reusable queue filters with account and administrator authorization."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.request_metadata import build_audit_context
from app.api.routes.admin_auth import (
    require_admin_user,
    require_authenticated_user,
    require_shared_authentication,
)
from app.core.database import get_db
from app.models.models import SavedQueueFilter, UserAccount
from app.models.saved_filter_schemas import (
    SavedFilterCreate,
    SavedFilterQueue,
    SavedFilterRead,
    SavedFilterRename,
    SavedFilterScope,
)
from app.services import saved_filter_service


router = APIRouter(prefix="/saved-filters", tags=["saved-filters"])


@router.get("", operation_id="listSavedFilters", response_model=list[SavedFilterRead])
async def list_saved_filters(
    queue: SavedFilterQueue,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_authenticated_user),
) -> list[SavedFilterRead]:
    """List the user's personal filters and organization filters for one queue."""
    return await saved_filter_service.list_saved_filters(db, queue, user.id)


@router.post(
    "",
    operation_id="createSavedFilter",
    response_model=SavedFilterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_saved_filter(
    payload: SavedFilterCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_shared_authentication),
) -> SavedFilterRead:
    """Create a saved filter in the selected scope."""
    if payload.scope == SavedFilterScope.ORGANIZATION:
        await require_admin_user(request, user)
    return await saved_filter_service.create_saved_filter(
        db, payload, actor=user, audit_context=build_audit_context(request)
    )


async def _get_saved_filter_for_edit(
    filter_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_shared_authentication),
) -> SavedQueueFilter:
    saved_filter = await saved_filter_service.get_visible_saved_filter_for_update(db, filter_id, user.id)
    if saved_filter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved filter not found")
    if saved_filter.scope == SavedFilterScope.ORGANIZATION:
        await require_admin_user(request, user)
    return saved_filter


@router.patch("/{filter_id}", operation_id="renameSavedFilter", response_model=SavedFilterRead)
async def rename_saved_filter(
    payload: SavedFilterRename,
    request: Request,
    saved_filter: SavedQueueFilter = Depends(_get_saved_filter_for_edit),
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_shared_authentication),
) -> SavedFilterRead:
    """Rename a saved filter."""
    return await saved_filter_service.rename_saved_filter(
        db, saved_filter, payload.name, actor=user, audit_context=build_audit_context(request)
    )


@router.delete("/{filter_id}", operation_id="deleteSavedFilter", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_filter(
    request: Request,
    saved_filter: SavedQueueFilter = Depends(_get_saved_filter_for_edit),
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_shared_authentication),
) -> None:
    """Delete a saved filter."""
    await saved_filter_service.delete_saved_filter(
        db, saved_filter, actor=user, audit_context=build_audit_context(request)
    )
