from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin_auth import require_admin_user
from app.core.database import get_db
from app.models.models import QueueJobsPage, QueueStatsRead
from app.services.queue_status_service import QueueStatusService

router = APIRouter(
    prefix="/admin/queue",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


@router.get("/jobs", response_model=QueueJobsPage)
async def get_queue_jobs(
    entrypoint: Optional[str] = Query(None, description="Filter by task entrypoint name"),
    status: Optional[str] = Query(None, description="Filter by job status (queued, picked, successful, exception, canceled)"),
    start_date: Optional[datetime] = Query(None, description="Filter jobs created after this UTC datetime"),
    end_date: Optional[datetime] = Query(None, description="Filter jobs created before this UTC datetime"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated queue jobs with optional filters."""
    service = QueueStatusService(db)
    return await service.get_jobs(
        entrypoint=entrypoint,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        size=size,
    )


@router.get("/stats", response_model=List[QueueStatsRead])
async def get_queue_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate job counts grouped by entrypoint and status."""
    service = QueueStatusService(db)
    return await service.get_stats()


@router.get("/entrypoints", response_model=List[str])
async def list_queue_entrypoints(
    db: AsyncSession = Depends(get_db),
):
    """List distinct entrypoint names for filter dropdowns."""
    service = QueueStatusService(db)
    return await service.get_entrypoints()
