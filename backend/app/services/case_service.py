from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, cast, String
from sqlalchemy.orm import selectinload, defer
from sqlmodel import col
from typing import List, Optional, Set, Dict, Any, Tuple
from datetime import datetime, timezone
import logging
from uuid import uuid4
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate

from app.models.models import (
    Case, Alert, Task, Actor, ActorSnapshot,
    CaseCreate, CaseUpdate, CaseRead,
    AlertCreate, AlertUpdate, AlertTriageRequest,
    CaseReadWithAlerts, AlertReadWithCase, CaseTimelineItem, CaseAlertClosureUpdate,
)
from app.models.enums import CaseStatus, AlertStatus, TaskStatus, RealtimeEventType
from app.services.timeline_add_service import add_timeline_item_and_commit, update_timeline_item_and_commit
from app.services.timeline_service import timeline_service
from app.services.audit_service import get_audit_service
from app.services.realtime_service import emit_event

logger = logging.getLogger(__name__)

# Valid closed statuses for alerts when auto-closing
VALID_ALERT_CLOSED_STATUSES = [
    AlertStatus.CLOSED_TP,
    AlertStatus.CLOSED_BP,
    AlertStatus.CLOSED_FP,
    AlertStatus.CLOSED_UNRESOLVED,
    AlertStatus.CLOSED_DUPLICATE
]

# Human-readable descriptions for alert closure statuses
ALERT_STATUS_DESCRIPTIONS = {
    AlertStatus.CLOSED_TP: "True Positive",
    AlertStatus.CLOSED_BP: "Benign Positive",
    AlertStatus.CLOSED_FP: "False Positive",
    AlertStatus.CLOSED_UNRESOLVED: "Unresolved",
    AlertStatus.CLOSED_DUPLICATE: "Duplicate"
}


