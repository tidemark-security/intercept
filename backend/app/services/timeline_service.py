from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone
import uuid
import logging

from app.services.normalization_service import normalization_service

if TYPE_CHECKING:
    from app.models.models import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)

# Fields that are dynamically populated from the Task entity on read
# These should NOT be stored in the timeline JSON (snapshots)
TASK_SNAPSHOT_FIELDS: Set[str] = {
    "title", "status", "priority", "assignee", "due_date",
    "task_human_id", "description",
}

# Fields that should be preserved in the timeline JSON for task items
TASK_REFERENCE_FIELDS: Set[str] = {
    "id", "type", "task_id", "created_at", "created_by",
    "parent_id", "replies", "flagged", "highlighted", "tags", "timestamp",
}


class TimelineService:
    """
    Shared helpers for timeline item normalization, denormalization,
    and mutation (add/update/remove) across alerts and cases.
    """

    def _ensure_list(self, entity: Any) -> None:
        if getattr(entity, "timeline_items", None) is None:
            entity.timeline_items = []

    def generate_item_id(self) -> str:
        """Generate a unique identifier for a timeline item."""
        return uuid.uuid4().hex

    def _validate_reply_depth(self, item: Dict[str, Any], current_depth: int = 0, max_depth: int = 5) -> None:
        """
        Validate that replies don't exceed max depth (default: 5 levels).
        Raises ValueError if validation fails.
        
        Args:
            item: Timeline item to validate
            current_depth: Current nesting level (0 = top-level)
            max_depth: Maximum allowed nesting depth
        """
        if current_depth >= max_depth:
            raise ValueError(f"Replies cannot be nested more than {max_depth} levels deep")
        
        # Check each reply recursively
        if item.get("replies"):
            for reply in item["replies"]:
                self._validate_reply_depth(reply, current_depth + 1, max_depth)

    async def normalize_item(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a timeline item using the actor service (handles actor/alert/case normalization)."""
        # Validate reply depth before normalizing (max 5 levels)
        self._validate_reply_depth(item)
        
        normalized = await normalization_service.normalize_actor_item(db, item)
        
        # Recursively normalize replies if present (up to max depth)
        if "replies" in normalized and normalized["replies"]:
            normalized_replies = []
            for reply in normalized["replies"]:
                # Recursively normalize each reply (which may have its own replies)
                normalized_replies.append(await self.normalize_item(db, reply))
            normalized["replies"] = normalized_replies
        
        return normalized

    async def denormalize_entity_timeline(
        self, 
        db: AsyncSession, 
        entity: Any, 
        human_prefix: str,
        include_linked_timelines: bool = False,
        detach: bool = True,
    ) -> Any:
        """
        Set human-readable id on the entity and denormalize all timeline items.
        human_prefix examples: "ALT" for alerts, "CAS" for cases.
        
        Also injects synthetic timeline items for linked entities:
        - For Cases: injects alert items for each linked alert (based on alert.case_id FK)
        - For Alerts: injects case item if linked to a case (based on alert.case_id FK)
        
        Args:
            db: Database session
            entity: The case/alert entity
            human_prefix: Prefix for human ID (e.g., "ALT", "CAS")
            include_linked_timelines: If True, alert and task items will include
                source_timeline_items from the linked entity
        """
        items = list(getattr(entity, "timeline_items", None) or [])
        
        # Filter out any previously injected items (in case entity was cached/reused)
        items = [it for it in items if not it.get("_injected")]
        
        # Inject synthetic timeline items for linked entities
        items = await self._inject_linked_entity_items(db, entity, human_prefix, items)

        denormed: List[Dict[str, Any]] = []
        for it in items:
            denormed.append(await self._denormalize_item_recursive(
                db, it, include_linked_timelines=include_linked_timelines
            ))

        if detach:
            state = sa_inspect(entity)
            if state.session is not None:
                state.session.expunge(entity)

        entity.timeline_items = denormed
        return entity
    
    async def _inject_linked_entity_items(
        self,
        db: AsyncSession,
        entity: Any,
        human_prefix: str,
        items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Inject synthetic timeline items for linked entities based on FK relationships.
        
        - For Cases (CAS): inject alert items for each linked alert
        - For Alerts (ALT): inject case item if linked to a case
        """
        if human_prefix == "CAS":
            # Inject alert items for linked alerts
            alerts = getattr(entity, "alerts", None)
            if alerts:
                for alert in alerts:
                    if alert.linked_at:
                        # Create synthetic alert timeline item
                        alert_item = {
                            "id": f"linked-alert-{alert.id}",
                            "type": "alert",
                            "alert_id": alert.id,
                            "title": alert.title,
                            "priority": alert.priority,
                            "assignee": alert.assignee,
                            "created_at": alert.linked_at.isoformat() if alert.linked_at else alert.created_at.isoformat(),
                            "timestamp": alert.linked_at.isoformat() if alert.linked_at else alert.created_at.isoformat(),
                            "created_by": alert.assignee or "system",
                            "tags": ["linked-alert"],
                            "flagged": False,
                            "highlighted": False,
                            "replies": [],
                            "_injected": True,  # Mark as dynamically injected
                        }
                        items.append(alert_item)
            
            # Inject task items for linked tasks
            tasks = getattr(entity, "tasks", None)
            if tasks:
                for task in tasks:
                    if task.linked_at:
                        # Create synthetic task timeline item
                        task_item = {
                            "id": f"linked-task-{task.id}",
                            "type": "task",
                            "task_id": task.id,
                            "title": task.title,
                            "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
                            "priority": task.priority,
                            "assignee": task.assignee,
                            "due_date": task.due_date.isoformat() if task.due_date else None,
                            "created_at": task.linked_at.isoformat() if task.linked_at else task.created_at.isoformat(),
                            "timestamp": task.linked_at.isoformat() if task.linked_at else task.created_at.isoformat(),
                            "created_by": task.created_by or "system",
                            "tags": ["linked-task"],
                            "flagged": False,
                            "highlighted": False,
                            "replies": [],
                            "_injected": True,  # Mark as dynamically injected
                        }
                        items.append(task_item)
        
        elif human_prefix == "ALT":
            # Inject case item if alert is linked to a case
            case_id = getattr(entity, "case_id", None)
            linked_at = getattr(entity, "linked_at", None)
            if case_id and linked_at:
                # Need to fetch case details for the item
                from app.services.case_service import case_service
                case = await case_service.get_case_minimal(db, case_id)
                if case:
                    case_item = {
                        "id": f"linked-case-{case_id}",
                        "type": "case",
                        "case_id": case_id,
                        "title": case.title,
                        "priority": case.priority,
                        "assignee": case.assignee,
                        "description": f"Linked to Case CAS-{case_id:07d}",
                        "created_at": linked_at.isoformat(),
                        "timestamp": linked_at.isoformat(),
                        "created_by": entity.assignee or "system",
                        "tags": ["linked"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                        "_injected": True,  # Mark as dynamically injected
                    }
                    items.append(case_item)
        
        elif human_prefix == "TSK":
            # Inject case item if task is linked to a case
            case_id = getattr(entity, "case_id", None)
            linked_at = getattr(entity, "linked_at", None)
            if case_id and linked_at:
                # Need to fetch case details for the item
                from app.services.case_service import case_service
                case = await case_service.get_case_minimal(db, case_id)
                if case:
                    case_item = {
                        "id": f"linked-case-{case_id}",
                        "type": "case",
                        "case_id": case_id,
                        "title": case.title,
                        "priority": case.priority,
                        "assignee": case.assignee,
                        "description": f"Linked to Case CAS-{case_id:07d}",
                        "created_at": linked_at.isoformat(),
                        "timestamp": linked_at.isoformat(),
                        "created_by": getattr(entity, "created_by", None) or "system",
                        "tags": ["linked"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                        "_injected": True,  # Mark as dynamically injected
                    }
                    items.append(case_item)
        
        return items
    
    async def _denormalize_item_recursive(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any],
        include_linked_timelines: bool = False
    ) -> Dict[str, Any]:
        """Recursively denormalize a timeline item and its replies.
        
        Args:
            db: Database session
            item: Timeline item dict to denormalize
            include_linked_timelines: If True, alert and task items will include
                source_timeline_items from the linked entity
        """
        denormalized = await normalization_service.denormalize_actor_item(db, item)
        
        # For task items, populate fields dynamically from the Task entity
        if denormalized.get("type") == "task":
            denormalized = await self._denormalize_task_item(
                db, denormalized, include_linked_timelines=include_linked_timelines
            )
        
        # For alert items, optionally embed timeline items from the linked alert
        if denormalized.get("type") == "alert" and include_linked_timelines:
            denormalized = await self._embed_alert_timeline_items(db, denormalized)
        
        # For case items, optionally embed timeline items from the linked case
        if denormalized.get("type") == "case" and include_linked_timelines:
            denormalized = await self._embed_case_timeline_items(db, denormalized)
        
        # Recursively denormalize replies if present
        if "replies" in denormalized and denormalized["replies"]:
            denormalized_replies = []
            for reply in denormalized["replies"]:
                denormalized_replies.append(await self._denormalize_item_recursive(
                    db, reply, include_linked_timelines=include_linked_timelines
                ))
            denormalized["replies"] = denormalized_replies
        
        return denormalized

    # ===== Task Item Helpers =====
    
    def _resolve_task_id(self, item: Dict[str, Any]) -> Optional[int]:
        """Extract task_id from a timeline item (from task_id or task_human_id)."""
        task_id = item.get("task_id")
        if isinstance(task_id, int):
            return task_id
        if isinstance(task_id, str) and task_id.isdigit():
            return int(task_id)
        
        # Try parsing from human ID
        human_id = item.get("task_human_id")
        if isinstance(human_id, str) and human_id.startswith("TSK-"):
            try:
                return int(human_id[4:])
            except ValueError:
                pass
        
        return None

    async def _denormalize_task_item(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any],
        include_linked_timelines: bool = False
    ) -> Dict[str, Any]:
        """
        Populate task timeline item fields from the Task entity.
        
        Uses task_id to fetch live data. Any snapshot fields in the stored
        JSON are ignored - the Task entity is the source of truth.
        
        Args:
            db: Database session
            item: Task timeline item dict
            include_linked_timelines: If True, embed task's timeline_items as source_timeline_items
        """
        task_id = self._resolve_task_id(item)
        if not task_id:
            logger.warning("Task timeline item missing task_id, cannot denormalize")
            return item
        
        # Lazy import to avoid circular dependency
        from app.services.task_service import task_service
        
        task = await task_service.get_task(db, task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for timeline denormalization")
            # Return item as-is, it may have stale snapshot data
            return item
        
        # Populate from Task entity (source of truth)
        item["task_id"] = task.id
        item["task_human_id"] = f"TSK-{task.id:07d}"
        item["title"] = task.title
        item["description"] = task.description
        item["status"] = task.status.value if task.status else None
        item["priority"] = task.priority.value if task.priority else None
        item["assignee"] = task.assignee
        item["due_date"] = task.due_date.isoformat() if task.due_date else None
        
        # Use Task's created_at/created_by as the canonical source
        item["created_at"] = task.created_at.isoformat() if task.created_at else item.get("created_at")
        item["created_by"] = task.created_by or item.get("created_by")
        
        # Optionally embed task's timeline items as source_timeline_items
        if include_linked_timelines and task.timeline_items:
            # Denormalize the task's timeline items (without further nesting to avoid infinite recursion)
            source_items = []
            for task_item in task.timeline_items:
                denormalized = await self._denormalize_item_recursive(
                    db, task_item, include_linked_timelines=False  # Don't recurse into linked entities
                )
                source_items.append(denormalized)
            item["source_timeline_items"] = source_items
        
        return item

    async def _embed_alert_timeline_items(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Embed timeline items from the linked alert into the alert timeline item.
        
        This is called when include_linked_timelines=True to populate
        the source_timeline_items field on AlertItem.
        
        Args:
            db: Database session
            item: Alert timeline item dict
            
        Returns:
            Item with source_timeline_items populated
        """
        alert_id = item.get("alert_id")
        if not alert_id:
            return item
        
        # Lazy import to avoid circular dependency
        from app.services.alert_service import alert_service
        
        try:
            alert = await alert_service.get_alert(db, alert_id)
            if not alert:
                logger.warning(f"Alert {alert_id} not found for timeline embedding")
                return item
            
            # Embed the alert's timeline items
            if alert.timeline_items:
                # Items are already denormalized from get_alert
                item["source_timeline_items"] = alert.timeline_items
        except Exception as e:
            logger.warning(f"Failed to embed timeline items for alert {alert_id}: {e}")
        
        return item

    async def _embed_case_timeline_items(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Embed timeline items from the linked case into the case timeline item.
        
        This is called when include_linked_timelines=True to populate
        the source_timeline_items field on CaseItem.
        
        Args:
            db: Database session
            item: Case timeline item dict
            
        Returns:
            Item with source_timeline_items populated
        """
        case_id = item.get("case_id")
        if not case_id:
            return item
        
        # Lazy import to avoid circular dependency
        from app.services.case_service import case_service
        
        try:
            # Use get_case without include_linked_timelines to avoid infinite recursion
            case = await case_service.get_case(db, case_id, include_linked_timelines=False)
            if not case:
                logger.warning(f"Case {case_id} not found for timeline embedding")
                return item
            
            # Embed the case's timeline items
            if case.timeline_items:
                # Items are already denormalized from get_case
                item["source_timeline_items"] = case.timeline_items
        except Exception as e:
            logger.warning(f"Failed to embed timeline items for case {case_id}: {e}")
        
        return item

    def _strip_task_snapshot_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove snapshot fields from a task item before persistence.
        Only keeps reference fields (task_id, type, id, etc.).
        """
        if item.get("type") != "task":
            return item
        
        # Keep only reference fields, strip everything else
        return {k: v for k, v in item.items() if k in TASK_REFERENCE_FIELDS}

    async def _create_task_for_timeline_item(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        case_id: int,
        created_by: str,
    ) -> int:
        """
        Create a Task entity for a new task timeline item.
        
        Returns the task_id of the created task.
        """
        from app.services.task_service import task_service
        from app.models.models import TaskCreate
        from app.models.enums import Priority, TaskStatus
        
        # Extract task data from the timeline item
        # Prioritize title field, only fall back to description if title is None or empty
        title = item.get("title")
        if not title or not title.strip():
            title = item.get("description")
        if not title or not title.strip():
            title = "Case Task"
        
        # Ensure title doesn't exceed max length
        if len(title) > 200:
            title = title[:200]
        
        # Parse priority
        priority = Priority.MEDIUM
        if item.get("priority"):
            try:
                priority = Priority(item["priority"]) if isinstance(item["priority"], str) else item["priority"]
            except (ValueError, TypeError):
                pass
        
        # Parse status
        status = TaskStatus.TODO
        if item.get("status"):
            try:
                status = TaskStatus(item["status"]) if isinstance(item["status"], str) else item["status"]
            except (ValueError, TypeError):
                pass
        
        # Parse due_date
        due_date = None
        if item.get("due_date"):
            due_date_val = item["due_date"]
            if isinstance(due_date_val, datetime):
                due_date = due_date_val
            elif isinstance(due_date_val, str):
                try:
                    due_date = datetime.fromisoformat(due_date_val.replace("Z", "+00:00"))
                except ValueError:
                    pass
        
        task_create = TaskCreate(
            title=title,
            description=item.get("description"),
            priority=priority,
            status=status,
            assignee=item.get("assignee"),
            due_date=due_date,
            case_id=case_id,
        )
        
        task = await task_service.create_task(db, task_create, created_by)
        return task.id

    async def _update_task_for_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        item: Dict[str, Any],
        updated_by: str,
    ) -> bool:
        """
        Update a Task entity from timeline item data.
        
        Returns True if update succeeded, False if task not found.
        """
        from app.services.task_service import task_service
        from app.models.models import TaskUpdate
        from app.models.enums import Priority, TaskStatus
        
        # Build update payload from provided fields
        update_data: Dict[str, Any] = {}
        
        if "title" in item and item["title"]:
            title = item["title"]
            if len(title) > 200:
                title = title[:200]
            update_data["title"] = title
        
        if "description" in item:
            update_data["description"] = item["description"]
        
        if "priority" in item and item["priority"]:
            try:
                update_data["priority"] = Priority(item["priority"]) if isinstance(item["priority"], str) else item["priority"]
            except (ValueError, TypeError):
                pass
        
        if "status" in item and item["status"]:
            try:
                update_data["status"] = TaskStatus(item["status"]) if isinstance(item["status"], str) else item["status"]
            except (ValueError, TypeError):
                pass
        
        if "assignee" in item:
            update_data["assignee"] = item["assignee"]
        
        if "due_date" in item:
            due_date_val = item["due_date"]
            if due_date_val is None:
                update_data["due_date"] = None
            elif isinstance(due_date_val, datetime):
                update_data["due_date"] = due_date_val
            elif isinstance(due_date_val, str):
                try:
                    update_data["due_date"] = datetime.fromisoformat(due_date_val.replace("Z", "+00:00"))
                except ValueError:
                    pass
        
        if not update_data:
            return True  # Nothing to update
        
        task_update = TaskUpdate(**update_data)
        result = await task_service.update_task(db, task_id, task_update, updated_by)
        return result is not None

    async def _delete_task_for_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        deleted_by: str,
    ) -> bool:
        """Delete the Task entity associated with a timeline item."""
        from app.services.task_service import task_service
        
        try:
            return await task_service.delete_task(db, task_id, deleted_by)
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return False

    # ===== High-level Timeline Operations with Resource Sync =====

    async def add_timeline_item_with_sync(
        self,
        db: AsyncSession,
        entity: Any,
        item: Dict[str, Any],
        created_by: str,
        entity_id: Optional[int] = None,
        entity_type: str = "case",
    ) -> Dict[str, Any]:
        """
        Add a timeline item with external resource synchronization.
        
        For task items:
        - Creates the backing Task record
        - Stores only the reference (task_id) in timeline JSON
        
        For other items:
        - Adds normally via add_timeline_item
        
        Args:
            db: Database session
            entity: The case/alert entity to add the item to
            item: The timeline item data
            created_by: Username performing the action
            entity_id: The case_id for task creation (required for tasks)
            entity_type: "case" or "alert" - alerts reject task items
        
        Returns:
            The normalized item dict (with task_id for tasks)
        
        Raises:
            ValueError: If trying to add a task to an alert
        """
        item_type = item.get("type")
        
        # Alerts do not support task timeline items
        if item_type == "task" and entity_type == "alert":
            raise ValueError("Task timeline items are not supported on alerts")
        
        # Normalize the item first
        normalized = await self.normalize_item(db, item)
        
        # Handle task creation
        if item_type == "task":
            if not entity_id:
                raise ValueError("entity_id (case_id) is required for task timeline items")
            
            # Create the Task entity using the ORIGINAL item (before normalization stripped fields)
            # This sets linked_at which triggers dynamic injection
            task_id = await self._create_task_for_timeline_item(db, item, entity_id, created_by)
            
            # Don't add to timeline JSON - tasks are dynamically injected based on FK relationship
            # Return the reference for the caller
            normalized = self._strip_task_snapshot_fields(normalized)
            normalized["task_id"] = task_id
            return normalized
        
        # Add to timeline (for non-task items)
        self.add_timeline_item(entity, normalized, created_by=created_by)

        if entity_id is not None:
            from app.services.enrichment.service import enrichment_service

            await enrichment_service.maybe_enqueue_item_enrichment(
                db,
                entity=entity,
                entity_type=entity_type,
                entity_id=entity_id,
                item=normalized,
            )
        
        return normalized

    async def update_timeline_item_with_sync(
        self,
        db: AsyncSession,
        entity: Any,
        item_id: str,
        item: Dict[str, Any],
        updated_by: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Update a timeline item with external resource synchronization.
        
        For task items:
        - Routes the update to the Task entity
        - Timeline JSON remains unchanged (just holds reference)
        
        For other items:
        - Updates normally via update_timeline_item
        
        Returns:
            The updated item dict, or None if not found
        """
        # Find the existing item
        existing = self._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if not existing:
            return None
        
        item_type = existing.get("type")
        
        # Handle task updates
        if item_type == "task":
            task_id = self._resolve_task_id(existing)
            if task_id:
                # Route task-specific updates (title, status, etc.) to Task entity
                success = await self._update_task_for_timeline_item(db, task_id, item, updated_by)
                if not success:
                    logger.warning(f"Task {task_id} not found, may have been deleted")
            
            # For tasks, we need to update timeline-specific reference fields in the JSON
            # (flagged, highlighted, tags, timestamp) while leaving task entity fields alone
            timeline_specific_update = {"updated_at": datetime.now(timezone.utc).isoformat()}
            
            # Include any timeline-specific reference fields that were provided
            for field in ("flagged", "highlighted", "tags", "timestamp"):
                if field in item:
                    timeline_specific_update[field] = item[field]
            
            self.update_timeline_item(entity, item_id, timeline_specific_update, updated_by=updated_by)
            
            # Return the existing item (caller should re-read with denormalization)
            return existing
        
        # For non-task items, update normally
        normalized = await self.normalize_item(db, item)
        if not self.update_timeline_item(entity, item_id, normalized, updated_by=updated_by):
            return None
        
        return normalized

    async def remove_timeline_item_with_cleanup(
        self,
        db: AsyncSession,
        entity: Any,
        item_id: str,
        removed_by: str,
    ) -> bool:
        """
        Remove a timeline item and clean up external resources.
        
        Handles:
        - Attachments: Deletes file from storage
        - Tasks: Deletes the Task record from database
        
        Returns:
            True if item was found and removed, False otherwise
        """
        items = getattr(entity, "timeline_items", None)
        if not items:
            return False
        
        # Find the item first
        item_to_remove = self._find_item_by_id(items, item_id)
        if not item_to_remove:
            return False
        
        item_type = item_to_remove.get("type")
        
        # Clean up external resources
        if item_type == "attachment":
            storage_key = item_to_remove.get("storage_key")
            if storage_key:
                from app.services.storage_service import storage_service
                try:
                    await storage_service.delete_file(storage_key)
                    logger.info(f"Deleted file from storage: {storage_key}")
                except Exception as e:
                    logger.error(f"Failed to delete file from storage {storage_key}: {e}")
                    # Continue with removal even if storage delete fails
        
        elif item_type == "task":
            task_id = self._resolve_task_id(item_to_remove)
            if task_id:
                await self._delete_task_for_timeline_item(db, task_id, removed_by)
        
        # Remove from timeline
        return self.remove_timeline_item(entity, item_id)

    def _find_item_by_id(self, items: List[Dict[str, Any]], item_id: str) -> Optional[Dict[str, Any]]:
        """Recursively find a timeline item by ID, supporting nested replies."""
        if not items:
            return None
        for item in items:
            if item.get("id") == item_id:
                return item
            # Check replies recursively
            replies = item.get("replies")
            if replies and isinstance(replies, list):
                found = self._find_item_by_id(replies, item_id)
                if found:
                    return found
        return None

    def _add_item_metadata(self, item: Dict[str, Any], created_by: str) -> None:
        if not item.get("id"):
            item["id"] = self.generate_item_id()
        if not item.get("created_at"):
            item["created_at"] = datetime.now(timezone.utc).isoformat()
        item["created_by"] = created_by
    
    def _serialize_datetime_fields(self, item: Dict[str, Any]) -> None:
        """Ensure all datetime objects in item are converted to ISO strings for JSON storage."""
        for key, value in item.items():
            if isinstance(value, datetime):
                item[key] = value.isoformat()
            elif isinstance(value, list):
                # Handle lists that might contain dicts with datetime values
                for i, list_item in enumerate(value):
                    if isinstance(list_item, dict):
                        self._serialize_datetime_fields(list_item)

    def add_timeline_item(self, entity: Any, item: Dict[str, Any], created_by: str) -> None:
        """
        Mutate entity to append a normalized item with metadata; does not commit.
        
        If item has a parent_id, this will add it as a reply to the parent item.
        Otherwise, it will add it as a top-level timeline item.
        """
        self._ensure_list(entity)
        self._add_item_metadata(item, created_by)
        # Ensure all datetime fields are serialized to ISO strings before storing in JSON column
        self._serialize_datetime_fields(item)
        
        # Check if this is a reply (has parent_id)
        parent_id = item.get("parent_id")
        if parent_id:
            # Find parent and add as reply
            if self._add_reply_to_parent(entity.timeline_items, parent_id, item):
                flag_modified(entity, "timeline_items")
                if hasattr(entity, "updated_at"):
                    setattr(entity, "updated_at", datetime.now(timezone.utc))
                return
            else:
                # Parent not found - add as top-level item anyway (graceful degradation)
                # Could also raise an error here if strict validation is needed
                pass
        
        # Add as top-level item
        entity.timeline_items.append(item)
        # Mark the JSON column as modified so SQLAlchemy knows to update it
        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            setattr(entity, "updated_at", datetime.now(timezone.utc))
    
    def _add_reply_to_parent(self, items: List[Dict[str, Any]], parent_id: str, reply: Dict[str, Any]) -> bool:
        """
        Recursively search for parent item and add reply to it.
        Returns True if parent found and reply added, False otherwise.
        """
        for item in items:
            if item.get("id") == parent_id:
                # Found parent - add reply
                if "replies" not in item:
                    item["replies"] = []
                item["replies"].append(reply)
                return True
            
            # Check nested replies
            if item.get("replies"):
                if self._add_reply_to_parent(item["replies"], parent_id, reply):
                    return True
        
        return False

    def update_timeline_item(self, entity: Any, item_id: str, updated: Dict[str, Any], updated_by: str) -> bool:
        """
        Update a timeline item by id; preserves created_* fields; returns True if found and updated.
        Supports nested replies at any depth.
        """
        items = getattr(entity, "timeline_items", None)
        if not items:
            return False
        
        # Try to update recursively
        if self._update_item_recursive(items, item_id, updated, updated_by):
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                setattr(entity, "updated_at", datetime.now(timezone.utc))
            return True
        
        return False
    
    def _update_item_recursive(self, items: List[Dict[str, Any]], item_id: str, updated: Dict[str, Any], updated_by: str) -> bool:
        """Recursively search and update a timeline item by ID."""
        for idx, item in enumerate(items):
            if item.get("id") == item_id:
                # Found the item - update it
                created_at = item.get("created_at")
                created_by = item.get("created_by")
                existing_replies = item.get("replies")  # Preserve existing replies
                
                new_item = {**item, **updated}
                new_item["id"] = item_id
                new_item["created_at"] = created_at
                new_item["created_by"] = created_by
                new_item["updated_at"] = datetime.now(timezone.utc).isoformat()
                new_item["updated_by"] = updated_by
                
                # Preserve existing replies - don't allow updates to overwrite the replies structure
                # Replies should only be modified through add_timeline_item with parent_id
                if existing_replies is not None:
                    new_item["replies"] = existing_replies
                
                # Ensure all datetime objects are serialized to ISO format strings
                for key, value in new_item.items():
                    if isinstance(value, datetime):
                        new_item[key] = value.isoformat()
                
                items[idx] = new_item
                return True
            
            # Check nested replies recursively
            replies = item.get('replies')
            if replies and isinstance(replies, list):
                if self._update_item_recursive(replies, item_id, updated, updated_by):
                    return True
        
        return False

    def remove_timeline_item(self, entity: Any, item_id: str) -> bool:
        """
        Remove a timeline item by id; returns True if item removed.
        Supports removing nested replies at any depth.
        """
        items = getattr(entity, "timeline_items", None)
        if not items:
            return False
        
        if self._remove_item_recursive(items, item_id):
            # Mark the JSON column as modified so SQLAlchemy knows to update it
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                setattr(entity, "updated_at", datetime.now(timezone.utc))
            return True
        
        return False
    
    def _remove_item_recursive(self, items: List[Dict[str, Any]], item_id: str) -> bool:
        """Recursively search and remove a timeline item by ID."""
        # Try to remove at current level
        original_len = len(items)
        items[:] = [it for it in items if it.get("id") != item_id]
        if len(items) < original_len:
            return True
        
        # Item not found at this level - check nested replies
        for item in items:
            replies = item.get('replies')
            if replies and isinstance(replies, list):
                if self._remove_item_recursive(replies, item_id):
                    return True
        
        return False


timeline_service = TimelineService()
