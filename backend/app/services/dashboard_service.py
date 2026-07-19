"""
Dashboard Service

Provides aggregated statistics for the dashboard homepage.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case as sql_case
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.entity_ids import ALERT_PREFIX, CASE_PREFIX, TASK_PREFIX, format_entity_id
from app.models.enums import AlertStatus, CaseStatus, TaskStatus, Priority
from app.models.models import Alert, Case, Task


_DASHBOARD_ITEM_METADATA = {
    Alert: (ALERT_PREFIX, "alert", "NEW"),
    Case: (CASE_PREFIX, "case", "NEW"),
    Task: (TASK_PREFIX, "task", "TODO"),
}

_OPEN_ITEM_STATUSES = {
    Alert: (AlertStatus.NEW, AlertStatus.IN_PROGRESS),
    Case: (CaseStatus.NEW, CaseStatus.IN_PROGRESS),
    Task: (TaskStatus.TODO, TaskStatus.IN_PROGRESS),
}

_PRIORITY_ORDER = {
    Priority.EXTREME: 5,
    Priority.CRITICAL: 4,
    Priority.HIGH: 3,
    Priority.MEDIUM: 2,
    Priority.LOW: 1,
    Priority.INFO: 0,
}

_ITEM_TYPE_ORDER = {
    "alert": 0,
    "task": 1,
    "case": 2,
}


def _serialize_dashboard_item(item: Alert | Case | Task) -> Dict[str, Any]:
    """Map a work item to the shared dashboard response shape."""
    prefix, item_type, default_status = _DASHBOARD_ITEM_METADATA[type(item)]
    return {
        "id": item.id,
        "human_id": format_entity_id(item.id, prefix),
        "title": item.title,
        "item_type": item_type,
        "priority": item.priority,
        "status": item.status.value if item.status else default_status,
        "updated_at": item.updated_at,
    }


async def _count_entities(
    db: AsyncSession,
    model: type[Alert] | type[Case] | type[Task],
    *criteria: Any,
) -> int:
    """Count entities matching the supplied SQL criteria."""
    result = await db.execute(select(func.count(model.id)).where(*criteria))
    return result.scalar() or 0


async def _fetch_dashboard_items(
    db: AsyncSession,
    model: type[Alert] | type[Case] | type[Task],
    *,
    criteria: tuple[Any, ...] = (),
    order_by: tuple[Any, ...],
    limit: int,
) -> List[Dict[str, Any]]:
    """Fetch and serialize one bounded entity partition."""
    query = (
        select(model)
        .where(*criteria)
        .order_by(*order_by)
        .limit(limit)
    )
    result = await db.execute(query)
    return [_serialize_dashboard_item(item) for item in result.scalars().all()]


def _priority_query_order(
    model: type[Alert] | type[Case] | type[Task],
) -> tuple[Any, ...]:
    """Return the per-entity ordering required for a correct global top-N."""
    priority_rank = sql_case(
        _PRIORITY_ORDER,
        value=model.priority,
        else_=0,
    )
    return (
        priority_rank.desc(),
        col(model.updated_at).desc().nulls_last(),
    )


def _priority_sort_key(item: Dict[str, Any]) -> tuple[int, int, float]:
    """Apply the dashboard's public priority, type, and recency ordering."""
    priority = item["priority"]
    updated_at = item["updated_at"]
    return (
        -_PRIORITY_ORDER.get(priority, 0) if priority else 0,
        _ITEM_TYPE_ORDER.get(item["item_type"], 99),
        -updated_at.timestamp() if updated_at else 0,
    )


@dataclass(slots=True)
class DashboardStats:
    """Dashboard statistics container."""

    unacknowledged_alerts: int = 0
    open_tasks: int = 0
    assigned_cases: int = 0
    tasks_due_today: int = 0
    critical_cases: int = 0


