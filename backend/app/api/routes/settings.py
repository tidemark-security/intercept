"""
Settings API routes for application configuration management.

Provides CRUD operations for app settings with ADMIN-only access for mutations.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user
from app.core.database import get_db
from app.models.models import (
    AppSettingCreate,
    AppSettingUpdate,
    AppSettingRead,
    UserAccount,
)
from app.services.audit_service import AuditContext
from app.services.settings_service import SettingsService

router = APIRouter(
    prefix="/admin/settings",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
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
    service = SettingsService(db)  # type: ignore[arg-type]
    audit_context = AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-correlation-id"),
    )
    
    try:
        return await service.create_setting(
            setting,
            performed_by=current_user.username,
            audit_context=audit_context,
        )
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_409_CONFLICT
            if "already exists" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)


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
    service = SettingsService(db)  # type: ignore[arg-type]
    audit_context = AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-correlation-id"),
    )
    
    try:
        return await service.update_setting(
            key,
            setting_update,
            performed_by=current_user.username,
            audit_context=audit_context,
        )
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)


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
    audit_context = AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-correlation-id"),
    )
    
    try:
        deleted = await service.delete_setting(
            key,
            performed_by=current_user.username,
            audit_context=audit_context,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found"
        )
    
    return None
