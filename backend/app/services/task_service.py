from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, cast, String
from sqlalchemy.orm import defer
from sqlmodel import col
from typing import List, Optional, Set, Dict, Any
from datetime import datetime, timezone
import logging
from uuid import uuid4
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate
from fastapi import HTTPException

from app.models.models import Task, TaskCreate, TaskUpdate, TaskRead, TaskTimelineItem, UserAccount, Actor, Alert, Case
from app.models.enums import TaskStatus, Priority
from app.services.timeline_service import timeline_service
from app.services.audit_service import TimelineAuditService

logger = logging.getLogger(__name__)
timeline_audit_service = TimelineAuditService()

# Valid string values for task status and priority
VALID_TASK_STATUSES = {e.value for e in TaskStatus}
VALID_PRIORITIES = {e.value for e in Priority}


class TaskService:
    
    async def create_task(
        self, 
        db: AsyncSession, 
        task_data: TaskCreate, 
        created_by: str
    ) -> Task:
        """Create a new task.
        
        Per FR-001 from spec: If no assignee specified, default to creator.
        """
        try:
            # Default assignee to creator if not specified (per spec requirement)
            assignee = task_data.assignee if task_data.assignee else created_by

            # Normalize priority to Priority enum
            priority = task_data.priority or Priority.MEDIUM
            if isinstance(priority, str):
                try:
                    priority = Priority(priority.upper())
                except ValueError:
                    priority = Priority.MEDIUM
            elif not isinstance(priority, Priority):
                priority = Priority.MEDIUM

            # Normalize status to TaskStatus enum
            status = task_data.status or TaskStatus.TODO
            if isinstance(status, str):
                try:
                    status = TaskStatus(status.upper())
                except ValueError:
                    status = TaskStatus.TODO
            elif not isinstance(status, TaskStatus):
                status = TaskStatus.TODO
            
            # Create task
            db_task = Task(
                title=task_data.title,
                description=task_data.description,
                priority=priority,
                due_date=task_data.due_date,
                status=status,
                assignee=assignee,
                case_id=task_data.case_id,
                linked_at=datetime.now(timezone.utc) if task_data.case_id else None,
                created_by=created_by
            )
            
            db.add(db_task)
            await db.commit()
            await db.refresh(db_task)
            
            logger.info(f"Task {db_task.id} created by {created_by}, assigned to {assignee}")
            return db_task
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating task: {e}")
            raise
    
    async def _get_task_model(self, db: AsyncSession, task_id: int) -> Optional[Task]:
        """Get the tracked task model."""
        try:
            query = select(Task).where(Task.id == task_id)
            result = await db.execute(query)
            db_task = result.scalar_one_or_none()
            if not db_task:
                return None
            
            # Eager load all entities referenced in timeline items to avoid N+1 queries
            if db_task.timeline_items:
                await self._preload_timeline_entities(db, db_task.timeline_items)

            return db_task
        except Exception as e:
            logger.error(f"Error fetching task {task_id}: {e}")
            raise

    async def get_task(self, db: AsyncSession, task_id: int, include_linked_timelines: bool = False) -> Optional[Task]:
        """Get task by ID with denormalized timeline.
        
        Args:
            db: Database session
            task_id: Task ID
            include_linked_timelines: If True, case and alert timeline items will include
                source_timeline_items from the linked entity
        """
        db_task = await self._get_task_model(db, task_id)
        if not db_task:
            return None

        return await timeline_service.denormalize_entity_timeline(
            db,
            db_task,
            human_prefix="TSK",
            include_linked_timelines=include_linked_timelines,
        )
    
    async def get_tasks(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100,
        status: Optional[List[TaskStatus]] = None,
        assignee: Optional[str] = None,
        case_id: Optional[int] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Page[Task]:
        """Get tasks with optional filtering and pagination.
        
        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            status: Filter by task status (can filter by multiple statuses)
            assignee: Filter by assignee username (exact match)
            case_id: Filter by case ID (for tasks linked to a specific case)
            search: Search string to match against task title or description (case-insensitive partial match)
            start_date: Filter tasks created after this UTC datetime (ISO8601 format with 'Z' suffix)
            end_date: Filter tasks created before this UTC datetime (ISO8601 format with 'Z' suffix)
        """
        try:
            # Build base query with ordering
            # Defer timeline_items - not needed for list view and can cause validation 
            # errors if malformed data exists. Detail view fetches them separately.
            query = select(Task).options(defer(Task.timeline_items)).order_by(col(Task.created_at).desc())  # type: ignore[arg-type]
            
            # Apply filters
            filters = []
            
            if status:
                normalized_statuses = []
                for status_value in status:
                    if isinstance(status_value, TaskStatus):
                        normalized_statuses.append(status_value)
                        continue

                    if isinstance(status_value, str):
                        candidate = status_value.strip().upper()
                        try:
                            normalized_statuses.append(TaskStatus(candidate))
                        except ValueError:
                            logger.warning(
                                "Ignoring unsupported task status filter value: %s",
                                status_value,
                            )
                    else:
                        logger.warning(
                            "Ignoring task status filter with unsupported type: %s",
                            type(status_value),
                        )

                if normalized_statuses:
                    filters.append(col(Task.status).in_(normalized_statuses))
            
            if assignee:
                filters.append(Task.assignee == assignee)
            
            if case_id is not None:
                filters.append(Task.case_id == case_id)
            
            # Date range filtering (expects UTC ISO8601 strings)
            if start_date:
                try:
                    # Parse ISO8601 with or without 'Z' suffix
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    filters.append(Task.created_at >= start_dt)
                except ValueError:
                    logger.warning(f"Invalid start_date format: {start_date}")
            
            if end_date:
                try:
                    # Parse ISO8601 with or without 'Z' suffix
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    filters.append(Task.created_at <= end_dt)
                except ValueError:
                    logger.warning(f"Invalid end_date format: {end_date}")
            
            if search:
                # Search in title or description (case-insensitive)
                search_pattern = f"%{search}%"
                filters.append(
                    or_(
                        col(Task.title).ilike(search_pattern),
                        cast(Task.description, String).ilike(search_pattern)  # type: ignore[arg-type]
                    )
                )
            
            # Apply all filters if any exist
            if filters:
                query = query.where(and_(*filters))
            
            # Use fastapi-pagination's paginate function
            return await paginate(db, query)
            
        except Exception as e:
            logger.error(f"Error fetching tasks: {e}")
            raise
    
    async def update_task(
        self, 
        db: AsyncSession, 
        task_id: int, 
        task_update: TaskUpdate, 
        updated_by: str
    ) -> Optional[Task]:
        """Update a task. Updated_at timestamp is automatically refreshed."""
        try:
            # Get existing task
            db_task = await self._get_task_model(db, task_id)
            if not db_task:
                return None
            
            # Track status changes for timeline
            old_status = db_task.status
            status_changed = False
            status_changed_to_done = False
            
            # Update fields
            update_data = task_update.model_dump(exclude_unset=True)
            # Capture original values before mutating for audit logging
            original_values = {field: getattr(db_task, field, None) for field in update_data if hasattr(db_task, field)}
            
            # Track if case_id is being set for the first time
            old_case_id = db_task.case_id
            old_assignee = db_task.assignee
            assignee_changed = False
            
            for field, new_value in update_data.items():
                if hasattr(db_task, field):
                    # Normalize status to TaskStatus enum
                    if field == 'status' and new_value is not None:
                        if isinstance(new_value, str):
                            try:
                                new_value = TaskStatus(new_value.upper())
                            except ValueError:
                                continue  # Skip invalid status
                        elif not isinstance(new_value, TaskStatus):
                            continue
                        if new_value != old_status:
                            status_changed = True
                            if new_value == TaskStatus.DONE:
                                status_changed_to_done = True
                    # Normalize priority to Priority enum
                    elif field == 'priority' and new_value is not None:
                        if isinstance(new_value, str):
                            try:
                                new_value = Priority(new_value.upper())
                            except ValueError:
                                continue  # Skip invalid priority
                        elif not isinstance(new_value, Priority):
                            continue
                    # Track assignee changes
                    elif field == 'assignee':
                        if new_value != old_assignee:
                            assignee_changed = True
                    setattr(db_task, field, new_value)
            
            # Set linked_at when case_id is set for the first time
            if db_task.case_id and not old_case_id:
                db_task.linked_at = datetime.now(timezone.utc)
            # Clear linked_at when case_id is removed
            elif not db_task.case_id and old_case_id:
                db_task.linked_at = None
            
            # Update timestamp (per FR-001 requirement)
            db_task.updated_at = datetime.now(timezone.utc)
            
            # Add timeline item for status changes
            if status_changed and updated_by:
                status_descriptions = {
                    "todo": "Task status changed to To Do",
                    "in_progress": "Task status changed to In Progress",
                    "done": "Task marked as Done",
                }
                
                description = status_descriptions.get(
                    db_task.status.value.lower() if hasattr(db_task.status, 'value') else str(db_task.status).lower(),
                    f"Task status changed to {db_task.status}"
                )
                
                now = datetime.now(timezone.utc)
                status_change_item = {
                    "id": str(uuid4()),
                    "type": "note",
                    "description": description,
                    "created_at": now.isoformat(),
                    "timestamp": now.isoformat(),
                    "created_by": updated_by,
                    "tags": ["status-change"],
                    "flagged": False,
                    "highlighted": False,
                    "replies": []
                }
                
                timeline_service.add_timeline_item(db_task, status_change_item, created_by=updated_by)
            
            await db.commit()
            await db.refresh(db_task)
            
            # Audit log field-level changes
            audit_changes = [
                {"field": field, "before": original_values.get(field), "after": getattr(db_task, field, None)}
                for field in update_data
                if field in original_values and str(original_values.get(field)) != str(getattr(db_task, field, None))
            ]
            if audit_changes:
                timeline_audit_service.log_entity_updated(
                    entity_type="task",
                    entity_id=task_id,
                    changes=audit_changes,
                    user=updated_by,
                )

            logger.info(f"Task {task_id} updated by {updated_by}")
            return await timeline_service.denormalize_entity_timeline(db, db_task, human_prefix="TSK")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating task {task_id}: {e}")
            raise
    
    async def delete_task(
        self, 
        db: AsyncSession, 
        task_id: int, 
        deleted_by: str
    ) -> bool:
        """Delete a task."""
        try:
            db_task = await self._get_task_model(db, task_id)
            if not db_task:
                return False
            
            await db.delete(db_task)
            await db.commit()
            
            timeline_audit_service.log_entity_deleted(
                entity_type="task",
                entity_id=task_id,
                user=deleted_by,
            )
            logger.info(f"Task {task_id} deleted by {deleted_by}")
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting task {task_id}: {e}")
            raise

    async def add_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        timeline_item: TaskTimelineItem,
        added_by: str
    ) -> Optional[Task]:
        """Add a single timeline item to a task's timeline.
        
        Note: Task items (type='task') are not allowed on task timelines.
        Tasks cannot be nested within other tasks.
        """
        try:
            db_task = await self._get_task_model(db, task_id)
            if not db_task:
                return None
            
            # Use mode='json' to ensure datetime fields are serialized to ISO strings
            item_dict = timeline_item.model_dump(mode='json')
            
            # Validate: tasks cannot contain task timeline items (no nesting)
            if item_dict.get("type") == "task":
                raise HTTPException(
                    status_code=400,
                    detail="Task timeline items cannot be added to tasks. Tasks cannot be nested."
                )
            
            # Add via timeline service with resource sync
            item_dict = await timeline_service.add_timeline_item_with_sync(
                db, db_task, item_dict, added_by,
                entity_id=task_id, entity_type="task"
            )
            
            await db.commit()
            await db.refresh(db_task)
            
            timeline_audit_service.log_timeline_item_added(
                entity_type="task",
                entity_id=task_id,
                item_id=item_dict.get("id", ""),
                item_type=item_dict.get("type", "unknown"),
                user=added_by,
            )
            logger.info(f"Timeline item added to task by {added_by}")
            return await timeline_service.denormalize_entity_timeline(db, db_task, human_prefix="TSK")
            
        except ValueError as e:
            await db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding timeline item to task {task_id}: {e}")
            raise

    async def update_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        item_id: str,
        updated_item: TaskTimelineItem,
        updated_by: str
    ) -> Optional[Task]:
        """Update a specific timeline item in a task with permission checks and audit logging."""
        try:
            db_task = await self._get_task_model(db, task_id)
            if not db_task:
                return None
            
            # Find the existing item to validate permissions and preserve metadata
            existing_item = timeline_service._find_item_by_id(db_task.timeline_items or [], item_id)
            if not existing_item:
                raise ValueError(f"Timeline item {item_id} not found")
            
            # Permission check: users can edit own items, admins can edit any
            if existing_item.get('created_by') != updated_by:
                # Check if user is admin
                result = await db.execute(
                    select(UserAccount).where(UserAccount.username == updated_by)  # type: ignore
                )
                user = result.scalars().first()
                if not user or user.role.value != 'ADMIN':
                    raise HTTPException(
                        status_code=403,
                        detail=f"You can only edit items you created. This item was created by {existing_item.get('created_by')}"
                    )
            
            # Use mode='json' to ensure datetime fields are serialized to ISO strings
            item_dict = updated_item.model_dump(mode='json')
            
            # Update via timeline service with resource sync
            result = await timeline_service.update_timeline_item_with_sync(
                db, db_task, item_id, item_dict, updated_by
            )
            
            if result is None:
                raise ValueError(f"Timeline item {item_id} not found")
            
            # Re-fetch the updated item for audit logging
            updated_dict = timeline_service._find_item_by_id(db_task.timeline_items or [], item_id) or item_dict
            
            # Audit log the edit with field-level changes
            timeline_audit_service.log_timeline_edit(
                entity_type="task",
                entity_id=task_id,
                item_id=item_id,
                item_type=updated_dict.get('type', 'unknown'),
                before=existing_item,
                after=updated_dict,
                user=updated_by,
            )
            
            await db.commit()
            await db.refresh(db_task)
            
            logger.info(
                f"Timeline item {item_id} (type: {updated_dict.get('type')}) updated in task {task_id} by {updated_by}"
            )
            return await timeline_service.denormalize_entity_timeline(db, db_task, human_prefix="TSK")
            
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating timeline item {item_id} in task {task_id}: {e}")
            raise

    async def remove_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        item_id: str,
        removed_by: str
    ) -> Optional[Task]:
        """Remove a specific timeline item from a task and clean up associated resources."""
        try:
            db_task = await self._get_task_model(db, task_id)
            if not db_task:
                return None
            
            # Find the item for error messaging
            item_to_remove = timeline_service._find_item_by_id(db_task.timeline_items or [], item_id)
            if not item_to_remove:
                raise ValueError(f"Timeline item {item_id} not found")
            
            # Remove timeline item with resource cleanup (handles attachments, etc.)
            if not await timeline_service.remove_timeline_item_with_cleanup(
                db, db_task, item_id, removed_by
            ):
                raise ValueError(f"Timeline item {item_id} not found")
            
            await db.commit()
            await db.refresh(db_task)
            
            timeline_audit_service.log_timeline_item_deleted(
                entity_type="task",
                entity_id=task_id,
                item_id=item_id,
                item_type=item_to_remove.get("type", "unknown"),
                user=removed_by,
            )
            logger.info(f"Timeline item {item_id} removed from task by {removed_by}")
            return await timeline_service.denormalize_entity_timeline(db, db_task, human_prefix="TSK")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error removing timeline item {item_id} from task {task_id}: {e}")
            raise
    
    async def _preload_timeline_entities(
        self,
        db: AsyncSession,
        timeline_items: List[Dict[str, Any]]
    ) -> None:
        """Preload all entities referenced in timeline items to avoid N+1 queries.
        
        This eagerly loads actors, alerts, and cases that are referenced
        in the timeline items into SQLAlchemy's session cache.
        """
        actor_ids: Set[int] = set()
        alert_ids: Set[int] = set()
        case_ids: Set[int] = set()
        
        def extract_ids_recursive(items: List[Dict[str, Any]]) -> None:
            """Recursively extract entity IDs from items and their replies."""
            for item in items:
                item_type = item.get("type")
                
                # Extract entity IDs based on item type
                if item_type in ("internal_actor", "external_actor", "threat_actor"):
                    if item.get("actor_id"):
                        actor_ids.add(item["actor_id"])
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
            logger.debug(f"Preloaded {len(actor_ids)} actors for task timeline")
        
        # Bulk load all alerts
        if alert_ids:
            alert_query = select(Alert).where(col(Alert.id).in_(alert_ids))
            await db.execute(alert_query)
            logger.debug(f"Preloaded {len(alert_ids)} alerts for task timeline")
        
        # Bulk load all cases
        if case_ids:
            case_query = select(Case).where(col(Case.id).in_(case_ids))
            await db.execute(case_query)
            logger.debug(f"Preloaded {len(case_ids)} cases for task timeline")


# Singleton instance
task_service = TaskService()
