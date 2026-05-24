"""Routes for analyst-editable AI triage context."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_authenticated_user, require_non_auditor_user
from app.core.database import get_db
from app.models.models import (
    AITriageContextEntryCreate,
    AITriageContextEntryRead,
    AITriageContextEntryUpdate,
    UserAccount,
)
from app.services.ai_triage_context_service import AITriageContextService
from app.services.audit_service import AuditContext


router = APIRouter(
    prefix="/ai-triage-context",
    tags=["ai-triage-context"],
    dependencies=[Depends(require_authenticated_user)],
)


def _audit_context(request: Request) -> AuditContext:
    return AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-correlation-id"),
    )


@router.get("", response_model=List[AITriageContextEntryRead])
async def list_ai_triage_context(
    include_expired: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> List[AITriageContextEntryRead]:
    """List shared AI triage context entries."""
    return await AITriageContextService(db).list_entries(include_expired=include_expired)


@router.post("", response_model=AITriageContextEntryRead, status_code=status.HTTP_201_CREATED)
async def create_ai_triage_context(
    request: Request,
    payload: AITriageContextEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> AITriageContextEntryRead:
    """Create shared AI triage context."""
    try:
        return await AITriageContextService(db).create_entry(
            payload,
            author=current_user.username,
            audit_context=_audit_context(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/{entry_id}", response_model=AITriageContextEntryRead)
async def update_ai_triage_context(
    entry_id: int,
    request: Request,
    payload: AITriageContextEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> AITriageContextEntryRead:
    """Edit shared AI triage context."""
    try:
        return await AITriageContextService(db).update_entry(
            entry_id,
            payload,
            updated_by=current_user.username,
            audit_context=_audit_context(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{entry_id}/expire", response_model=AITriageContextEntryRead)
async def expire_ai_triage_context(
    entry_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> AITriageContextEntryRead:
    """Expire shared AI triage context immediately."""
    return await AITriageContextService(db).expire_entry(
        entry_id,
        expired_by=current_user.username,
        audit_context=_audit_context(request),
    )
