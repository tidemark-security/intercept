from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, cast, String
from sqlalchemy.orm import defer
from sqlmodel import col
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import logging
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate

from app.core.entity_ids import TASK_PREFIX
from app.models.models import Task, TaskCreate, TaskUpdate, TaskTimelineItem, UserAccount
from app.models.enums import TaskStatus, RealtimeEventType
from app.services.timeline_add_service import (
    TimelineItemConflict,
    add_timeline_item_and_commit,
    remove_timeline_item_and_commit,
    update_timeline_item_and_commit,
)
from app.services.timeline_service import TimelineValidationError, timeline_service
from app.services.audit_service import get_audit_service
from app.services.realtime_service import emit_event
from app.services.date_filter_utils import DateFilterValidationError, parse_datetime_filter
from app.services.tag_filter_utils import append_tag_filters, normalize_persisted_tags
from app.services.committed_response import load_committed_response

logger = logging.getLogger(__name__)


class TaskValidationError(ValueError):
    """A task operation violates a client-facing domain rule."""


_TASK_STATUS_DESCRIPTIONS = {
    TaskStatus.TODO: "Task status changed to To Do",
    TaskStatus.IN_PROGRESS: "Task status changed to In Progress",
    TaskStatus.DONE: "Task marked as Done",
}


def _task_status_description(status: TaskStatus) -> str:
    return _TASK_STATUS_DESCRIPTIONS.get(status, f"Task status changed to {status}")