class CaseService:
    
    async def create_case(
        self, 
        db: AsyncSession, 
        case_data: CaseCreate, 
        created_by: str
    ) -> Case:
        """Create a new case."""
        try:
            # Create case
            db_case = Case(
                title=case_data.title,
                description=case_data.description,
                priority=case_data.priority,
                assignee=case_data.assignee,
                tags=case_data.tags or [],
                timeline_items={},  # Initialize empty timeline as object-backed storage
                created_by=created_by
            )
            
            db.add(db_case)
            await db.flush()  # Get the ID without committing
            
            # Create audit log
            await self._create_audit_log(
                db, db_case.id, "created", "Case created", None, None, created_by  # type: ignore[arg-type]
            )
            
            await db.commit()
            await db.refresh(db_case)
            
            logger.info(f"Case created by {created_by}")
            loaded_case = await self.get_case(db, db_case.id)  # type: ignore[arg-type]
            if loaded_case is None:
                raise RuntimeError(f"Created case {db_case.id} could not be reloaded")
            return loaded_case
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating case: {e}")
            raise
    
    async def _get_case_model(
        self,
        db: AsyncSession,
        case_id: int,
        include_linked_timelines: bool = False,
    ) -> Optional[Case]:
        """Get the tracked case model with related entities loaded."""
        try:
            query = (
                select(Case)
                .options(
                    selectinload(Case.alerts).selectinload(Alert.triage_recommendation),
                    selectinload(Case.tasks)
                )
                .where(Case.id == case_id)
            )
            result = await db.execute(query)
            db_case = result.scalar_one_or_none()
            if not db_case:
                return None
            
            # Eager load all entities referenced in timeline items to avoid N+1 queries
            if db_case.timeline_items:
                await self._preload_timeline_entities(db, db_case.timeline_items, include_linked_timelines)

            return db_case
        except Exception as e:
            logger.error(f"Error fetching case {case_id}: {e}")
            raise

    async def get_case(
        self, 
        db: AsyncSession, 
        case_id: int,
        include_linked_timelines: bool = False
    ) -> Optional[Case]:
        """Get case by ID with related data.
        
        Args:
            db: Database session
            case_id: Case ID to fetch
            include_linked_timelines: If True, alert and task timeline items will include
                source_timeline_items from the linked entity
        """
        db_case = await self._get_case_model(db, case_id, include_linked_timelines)
        if not db_case:
            return None

        return await timeline_service.prepare_entity_detail_timeline(
            db,
            entity_type="case",
            entity_id=case_id,
            entity=db_case,
            human_prefix="CAS",
            include_linked_timelines=include_linked_timelines,
        )
    
    async def get_case_by_human_id(self, db: AsyncSession, human_id: str) -> Optional[Case]:
        """Get case by human_id."""
        try:
            if not human_id.startswith("CAS-"):
                return None
            case_id = int(human_id[4:])
            return await self.get_case(db, case_id)
        except (ValueError, IndexError):
            return None
    
    async def get_case_minimal(self, db: AsyncSession, case_id: int) -> Optional[Case]:
        """Get case by ID without denormalization (for injection into other timelines)."""
        try:
            query = select(Case).where(Case.id == case_id)
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching minimal case {case_id}: {e}")
            return None
    
    async def get_cases(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100,
        status: Optional[List[CaseStatus]] = None,
        assignee: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Page[Case]:
        """Get cases with optional filtering and pagination.
        
        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            status: Filter by case status (can filter by multiple statuses)
            assignee: Filter by assignee username (exact match)
            search: Search string to match against case title or description (case-insensitive partial match)
            start_date: Filter cases created after this UTC datetime (ISO8601 format with 'Z' suffix)
            end_date: Filter cases created before this UTC datetime (ISO8601 format with 'Z' suffix)
        """
        try:
            # Build base query with ordering
            # Defer timeline_items - not needed for list view and can cause validation 
            # errors if malformed data exists. Detail view fetches them separately.
            query = select(Case).options(defer(Case.timeline_items)).order_by(col(Case.created_at).desc())  # type: ignore[arg-type]
            
            # Apply filters
            filters = []
            
            if status:
                filters.append(col(Case.status).in_(status))
            
            if assignee:
                filters.append(Case.assignee == assignee)
            
            # Date range filtering (expects UTC ISO8601 strings)
            if start_date:
                try:
                    from datetime import datetime
                    # Parse ISO8601 with or without 'Z' suffix
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    filters.append(Case.created_at >= start_dt)
                except ValueError:
                    logger.warning(f"Invalid start_date format: {start_date}")
            
            if end_date:
                try:
                    from datetime import datetime
                    # Parse ISO8601 with or without 'Z' suffix
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    filters.append(Case.created_at <= end_dt)
                except ValueError:
                    logger.warning(f"Invalid end_date format: {end_date}")
            
            if search:
                # Search in title or description (case-insensitive)
                search_pattern = f"%{search}%"
                filters.append(
                    or_(
                        col(Case.title).ilike(search_pattern),
                        cast(Case.description, String).ilike(search_pattern)  # type: ignore[arg-type]
                    )
                )
            
            # Apply all filters if any exist
            if filters:
                query = query.where(and_(*filters))
            
            # Use fastapi-pagination's paginate function
            # This automatically handles skip/limit from query parameters
            return await paginate(db, query)
            
        except Exception as e:
            logger.error(f"Error fetching cases: {e}")
            raise
    
    async def update_case(
        self, 
        db: AsyncSession, 
        case_id: int, 
        case_update: CaseUpdate, 
        updated_by: str
    ) -> Optional[Case]:
        """Update a case and create audit logs."""
        try:
            # Get existing case
            db_case = await self._get_case_model(db, case_id)
            if not db_case:
                return None
            
            # Track changes for audit
            changes = []
            update_data = case_update.model_dump(exclude_unset=True)
            
            # Track if status changed to CLOSED and if assignee changed
            status_changed_to_closed = False
            old_status = db_case.status
            assignee_changed = False
            old_assignee = db_case.assignee
            
            for field, new_value in update_data.items():
                if hasattr(db_case, field):
                    old_value = getattr(db_case, field)
                    if old_value != new_value:
                        changes.append((field, str(old_value), str(new_value)))
                        setattr(db_case, field, new_value)
                        # Track specific changes for metrics
                        if field == 'status' and new_value == CaseStatus.CLOSED:
                            status_changed_to_closed = True
                        if field == 'assignee':
                            assignee_changed = True
            
            # Handle status change special case
            if 'status' in update_data and db_case.status == CaseStatus.CLOSED:
                db_case.closed_at = datetime.now(timezone.utc)
            
            # Create audit logs for changes
            for field, old_val, new_val in changes:
                await self._create_audit_log(
                    db, case_id, f"{field}_changed", 
                    f"{field.title()} changed from {old_val} to {new_val}",
                    old_val, new_val, updated_by
                )
            
            # If case status changed to CLOSED, close all linked tasks and alerts
            if status_changed_to_closed and old_status != CaseStatus.CLOSED:
                # Extract alert closure statuses if provided
                alert_closure_statuses = self._build_alert_closure_status_map(
                    case_update.alert_closure_updates
                )
                
                closure_results = await self._close_linked_items(
                    db, case_id, updated_by, alert_closure_statuses
                )
                
                # Log any errors that occurred during closure
                if closure_results["errors"]:
                    logger.warning(
                        f"Errors occurred while closing linked items for case {case_id}: "
                        f"{', '.join(closure_results['errors'])}"
                    )
                
                # Create audit log for linked item closures
                summary = (
                    f"Closed {closure_results['tasks_closed']} linked tasks and "
                    f"{closure_results['alerts_closed']} linked alerts. "
                )
                if closure_results["tasks_failed"] > 0 or closure_results["alerts_failed"] > 0:
                    summary += (
                        f"Failed to close {closure_results['tasks_failed']} tasks and "
                        f"{closure_results['alerts_failed']} alerts."
                    )
                
                await self._create_audit_log(
                    db, case_id, "linked_items_closed",
                    summary,
                    None, None, updated_by
                )
            
            await emit_event(
                db,
                entity_type="case",
                entity_id=case_id,
                event_type=RealtimeEventType.ENTITY_UPDATED,
                performed_by=updated_by,
            )

            await db.commit()
            
            logger.info(f"Case updated by {updated_by}")
            return await self.get_case(db, case_id)
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating case {case_id}: {e}")
            raise
    
    async def _close_linked_task(
        self,
        db: AsyncSession,
        task: Task,
        case_human_id: str,
        closed_by: str
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        Close a single linked task and add a note to its timeline.
        Returns (success, was_changed, error_message).
        was_changed is True only if the task status was actually changed.
        """
        try:
            # Skip tasks that are already done
            if task.status == TaskStatus.DONE:
                return (True, False, None)
            
            # Update task status to DONE
            task.status = TaskStatus.DONE
            task.updated_at = datetime.now(timezone.utc)
            
            # Add timeline note indicating closure was triggered by case closure
            now = datetime.now(timezone.utc)
            
            closure_note = {
                "id": str(uuid4()),
                "type": "note",
                "description": f"Task closed automatically due to case {case_human_id} closure",
                "created_at": now.isoformat(),
                "timestamp": now.isoformat(),
                "created_by": closed_by,
                "tags": ["auto-close", "case-closure"],
                "flagged": False,
                "highlighted": False,
                "replies": []
            }
            
            timeline_service.add_timeline_item(task, closure_note, created_by=closed_by)
            
            await db.flush()
            logger.info(f"Task {task.id} closed due to case {case_human_id} closure")
            return (True, True, None)
            
        except Exception as e:
            error_msg = f"Failed to close task {task.id}: {str(e)}"
            logger.error(error_msg)
            return (False, False, error_msg)
    
    async def _close_linked_alert(
        self,
        db: AsyncSession,
        alert: Alert,
        case_human_id: str,
        closed_by: str,
        custom_status: Optional[AlertStatus] = None
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        Close a single linked alert with the specified status.
        Returns (success, was_changed, error_message).
        was_changed is True only if the alert status was actually changed.
        
        Args:
            db: Database session
            alert: Alert to close
            case_id: Case ID for logging
            closed_by: Username of the user closing the alert
            custom_status: Optional custom closure status. If not provided, defaults to CLOSED_UNRESOLVED
        """
        try:
            # Skip alerts that are already closed
            if alert.status in VALID_ALERT_CLOSED_STATUSES:
                return (True, False, None)
            
            # Use custom status if provided, otherwise default to CLOSED_UNRESOLVED
            closure_status = custom_status or AlertStatus.CLOSED_UNRESOLVED
            
            # Validate that the provided status is a valid closed status
            if closure_status not in VALID_ALERT_CLOSED_STATUSES:
                error_msg = f"Invalid closure status for alert {alert.id}: {closure_status}"
                logger.error(error_msg)
                return (False, False, error_msg)
            
            # Update alert status
            alert.status = closure_status
            alert.updated_at = datetime.now(timezone.utc)
            
            # Get human-readable description for status
            status_desc = ALERT_STATUS_DESCRIPTIONS.get(closure_status, str(closure_status))
            
            # Add timeline note for the status change
            now = datetime.now(timezone.utc)
            closure_note = {
                "id": str(uuid4()),
                "type": "note",
                "description": f"Alert closed automatically as {status_desc} due to case {case_human_id} closure",
                "created_at": now.isoformat(),
                "timestamp": now.isoformat(),
                "created_by": closed_by,
                "tags": ["auto-close", "case-closure"],
                "flagged": False,
                "highlighted": False,
                "replies": []
            }
            
            timeline_service.add_timeline_item(alert, closure_note, created_by=closed_by)
            
            await db.flush()
            logger.info(f"Alert {alert.id} closed as {status_desc} due to case {case_human_id} closure")
            return (True, True, None)
            
        except Exception as e:
            error_msg = f"Failed to close alert {alert.id}: {str(e)}"
            logger.error(error_msg)
            return (False, False, error_msg)
    
    async def _close_linked_items(
        self,
        db: AsyncSession,
        case_id: int,
        closed_by: str,
        alert_closure_statuses: Optional[Dict[int, AlertStatus]] = None
    ) -> Dict[str, Any]:
        """
        Close all linked tasks and alerts when a case is closed.
        
        Args:
            db: Database session
            case_id: ID of the case being closed
            closed_by: Username of the user closing the case
            alert_closure_statuses: Optional dict mapping alert IDs to their desired closure statuses
        
        Returns a dictionary with closure results and any errors.
        """
        results = {
            "tasks_closed": 0,
            "tasks_failed": 0,
            "alerts_closed": 0,
            "alerts_failed": 0,
            "errors": []
        }
        
        # Convert None to empty dict (avoid mutable default argument)
        alert_closure_statuses = alert_closure_statuses or {}
        
        try:
            # Get the case with linked tasks and alerts
            query = (
                select(Case)
                .options(
                    selectinload(Case.tasks),
                    selectinload(Case.alerts)
                )
                .where(Case.id == case_id)
            )
            result = await db.execute(query)
            db_case = result.scalar_one_or_none()
            
            if not db_case:
                return results

            case_human_id = f"CAS-{case_id:07d}"
            
            # Close linked tasks individually
            if db_case.tasks:
                for task in db_case.tasks:
                    success, was_changed, error = await self._close_linked_task(
                        db, task, case_human_id, closed_by
                    )
                    if success and was_changed:
                        results["tasks_closed"] += 1
                    elif not success:
                        results["tasks_failed"] += 1
                        if error:
                            results["errors"].append(error)
            
            # Close linked alerts individually
            if db_case.alerts:
                for alert in db_case.alerts:
                    # Get custom status for this alert if provided
                    custom_status = alert_closure_statuses.get(alert.id)
                    success, was_changed, error = await self._close_linked_alert(
                        db, alert, case_human_id, closed_by, custom_status
                    )
                    if success and was_changed:
                        results["alerts_closed"] += 1
                    elif not success:
                        results["alerts_failed"] += 1
                        if error:
                            results["errors"].append(error)
            
            # Flush changes to database (commit happens in calling function)
            await db.flush()
            
            # Log summary
            logger.info(
                f"Case {case_id} closure: "
                f"Closed {results['tasks_closed']} tasks, {results['alerts_closed']} alerts. "
                f"Failed: {results['tasks_failed']} tasks, {results['alerts_failed']} alerts."
            )
            
        except Exception as e:
            error_msg = f"Error during bulk closure of linked items: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
        
        return results

    def _build_alert_closure_status_map(
        self,
        alert_closure_updates: Optional[List[CaseAlertClosureUpdate]]
    ) -> Dict[int, AlertStatus]:
        """Normalize array-based alert closure updates into an alert_id -> status map."""
        if not alert_closure_updates:
            return {}

        closure_status_map: Dict[int, AlertStatus] = {}
        for alert_update in alert_closure_updates:
            closure_status_map[alert_update.alert_id] = alert_update.status

        return closure_status_map
    
    async def delete_case(self, db: AsyncSession, case_id: int, deleted_by: str) -> bool:
        """Soft delete a case (mark as deleted in audit log)."""
        try:
            db_case = await self._get_case_model(db, case_id)
            if not db_case:
                return False
            
            await self._create_audit_log(
                db, case_id, "deleted", "Case deleted", None, None, deleted_by
            )
            
            await db.delete(db_case)
            await db.commit()
            
            logger.info(f"Case deleted by {deleted_by}")
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting case {case_id}: {e}")
            raise
    
    async def add_timeline_item(
        self, 
        db: AsyncSession, 
        case_id: int, 
        timeline_item: CaseTimelineItem, 
        created_by: str
    ) -> Optional[Case]:
        """Add a timeline item to a case."""
        try:
            db_case = await self._get_case_model(db, case_id)
            if not db_case:
                return None

            item_dict = await add_timeline_item_and_commit(
                db,
                entity=db_case,
                entity_id=case_id,
                entity_type="case",
                timeline_item=timeline_item,
                performed_by=created_by,
            )
            
            await db.refresh(db_case)
            
            logger.info(f"Timeline item added to case by {created_by}")
            db_case = await timeline_service.denormalize_entity_timeline(db, db_case, human_prefix="CAS")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="case",
                entity_id=case_id,
                entity=db_case,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding timeline item to case {case_id}: {e}")
            raise
    
    async def update_timeline_item(
        self, 
        db: AsyncSession, 
        case_id: int, 
        item_id: str, 
        timeline_item: CaseTimelineItem, 
        updated_by: str
    ) -> Optional[Case]:
        """Update a timeline item in a case."""
        try:
            db_case = await self._get_case_model(db, case_id)
            if not db_case or not db_case.timeline_items:
                return None
            
            # Find the existing item for audit logging
            existing_item = timeline_service._find_item_by_id(db_case.timeline_items or [], item_id)
            if not existing_item:
                return None

            updated_item = await update_timeline_item_and_commit(
                db,
                entity=db_case,
                entity_id=case_id,
                entity_type="case",
                item_id=item_id,
                existing_item=existing_item,
                timeline_item=timeline_item,
                performed_by=updated_by,
            )

            if updated_item is None:
                return None
            await db.refresh(db_case)

            logger.info(f"Timeline item {item_id} updated in case by {updated_by}")
            db_case = await timeline_service.denormalize_entity_timeline(db, db_case, human_prefix="CAS")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="case",
                entity_id=case_id,
                entity=db_case,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating timeline item {item_id} in case {case_id}: {e}")
            raise
    
    async def remove_timeline_item(
        self, 
        db: AsyncSession, 
        case_id: int, 
        item_id: str, 
        deleted_by: str
    ) -> Optional[Case]:
        """Remove a timeline item from a case and clean up associated resources."""
        try:
            db_case = await self._get_case_model(db, case_id)
            if not db_case or not db_case.timeline_items:
                return None
            
            # Find the item for audit logging
            item_to_remove = timeline_service._find_item_by_id(db_case.timeline_items or [], item_id)
            if not item_to_remove:
                return None
            
            # Remove timeline item with resource cleanup (handles attachments, tasks, etc.)
            if not await timeline_service.remove_timeline_item_with_cleanup(
                db, db_case, item_id, deleted_by
            ):
                return None

            await get_audit_service(db).log_timeline_item_deleted(
                entity_type="case",
                entity_id=case_id,
                item_id=item_id,
                item_type=item_to_remove.get("type", "unknown"),
                user=deleted_by,
                old_value=item_to_remove,
            )

            await emit_event(
                db,
                entity_type="case",
                entity_id=case_id,
                event_type=RealtimeEventType.TIMELINE_ITEM_DELETED,
                performed_by=deleted_by,
                item_id=item_id,
                item_type=item_to_remove.get("type"),
            )

            await db.commit()
            await db.refresh(db_case)

            logger.info(f"Timeline item {item_id} deleted from case by {deleted_by}")
            db_case = await timeline_service.denormalize_entity_timeline(db, db_case, human_prefix="CAS")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="case",
                entity_id=case_id,
                entity=db_case,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting timeline item {item_id} from case {case_id}: {e}")
            raise
    
    async def _preload_timeline_entities(
        self,
        db: AsyncSession,
        timeline_items: List[Dict[str, Any]] | Dict[str, Dict[str, Any]],
        include_linked_timelines: bool = False
    ) -> None:
        """Preload all entities referenced in timeline items to avoid N+1 queries.
        
        This eagerly loads actors, tasks, alerts, and cases that are referenced
        in the timeline items into SQLAlchemy's session cache, so subsequent
        db.get() calls during denormalization will be instant.
        """
        actor_ids: Set[int] = set()
        task_ids: Set[int] = set()
        alert_ids: Set[int] = set()
        case_ids: Set[int] = set()
        
        def extract_ids_recursive(items: List[Dict[str, Any]] | Dict[str, Dict[str, Any]]) -> None:
            """Recursively extract entity IDs from items and their replies."""
            for item in timeline_service._iter_items(items):
                item_type = item.get("type")
                
                # Extract entity IDs based on item type
                if item_type in ("internal_actor", "external_actor", "threat_actor"):
                    if item.get("actor_id"):
                        actor_ids.add(item["actor_id"])
                elif item_type == "task":
                    if item.get("task_id") and isinstance(item["task_id"], int):
                        task_ids.add(item["task_id"])
                elif item_type == "alert":
                    if item.get("alert_id") and isinstance(item["alert_id"], int):
                        alert_ids.add(item["alert_id"])
                elif item_type == "case":
                    if item.get("case_id") and isinstance(item["case_id"], int):
                        case_ids.add(item["case_id"])
                
                # Recursively process replies
                if item.get("replies"):
                    extract_ids_recursive(item["replies"])
        
        # Extract all IDs from the timeline
        extract_ids_recursive(timeline_items)
        
        # Bulk load all actors
        if actor_ids:
            actor_query = select(Actor).where(col(Actor.id).in_(actor_ids))
            await db.execute(actor_query)
            logger.debug(f"Preloaded {len(actor_ids)} actors")
        
        # Bulk load all tasks
        if task_ids:
            task_query = select(Task).where(col(Task.id).in_(task_ids))
            await db.execute(task_query)
            logger.debug(f"Preloaded {len(task_ids)} tasks")
        
        # Bulk load all alerts (with their timelines if needed)
        if alert_ids:
            if include_linked_timelines:
                # Need to load alerts and recursively preload their timeline entities
                alert_query = select(Alert).where(col(Alert.id).in_(alert_ids))
                result = await db.execute(alert_query)
                alerts = result.scalars().all()
                logger.debug(f"Preloaded {len(alerts)} alerts with timelines")
                
                # Recursively preload entities from alert timelines
                for alert in alerts:
                    if alert.timeline_items:
                        await self._preload_timeline_entities(
                            db, alert.timeline_items, include_linked_timelines=False
                        )
            else:
                alert_query = select(Alert).where(col(Alert.id).in_(alert_ids))
                await db.execute(alert_query)
                logger.debug(f"Preloaded {len(alert_ids)} alerts")
        
        # Bulk load all cases
        if case_ids:
            case_query = select(Case).where(col(Case.id).in_(case_ids))
            await db.execute(case_query)
            logger.debug(f"Preloaded {len(case_ids)} cases")
    
    async def _create_audit_log(
        self,
        db: AsyncSession,
        case_id: int,
        action: str,
        description: str,
        old_value: Optional[str],
        new_value: Optional[str],
        performed_by: str
    ) -> None:
        """Create an audit log entry."""
        event_type_map = {
            "created": "case.created",
            "deleted": "case.deleted",
            "linked_items_closed": "case.linked_items_closed",
            "status_changed": "case.status_changed",
            "priority_changed": "case.priority_changed",
            "assignee_changed": "case.assignee_changed",
            "title_changed": "case.title_changed",
            "description_changed": "case.description_changed",
            "tags_changed": "case.tags_changed",
        }
        event_type = event_type_map.get(action, f"case.{action}")
        await get_audit_service(db).log_event(
            event_type=event_type,
            entity_type="case",
            entity_id=str(case_id),
            description=description,
            old_value=old_value,
            new_value=new_value,
            performed_by=performed_by,
        )


case_service = CaseService()
