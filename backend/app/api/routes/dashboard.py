"""
Dashboard API Routes

Provides aggregated statistics for the dashboard homepage.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime
import logging

from app.core.database import get_db
from app.services.dashboard_service import dashboard_service
from app.models.models import UserAccount
from app.models.enums import Priority
from app.api.routes.admin_auth import require_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_authenticated_user)]
)


class DashboardStatsResponse(BaseModel):
    """Response model for dashboard statistics."""
    
    unacknowledged_alerts: int
    open_tasks: int
    assigned_cases: int
    tasks_due_today: int
    critical_cases: int


class RecentItem(BaseModel):
    """A recent item for the dashboard."""
    
    id: int
    human_id: str
    title: str
    item_type: Literal["alert", "case", "task"]
    priority: Optional[Priority] = None
    status: str
    updated_at: datetime


class RecentItemsResponse(BaseModel):
    """Response model for recent items."""
    
    items: List[RecentItem]
    truncated: bool = False


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    my_items: bool = Query(
        True,
        description="If true, filter stats to current user's assignments only"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Get dashboard statistics.
    
    Returns counts for:
    - Unacknowledged alerts (NEW status)
    - Open tasks (TODO or IN_PROGRESS)
    - Assigned cases (NEW or IN_PROGRESS)
    - Tasks due today
    - Critical cases (CRITICAL or EXTREME priority)
    
    If my_items=true (default), stats are filtered to current user's assignments.
    """
    try:
        username = current_user.username if my_items else None
        stats = await dashboard_service.get_dashboard_stats(db, username)
        
        return DashboardStatsResponse(
            unacknowledged_alerts=stats.unacknowledged_alerts,
            open_tasks=stats.open_tasks,
            assigned_cases=stats.assigned_cases,
            tasks_due_today=stats.tasks_due_today,
            critical_cases=stats.critical_cases,
        )
        
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard stats: {str(e)}")


@router.get("/recent", response_model=RecentItemsResponse)
async def get_recent_items(
    limit: int = Query(10, ge=1, le=50, description="Maximum number of items to return"),
    my_items: bool = Query(
        True,
        description="If true, filter to current user's assignments only"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Get recently updated items (alerts, cases, tasks).
    
    Returns items sorted by updated_at descending.
    If my_items=true (default), only items assigned to current user are returned.
    """
    try:
        username = current_user.username if my_items else None
        items = await dashboard_service.get_recent_items(db, username, limit)
        
        return RecentItemsResponse(items=items)
        
    except Exception as e:
        logger.error(f"Error fetching recent items: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching recent items: {str(e)}")


@router.get("/priority-items", response_model=RecentItemsResponse)
async def get_priority_items(
    limit: int = Query(100, ge=1, le=100, description="Maximum number of items to return"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Get open items assigned to current user (My Open Items).
    
    Returns all open alerts, cases, and tasks assigned to the current user,
    sorted by priority (highest first), then by type (alerts, tasks, cases).
    This helps analysts see their workload prioritized.
    """
    try:
        items, truncated = await dashboard_service.get_priority_items(db, current_user.username, limit)
        
        return RecentItemsResponse(items=items, truncated=truncated)
        
    except Exception as e:
        logger.error(f"Error fetching priority items: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching priority items: {str(e)}")