class TaskService:

    @staticmethod
    def _validate_task_timeline_item(item_dict: Dict[str, Any]) -> None:
        if item_dict.get("type") == "task":
            raise TaskValidationError(
                "Task timeline items cannot be added to tasks. Tasks cannot be nested."
            )

    async def create_task(
        self, 
        db: AsyncSession, 
        task_data: TaskCreate, 
        created_by: str,
        created_at_override: Optional[datetime] = None,
    ) -> Task:
        """Create a new task.
        
        Per FR-001 from spec: If no assignee specified, default to creator.
        """
        try:
            db_task = await self.create_task_in_transaction(
                db,
                task_data,
                created_by,
                created_at_override=created_at_override,
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating task: {e}")
            raise

        task_id = db_task.id  # type: ignore[assignment]
        logger.info(
            "Task %s created by %s, assigned to %s",
            task_id,
            created_by,
            db_task.assignee,
        )
        return await load_committed_response(
            db,
            lambda: self.get_task(db, task_id),
            db_task,
            logger=logger,
            entity_type="task",
            entity_id=task_id,
            operation="creation",
        )

    async def create_task_in_transaction(
        self,
        db: AsyncSession,
        task_data: TaskCreate,
        created_by: str,
        created_at_override: Optional[datetime] = None,
    ) -> Task:
        """Create and flush a task while leaving commit ownership to the caller."""
        assignee = task_data.assignee if task_data.assignee else created_by
        task_kwargs = {
            "title": task_data.title,
            "description": task_data.description,
            "priority": task_data.priority,
            "due_date": task_data.due_date,
            "picerl_stage": task_data.picerl_stage,
            "status": task_data.status or TaskStatus.TODO,
            "assignee": assignee,
            "case_id": task_data.case_id,
            "linked_at": datetime.now(timezone.utc) if task_data.case_id else None,
            "created_by": created_by,
            "tags": normalize_persisted_tags(task_data.tags),
        }
        if created_at_override is not None:
            task_kwargs["created_at"] = created_at_override

        db_task = Task(**task_kwargs)
        db.add(db_task)
        await db.flush()
        return db_task
    
    async def _get_task_model(self, db: AsyncSession, task_id: int) -> Optional[Task]:
        """Get the tracked task model."""
        result = await db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

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

        return await timeline_service.prepare_entity_detail_timeline(
            db,
            entity_type="task",
            entity_id=task_id,
            entity=db_task,
            human_prefix=TASK_PREFIX,
            include_linked_timelines=include_linked_timelines,
        )
    
    async def get_tasks(
        self, 
        db: AsyncSession, 
        status: Optional[List[TaskStatus]] = None,
        assignee: Optional[str] = None,
        case_id: Optional[int] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Page[Task]:
        """Get tasks with optional filtering and pagination.
        
        Args:
            status: Filter by task status (can filter by multiple statuses)
            assignee: Filter by assignee username (exact match)
            case_id: Filter by case ID (for tasks linked to a specific case)
            include_tags: Tags tasks must include
            exclude_tags: Tags tasks must exclude
            search: Search string to match against task title or description (case-insensitive partial match)
            start_date: Filter tasks created after this UTC datetime (ISO8601 format with 'Z' suffix)
            end_date: Filter tasks created before this UTC datetime (ISO8601 format with 'Z' suffix)
        """
        # Defer timeline_items because list responses do not need the potentially
        # malformed legacy JSON that detail views normalize separately.
        query = select(Task).options(defer(Task.timeline_items))
        filters = []
        if status:
            filters.append(col(Task.status).in_(status))
        if assignee:
            filters.append(
                Task.assignee.is_(None)  # type: ignore
                if assignee == "__unassigned__"
                else Task.assignee == assignee
            )
        if case_id is not None:
            filters.append(Task.case_id == case_id)

        append_tag_filters(filters, Task.tags, include_tags, exclude_tags)
        try:
            start_dt = parse_datetime_filter(start_date, parameter="start_date")
            end_dt = parse_datetime_filter(end_date, parameter="end_date")
        except DateFilterValidationError as exc:
            raise TaskValidationError(str(exc)) from exc

        if start_dt is not None:
            filters.append(Task.created_at >= start_dt)
        if end_dt is not None:
            filters.append(Task.created_at <= end_dt)
        if search:
            search_pattern = f"%{search}%"
            filters.append(
                or_(
                    col(Task.title).ilike(search_pattern),
                    cast(Task.description, String).ilike(search_pattern),  # type: ignore[arg-type]
                )
            )
        if filters:
            query = query.where(and_(*filters))

        allowed_sort_columns = {
            "id": Task.id,
            "title": Task.title,
            "status": Task.status,
            "priority": Task.priority,
            "assignee": Task.assignee,
            "created_at": Task.created_at,
            "updated_at": Task.updated_at,
        }
        try:
            sort_column = allowed_sort_columns[sort_by]
        except KeyError as exc:
            raise TaskValidationError(
                f"Unsupported task sort column: {sort_by}"
            ) from exc
        ordering = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()
        return await apaginate(db, query.order_by(ordering))

    async def update_task(
        self, 
        db: AsyncSession, 
        task_id: int, 
        task_update: TaskUpdate, 
        updated_by: str
    ) -> Optional[Task]:
        """Update a task. Updated_at timestamp is automatically refreshed."""
        try:
            outcome = await self.update_task_in_transaction(
                db,
                task_id,
                task_update,
                updated_by,
            )
            if outcome is None:
                return None
            db_task, autonomous_assignee = outcome
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating task {task_id}: {e}")
            raise


        if autonomous_assignee is not None:
            await self.enqueue_autonomous_task_after_commit(
                db,
                task_id=task_id,
                assignee=autonomous_assignee,
            )

        logger.info(f"Task {task_id} updated by {updated_by}")
        return await load_committed_response(
            db,
            lambda: self.get_task(db, task_id),
            db_task,
            logger=logger,
            entity_type="task",
            entity_id=task_id,
            operation="update",
        )

    async def update_task_in_transaction(
        self,
        db: AsyncSession,
        task_id: int,
        task_update: TaskUpdate,
        updated_by: str,
    ) -> Optional[tuple[Task, Optional[str]]]:
        """Update and audit a locked task while leaving commit ownership to the caller.

        The optional string in the result is an assignee whose autonomous task
        should be enqueued only after the owning transaction commits.
        """
        update_data = task_update.model_dump(exclude_unset=True)
        destination_case_id = update_data.get("case_id")
        if destination_case_id is not None:
            # Preserve the task-not-found result while establishing the global
            # parent-before-child lock order used by case closure.
            existence_result = await db.execute(
                select(Task.id).where(Task.id == task_id)
            )
            if existence_result.scalar_one_or_none() is None:
                return None

            from app.services.case_service import case_service

            destination_case = await case_service.lock_case_for_update(
                db,
                destination_case_id,
            )
            if destination_case is None:
                raise TaskValidationError(f"Case {destination_case_id} not found")

        result = await db.execute(
            select(Task)
            .where(Task.id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        db_task = result.scalar_one_or_none()
        if db_task is None:
            return None

        old_status = db_task.status
        original_values = {
            field: getattr(db_task, field, None)
            for field in update_data
            if hasattr(db_task, field)
        }

        old_case_id = db_task.case_id
        old_assignee = db_task.assignee
        now = datetime.now(timezone.utc)
        if "case_id" in update_data and update_data["case_id"] != old_case_id:
            if old_case_id is not None:
                raise TaskValidationError(
                    "Task case reassignment is not allowed; unlink before linking to another case"
                )

        for field, new_value in update_data.items():
            if not hasattr(db_task, field):
                continue
            if field == "tags":
                new_value = normalize_persisted_tags(new_value)
            setattr(db_task, field, new_value)

        if db_task.case_id and not old_case_id:
            db_task.linked_at = now
        elif not db_task.case_id and old_case_id:
            db_task.linked_at = None

        db_task.updated_at = now
        status_changed = db_task.status != old_status
        if status_changed and updated_by:
            status_change_item = timeline_service.build_note_item(
                description=_task_status_description(db_task.status),
                created_by=updated_by,
                created_at=now.isoformat(),
                timestamp=now.isoformat(),
                tags=["status-change"],
            )
            timeline_service.add_timeline_item(db_task, status_change_item, created_by=updated_by)

        await emit_event(
            db,
            entity_type="task",
            entity_id=task_id,
            event_type=RealtimeEventType.ENTITY_UPDATED,
            performed_by=updated_by,
        )

        changed_fields = [
            field
            for field in update_data
            if field in original_values
            and str(original_values.get(field)) != str(getattr(db_task, field, None))
        ]
        if changed_fields:
            await get_audit_service(db).log_entity_updated(
                entity_type="task",
                entity_id=task_id,
                before={field: original_values[field] for field in changed_fields},
                after={field: getattr(db_task, field, None) for field in changed_fields},
                user=updated_by,
            )

        await db.flush()
        autonomous_assignee = (
            db_task.assignee
            if db_task.assignee and db_task.assignee != old_assignee
            else None
        )
        return db_task, autonomous_assignee

    async def enqueue_autonomous_task_after_commit(
        self,
        db: AsyncSession,
        *,
        task_id: int,
        assignee: str,
    ) -> None:
        """Best-effort autonomous enqueue for an already committed task update."""
        try:
            await self._enqueue_autonomous_task_if_assigned_to_nhi(
                db,
                task_id=task_id,
                assignee=assignee,
            )
        except Exception:
            logger.exception(
                "Task %s was updated, but autonomous execution could not be enqueued",
                task_id,
            )

    async def _enqueue_autonomous_task_if_assigned_to_nhi(
        self,
        db: AsyncSession,
        *,
        task_id: int,
        assignee: str,
    ) -> None:
        from sqlalchemy import select

        from app.models.enums import AccountType, UserStatus
        from app.models.models import UserAccount
        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_AUTONOMOUS_TASK

        result = await db.execute(
            select(UserAccount).where(
                UserAccount.username == assignee,
                UserAccount.account_type == AccountType.NHI,
                UserAccount.status == UserStatus.ACTIVE,
                UserAccount.assignable.is_(True),  # type: ignore[attr-defined]
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            return

        try:
            queue = get_task_queue_service()
        except RuntimeError:
            logger.warning("Task queue not available; autonomous task was not enqueued", extra={"task_id": task_id})
            return

        await queue.enqueue(
            task_name=TASK_AUTONOMOUS_TASK,
            payload={"task_id": task_id, "agent_username": agent.username},
            dedupe_key=f"autonomous_task:{task_id}:{agent.username}",
        )
    
    async def delete_task(
        self, 
        db: AsyncSession, 
        task_id: int, 
        deleted_by: str
    ) -> bool:
        """Delete a task."""
        try:
            if not await self.delete_task_in_transaction(db, task_id, deleted_by):
                return False
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting task {task_id}: {e}")
            raise

        logger.info(f"Task {task_id} deleted by {deleted_by}")
        return True

    async def delete_task_in_transaction(
        self,
        db: AsyncSession,
        task_id: int,
        deleted_by: str,
    ) -> bool:
        """Audit and delete a task while leaving commit ownership to the caller."""
        result = await db.execute(
            select(Task).where(Task.id == task_id).with_for_update()
        )
        db_task = result.scalar_one_or_none()
        if db_task is None:
            return False

        old_value = {
            "id": db_task.id,
            "title": db_task.title,
            "description": db_task.description,
            "status": db_task.status,
            "priority": db_task.priority,
            "assignee": db_task.assignee,
            "case_id": db_task.case_id,
        }
        await get_audit_service(db).log_entity_deleted(
            entity_type="task",
            entity_id=task_id,
            user=deleted_by,
            old_value=old_value,
        )
        await db.delete(db_task)
        return True

    async def add_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        timeline_item: TaskTimelineItem,
        added_by: str,
        created_at_override: Optional[datetime] = None,
        preserve_item_id: bool = False,
    ) -> Optional[Task]:
        """Add a single timeline item to a task's timeline.
        
        Note: Task items (type='task') are not allowed on task timelines.
        Tasks cannot be nested within other tasks.
        """
        try:
            committed_task = await self._get_task_model(db, task_id)
            if committed_task is None:
                return None
            added_item = await add_timeline_item_and_commit(
                db,
                entity_id=task_id,
                entity_type="task",
                timeline_item=timeline_item,
                performed_by=added_by,
                validate_item=self._validate_task_timeline_item,
                created_at_override=created_at_override,
                preserve_item_id=preserve_item_id,
            )
            if added_item is None:
                return None
        except TaskValidationError:
            await db.rollback()
            raise
        except TimelineValidationError as exc:
            await db.rollback()
            raise TaskValidationError(str(exc)) from exc
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding timeline item to task {task_id}: {e}")
            raise

        logger.info(f"Timeline item added to task by {added_by}")
        return await load_committed_response(
            db,
            lambda: self.get_task(db, task_id),
            committed_task,
            logger=logger,
            entity_type="task",
            entity_id=task_id,
            operation="timeline item addition",
        )

    async def update_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        item_id: str,
        updated_item: TaskTimelineItem,
        updated_by: str,
        expected_item_fields: dict[str, Any] | None = None,
    ) -> Optional[Task]:
        """Update a specific timeline item in a task with permission checks and audit logging."""
        try:
            committed_task = await self._get_task_model(db, task_id)
            if committed_task is None:
                return None
            updated_dict = await update_timeline_item_and_commit(
                db,
                entity_id=task_id,
                entity_type="task",
                item_id=item_id,
                timeline_item=updated_item,
                performed_by=updated_by,
                expected_item_fields=expected_item_fields,
            )

            if updated_dict is None:
                return None
        except TaskValidationError:
            await db.rollback()
            raise
        except TimelineValidationError as exc:
            await db.rollback()
            raise TaskValidationError(str(exc)) from exc
        except TimelineItemConflict:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating timeline item {item_id} in task {task_id}: {e}")
            raise

        logger.info(
            f"Timeline item {item_id} (type: {updated_dict.get('type')}) updated in task {task_id} by {updated_by}"
        )
        return await load_committed_response(
            db,
            lambda: self.get_task(db, task_id),
            committed_task,
            logger=logger,
            entity_type="task",
            entity_id=task_id,
            operation="timeline item update",
        )

    async def remove_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        item_id: str,
        removed_by: str
    ) -> Optional[Task]:
        """Remove a specific timeline item from a task and clean up associated resources."""
        try:
            committed_task = await self._get_task_model(db, task_id)
            if committed_task is None:
                return None
            removed_item = await remove_timeline_item_and_commit(
                db,
                entity_id=task_id,
                entity_type="task",
                item_id=item_id,
                performed_by=removed_by,
            )
            if removed_item is None:
                return None
        except TaskValidationError:
            await db.rollback()
            raise
        except TimelineValidationError as exc:
            await db.rollback()
            raise TaskValidationError(str(exc)) from exc
        except Exception as e:
            await db.rollback()
            logger.error(f"Error removing timeline item {item_id} from task {task_id}: {e}")
            raise

        logger.info(f"Timeline item {item_id} removed from task by {removed_by}")
        return await load_committed_response(
            db,
            lambda: self.get_task(db, task_id),
            committed_task,
            logger=logger,
            entity_type="task",
            entity_id=task_id,
            operation="timeline item removal",
        )

# Singleton instance
task_service = TaskService()
