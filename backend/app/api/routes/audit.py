from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.enums import AuditEventType
from app.models.models import AuditLogRead
from app.services.audit_service import AuditService
from app.api.routes.admin_auth import require_admin_user

router = APIRouter(
    prefix="/admin/audit",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


@router.get("", response_model=Page[AuditLogRead])
async def get_audit_logs(
    event_type: Optional[list[str]] = Query(None, description="Filter by one or more audit event types"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    performed_by: Optional[str] = Query(None, description="Filter by actor username or identifier"),
    search: Optional[str] = Query(None, description="Search event type, description, entity ID, or actor"),
    start_date: Optional[str] = Query(None, description="Filter events performed after this UTC datetime"),
    end_date: Optional[str] = Query(None, description="Filter events performed before this UTC datetime"),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated audit logs for admin users."""

    try:
        audit_service = AuditService(db)
        return await audit_service.get_audit_logs(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            performed_by=performed_by,
            search=search,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching audit logs: {exc}") from exc


@router.get("/event-types", response_model=list[str])
async def list_audit_event_types() -> list[str]:
    """List supported audit event types for filter UIs."""

    return sorted(event_type.value for event_type in AuditEventType)