class DashboardService:
    """Service for dashboard statistics."""

    async def get_sidebar_badge_counts(self, db: AsyncSession) -> Dict[str, Dict[str, int]]:
        """Get open and unassigned counts for sidebar badges."""
        alert_open_statuses = [
            AlertStatus.NEW,
            AlertStatus.IN_PROGRESS,
        ]
        case_open_statuses = [CaseStatus.NEW, CaseStatus.IN_PROGRESS]
        task_open_statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS]

        return {
            "alerts": {
                "open": await _count_entities(
                    db,
                    Alert,
                    col(Alert.status).in_(alert_open_statuses),
                ),
                "unassigned": await _count_entities(
                    db,
                    Alert,
                    col(Alert.status).in_(alert_open_statuses),
                    Alert.assignee.is_(None),
                ),
            },
            "cases": {
                "open": await _count_entities(
                    db,
                    Case,
                    col(Case.status).in_(case_open_statuses),
                ),
                "unassigned": await _count_entities(
                    db,
                    Case,
                    col(Case.status).in_(case_open_statuses),
                    Case.assignee.is_(None),
                ),
            },
            "tasks": {
                "open": await _count_entities(
                    db,
                    Task,
                    col(Task.status).in_(task_open_statuses),
                ),
                "unassigned": await _count_entities(
                    db,
                    Task,
                    col(Task.status).in_(task_open_statuses),
                    Task.assignee.is_(None),
                ),
            },
        }
    
    async def get_dashboard_stats(
        self, 
        db: AsyncSession, 
        username: Optional[str] = None
    ) -> DashboardStats:
        """Get dashboard statistics for the current user.
        
        Args:
            db: Database session
            username: If provided, filter stats to this user's assignments
        """
        assignee_criteria = (Task.assignee == username,) if username else ()
        case_assignee_criteria = (Case.assignee == username,) if username else ()
        task_open = col(Task.status).in_(_OPEN_ITEM_STATUSES[Task])
        case_open = col(Case.status).in_(_OPEN_ITEM_STATUSES[Case])
        today_start = datetime.now(timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        today_end = today_start + timedelta(days=1)

        return DashboardStats(
            # NEW alerts are awaiting triage and are not user-filtered.
            unacknowledged_alerts=await _count_entities(
                db,
                Alert,
                Alert.status == AlertStatus.NEW,
            ),
            open_tasks=await _count_entities(
                db,
                Task,
                task_open,
                *assignee_criteria,
            ),
            assigned_cases=await _count_entities(
                db,
                Case,
                case_open,
                *case_assignee_criteria,
            ),
            tasks_due_today=await _count_entities(
                db,
                Task,
                task_open,
                col(Task.due_date) >= today_start,
                col(Task.due_date) < today_end,
                *assignee_criteria,
            ),
            critical_cases=await _count_entities(
                db,
                Case,
                case_open,
                col(Case.priority).in_([Priority.CRITICAL, Priority.EXTREME]),
                *case_assignee_criteria,
            ),
        )

    async def get_recent_items(
        self,
        db: AsyncSession,
        username: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recently updated items across alerts, cases, and tasks.
        
        Args:
            db: Database session
            username: If provided, filter to this user's assignments
            limit: Maximum number of items to return
        """
        items: List[Dict[str, Any]] = []
        for model in (Alert, Case, Task):
            criteria = (model.assignee == username,) if username else ()
            items.extend(
                await _fetch_dashboard_items(
                    db,
                    model,
                    criteria=criteria,
                    order_by=(col(model.updated_at).desc().nulls_last(),),
                    limit=limit,
                )
            )

        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items[:limit]

    async def get_priority_items(
        self,
        db: AsyncSession,
        username: str,
        limit: int = 100
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Get open items assigned to current user, sorted by priority.
        
        Args:
            db: Database session
            username: Current user's username
            limit: Maximum number of items to return
            
        Returns:
            Tuple of (items list, truncated flag)
        """
        items: List[Dict[str, Any]] = []
        # A global top-N can contain at most N items from any one entity type.
        # Fetching N+1 from each correctly ordered partition is therefore enough
        # both to build the result and to detect truncation.
        for model in (Alert, Case, Task):
            items.extend(
                await _fetch_dashboard_items(
                    db,
                    model,
                    criteria=(
                        model.assignee == username,
                        col(model.status).in_(_OPEN_ITEM_STATUSES[model]),
                    ),
                    order_by=_priority_query_order(model),
                    limit=limit + 1,
                )
            )

        items.sort(key=_priority_sort_key)
        return items[:limit], len(items) > limit


dashboard_service = DashboardService()
