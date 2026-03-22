"""
Dashboard Service

Provides aggregated statistics for the dashboard homepage.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, union_all, literal
from sqlmodel import col
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging

from app.models.models import Alert, Case, Task
from app.models.enums import AlertStatus, CaseStatus, TaskStatus, Priority

logger = logging.getLogger(__name__)


class DashboardStats:
    """Dashboard statistics container."""
    
    def __init__(
        self,
        unacknowledged_alerts: int = 0,
        open_tasks: int = 0,
        assigned_cases: int = 0,
        tasks_due_today: int = 0,
        critical_cases: int = 0,
    ):
        self.unacknowledged_alerts = unacknowledged_alerts
        self.open_tasks = open_tasks
        self.assigned_cases = assigned_cases
        self.tasks_due_today = tasks_due_today
        self.critical_cases = critical_cases


class DashboardService:
    """Service for dashboard statistics."""
    
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
        try:
            # Count unacknowledged alerts (NEW status, no assignee)
            # These are alerts awaiting triage - not filtered by username
            unack_alerts_query = select(func.count(Alert.id)).where(
                Alert.status == AlertStatus.NEW
            )
            result = await db.execute(unack_alerts_query)
            unacknowledged_alerts = result.scalar() or 0
            
            # Count open tasks (TODO or IN_PROGRESS)
            open_tasks_query = select(func.count(Task.id)).where(
                col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
            )
            if username:
                open_tasks_query = open_tasks_query.where(
                    Task.assignee == username
                )
            result = await db.execute(open_tasks_query)
            open_tasks = result.scalar() or 0
            
            # Count assigned cases (NEW or IN_PROGRESS)
            cases_query = select(func.count(Case.id)).where(
                col(Case.status).in_([CaseStatus.NEW, CaseStatus.IN_PROGRESS])
            )
            if username:
                cases_query = cases_query.where(
                    Case.assignee == username
                )
            result = await db.execute(cases_query)
            assigned_cases = result.scalar() or 0
            
            # Count tasks due today
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            
            tasks_due_today_query = select(func.count(Task.id)).where(
                col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
                col(Task.due_date) >= today_start,
                col(Task.due_date) < today_end
            )
            if username:
                tasks_due_today_query = tasks_due_today_query.where(
                    Task.assignee == username
                )
            result = await db.execute(tasks_due_today_query)
            tasks_due_today = result.scalar() or 0
            
            # Count critical cases (CRITICAL or EXTREME priority, not closed)
            critical_cases_query = select(func.count(Case.id)).where(
                col(Case.status).in_([CaseStatus.NEW, CaseStatus.IN_PROGRESS]),
                col(Case.priority).in_([Priority.CRITICAL, Priority.EXTREME])
            )
            if username:
                critical_cases_query = critical_cases_query.where(
                    Case.assignee == username
                )
            result = await db.execute(critical_cases_query)
            critical_cases = result.scalar() or 0
            
            return DashboardStats(
                unacknowledged_alerts=unacknowledged_alerts,
                open_tasks=open_tasks,
                assigned_cases=assigned_cases,
                tasks_due_today=tasks_due_today,
                critical_cases=critical_cases,
            )
            
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            raise

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
        try:
            items = []
            
            # Fetch recent alerts
            alerts_query = select(Alert).order_by(col(Alert.updated_at).desc()).limit(limit)
            if username:
                alerts_query = alerts_query.where(Alert.assignee == username)
            result = await db.execute(alerts_query)
            for alert in result.scalars().all():
                items.append({
                    "id": alert.id,
                    "human_id": f"ALT-{alert.id:07d}",
                    "title": alert.title,
                    "item_type": "alert",
                    "priority": alert.priority,
                    "status": alert.status.value if alert.status else "NEW",
                    "updated_at": alert.updated_at,
                })
            
            # Fetch recent cases
            cases_query = select(Case).order_by(col(Case.updated_at).desc()).limit(limit)
            if username:
                cases_query = cases_query.where(Case.assignee == username)
            result = await db.execute(cases_query)
            for case in result.scalars().all():
                items.append({
                    "id": case.id,
                    "human_id": f"CAS-{case.id:07d}",
                    "title": case.title,
                    "item_type": "case",
                    "priority": case.priority,
                    "status": case.status.value if case.status else "NEW",
                    "updated_at": case.updated_at,
                })
            
            # Fetch recent tasks
            tasks_query = select(Task).order_by(col(Task.updated_at).desc()).limit(limit)
            if username:
                tasks_query = tasks_query.where(Task.assignee == username)
            result = await db.execute(tasks_query)
            for task in result.scalars().all():
                items.append({
                    "id": task.id,
                    "human_id": f"TSK-{task.id:07d}",
                    "title": task.title,
                    "item_type": "task",
                    "priority": task.priority,
                    "status": task.status.value if task.status else "TODO",
                    "updated_at": task.updated_at,
                })
            
            # Sort all items by updated_at descending and take top N
            items.sort(key=lambda x: x["updated_at"], reverse=True)
            return items[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching recent items: {e}")
            raise

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
        try:
            items = []
            
            # Priority order for sorting (higher = more urgent)
            priority_order = {
                Priority.EXTREME: 5,
                Priority.CRITICAL: 4,
                Priority.HIGH: 3,
                Priority.MEDIUM: 2,
                Priority.LOW: 1,
                Priority.INFO: 0,
            }
            
            # Item type order for sorting (alerts first, then tasks, then cases)
            type_order = {
                "alert": 0,
                "task": 1,
                "case": 2,
            }
            
            # Fetch open alerts assigned to user (NEW or IN_PROGRESS)
            # Fetch limit+1 to detect if results are truncated
            alerts_query = select(Alert).where(
                Alert.assignee == username,
                col(Alert.status).in_([AlertStatus.NEW, AlertStatus.IN_PROGRESS])
            ).order_by(col(Alert.updated_at).desc()).limit(limit + 1)
            result = await db.execute(alerts_query)
            for alert in result.scalars().all():
                items.append({
                    "id": alert.id,
                    "human_id": f"ALT-{alert.id:07d}",
                    "title": alert.title,
                    "item_type": "alert",
                    "priority": alert.priority,
                    "status": alert.status.value if alert.status else "NEW",
                    "updated_at": alert.updated_at,
                })
            
            # Fetch open cases assigned to user (NEW or IN_PROGRESS)
            cases_query = select(Case).where(
                Case.assignee == username,
                col(Case.status).in_([CaseStatus.NEW, CaseStatus.IN_PROGRESS])
            ).order_by(col(Case.updated_at).desc()).limit(limit + 1)
            result = await db.execute(cases_query)
            for case in result.scalars().all():
                items.append({
                    "id": case.id,
                    "human_id": f"CAS-{case.id:07d}",
                    "title": case.title,
                    "item_type": "case",
                    "priority": case.priority,
                    "status": case.status.value if case.status else "NEW",
                    "updated_at": case.updated_at,
                })
            
            # Fetch open tasks assigned to user (TODO or IN_PROGRESS)
            tasks_query = select(Task).where(
                Task.assignee == username,
                col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
            ).order_by(col(Task.updated_at).desc()).limit(limit + 1)
            result = await db.execute(tasks_query)
            for task in result.scalars().all():
                items.append({
                    "id": task.id,
                    "human_id": f"TSK-{task.id:07d}",
                    "title": task.title,
                    "item_type": "task",
                    "priority": task.priority,
                    "status": task.status.value if task.status else "TODO",
                    "updated_at": task.updated_at,
                })
            
            # Sort by priority (highest first), then by item type (alerts, tasks, cases)
            items.sort(
                key=lambda x: (
                    -priority_order.get(x["priority"], 0) if x["priority"] else 0,
                    type_order.get(x["item_type"], 99),
                    -x["updated_at"].timestamp() if x["updated_at"] else 0
                )
            )
            
            # Check if results are truncated
            total_count = len(items)
            truncated = total_count > limit
            
            return items[:limit], truncated
            
        except Exception as e:
            logger.error(f"Error fetching priority items: {e}")
            raise


dashboard_service = DashboardService()
