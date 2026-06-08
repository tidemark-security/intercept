"""Routes for analyst-editable context entries."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_authenticated_user, require_non_auditor_user
from app.core.database import get_db
from app.models.models import (
    ContextEntryCreate,
    ContextEntryRead,
    ContextEntryUpdate,
    UserAccount,
)
from app.services.audit_service import AuditContext
from app.services.context_service import ContextService


router = APIRouter(
    prefix="/context-entries",
    tags=["context-entries"],
    dependencies=[Depends(require_authenticated_user)],
)


def _audit_context(request: Request) -> AuditContext:
    return AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-correlation-id"),
    )


@router.get("", response_model=List[ContextEntryRead])
async def list_context_entries(
    include_expired: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> List[ContextEntryRead]:
    """List shared context entries."""
    return await ContextService(db).list_entries(include_expired=include_expired)


@router.post("", response_model=ContextEntryRead, status_code=status.HTTP_201_CREATED)
async def create_context_entry(
    request: Request,
    payload: ContextEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> ContextEntryRead:
    """Create shared context."""
    try:
        return await ContextService(db).create_entry(
            payload,
            author=current_user.username,
            audit_context=_audit_context(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/{entry_id}", response_model=ContextEntryRead)
async def update_context_entry(
    entry_id: int,
    request: Request,
    payload: ContextEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> ContextEntryRead:
    """Edit shared context."""
    try:
        return await ContextService(db).update_entry(
            entry_id,
            payload,
            updated_by=current_user.username,
            audit_context=_audit_context(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{entry_id}/expire", response_model=ContextEntryRead)
async def expire_context_entry(
    entry_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> ContextEntryRead:
    """Expire shared context immediately."""
    return await ContextService(db).expire_entry(
        entry_id,
        expired_by=current_user.username,
        audit_context=_audit_context(request),
    )
