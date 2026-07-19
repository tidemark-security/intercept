"""
Settings API routes for application configuration management.

Provides CRUD operations for app settings with ADMIN-only access for mutations.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.request_metadata import build_audit_context
from app.api.routes.admin_auth import require_admin_user
from app.api.routes.admin_auth import require_authenticated_user
from app.core.database import get_db
from app.models.models import (
    AttachmentLimitsRead,
    AppSettingCreate,
    AppSettingRead,
    AppSettingUpdate,
    UserAccount,
)
from app.services.attachment_settings_service import get_attachment_limits
from app.services.enrichment.bulk_sync_schedule_sync import (
    BulkSyncScheduleValueError,
    cron_expression_for_utc_time,
    enqueue_bulk_sync_schedule_refresh,
    get_bulk_sync_provider_id_from_setting_key,
)
from app.services.settings_service import (
    SettingConflictError,
    SettingNotFoundError,
    SettingValidationError,
    SettingsService,
)

authenticated_router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_authenticated_user)],
)

router = APIRouter(
    prefix="/admin/settings",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


async def _enqueue_bulk_sync_schedule_refresh_if_needed(key: str) -> None:
    provider_id = get_bulk_sync_provider_id_from_setting_key(key)
    if provider_id is None:
        return
    await enqueue_bulk_sync_schedule_refresh(provider_id)


def _validate_bulk_sync_setting_value(key: str, value: str | None) -> None:
    if not key.endswith(".bulk_sync_time_utc"):
        return

    normalized = (value or "").strip()
    if not normalized:
        return

    cron_expression_for_utc_time(normalized)


async def _write_setting(
    *,
    request: Request,
    key: str,
    setting: AppSettingCreate | AppSettingUpdate,
    current_user: UserAccount,
    db: AsyncSession,
) -> AppSettingRead:
    """Run the shared route protocol for creating or updating a setting."""
    service = SettingsService(db)  # type: ignore[arg-type]
    audit_context = build_audit_context(request)

    try:
        _validate_bulk_sync_setting_value(key, setting.value)
    except BulkSyncScheduleValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        if isinstance(setting, AppSettingCreate):
            result = await service.create_setting(
                setting,
                performed_by=current_user.username,
                audit_context=audit_context,
            )
        else:
            result = await service.update_setting(
                key,
                setting,
                performed_by=current_user.username,
                audit_context=audit_context,
            )
    except SettingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SettingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SettingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await _enqueue_bulk_sync_schedule_refresh_if_needed(key)
    return result


@authenticated_router.get("/attachment-limits", response_model=AttachmentLimitsRead)
async def get_attachment_limits_settings(
    db: AsyncSession = Depends(get_db),
):
    """Get effective attachment upload and preview limits for authenticated users."""
    limits = await get_attachment_limits(db)  # type: ignore[arg-type]
    return AttachmentLimitsRead(
        max_upload_size_mb=limits.max_upload_size_mb,
        max_upload_size_bytes=limits.max_upload_size_bytes,
        max_image_preview_size_mb=limits.max_image_preview_size_mb,
        max_image_preview_size_bytes=limits.max_image_preview_size_bytes,
        max_text_preview_size_mb=limits.max_text_preview_size_mb,
        max_text_preview_size_bytes=limits.max_text_preview_size_bytes,
    )


@router.get("", response_model=List[AppSettingRead])
async def get_all_settings(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all application settings.
    
    - **category**: Optional category filter
    
    Requires ADMIN role.
    Returns settings with secret values masked.
    Environment variables take precedence over database values.
    """
    service = SettingsService(db)  # type: ignore[arg-type]
    return await service.get_all_settings(category=category, include_secrets=False)


@router.get("/{key}", response_model=AppSettingRead)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single setting by key.
    
    Requires ADMIN role.
    Returns setting with secret value masked.
    Environment variables take precedence over database values.
    """
    service = SettingsService(db)  # type: ignore[arg-type]
    setting = await service.get_setting(key, include_secret=False)
    
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found"
        )
    
    return setting


@router.post("", response_model=AppSettingRead, status_code=status.HTTP_201_CREATED)
async def create_setting(
    request: Request,
    setting: AppSettingCreate,
    current_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new setting.
    
    Requires ADMIN role.
    Secret values will be encrypted automatically.
    Returns created setting with secret value masked.
    """
    return await _write_setting(
        request=request,
        key=setting.key,
        setting=setting,
        current_user=current_user,
        db=db,
    )


@router.put("/{key}", response_model=AppSettingRead)
async def update_setting(
    request: Request,
    key: str,
    setting_update: AppSettingUpdate,
    current_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing setting.
    
    Requires ADMIN role.
    Only value and description can be updated.
    Secret values will be encrypted automatically.
    Returns updated setting with secret value masked.
    """
    return await _write_setting(
        request=request,
        key=key,
        setting=setting_update,
        current_user=current_user,
        db=db,
    )


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    request: Request,
    key: str,
    current_user: UserAccount = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a setting.
    
    Requires ADMIN role.
    Returns 204 No Content on success.
    """
    service = SettingsService(db)  # type: ignore[arg-type]
    audit_context = build_audit_context(request)
    
    try:
        deleted = await service.delete_setting(
            key,
            performed_by=current_user.username,
            audit_context=audit_context,
        )
    except SettingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found"
        )

    await _enqueue_bulk_sync_schedule_refresh_if_needed(key)
    
    return None
