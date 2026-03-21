from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from fastapi_pagination import Page
import logging

from app.core.database import get_db
from app.services.task_service import task_service
from app.models.models import (
    TaskCreate,
    TaskUpdate,
    TaskRead,
    TaskTimelineItem,
    UserAccount,
    PresignedUploadRequest,
    PresignedUploadResponse,
    AttachmentStatusUpdate,
    PresignedDownloadResponse,
)
from app.models.enums import TaskStatus
from app.api.route_utils import (
    get_timeline_item_types,
    create_timeline_converter,
    create_human_id_decorator,
    handle_generate_upload_url,
    handle_update_attachment_status,
    handle_generate_download_url,
)
from app.api.routes.admin_auth import require_authenticated_user, require_non_auditor_user

logger = logging.getLogger(__name__)

ID_PREFIX = "TSK-"
router = APIRouter(
    prefix="/tasks", 
    tags=["tasks"],
    dependencies=[Depends(require_authenticated_user)]
)

# Dynamically discovered timeline item types and converter
TIMELINE_ITEM_TYPES = get_timeline_item_types(TaskTimelineItem)
convert_timeline_item = create_timeline_converter(TIMELINE_ITEM_TYPES)

# Human ID decorator configured for tasks
handle_human_id = create_human_id_decorator(ID_PREFIX, "task_id")


@router.post("", response_model=TaskRead)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Create a new task.
    
    If no assignee is specified, the task will be assigned to the creator (per spec requirement).
    Tasks can optionally be linked to a case via case_id.
    """
    try:
        db_task = await task_service.create_task(db, task_data, current_user.username)
        return db_task
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating task: {str(e)}")


@router.get("", response_model=Page[TaskRead])
async def get_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    status: Optional[List[TaskStatus]] = Query(None, description="Filter by multiple task statuses"),
    assignee: Optional[str] = None,
    case_id: Optional[int] = Query(None, description="Filter by case ID"),
    search: Optional[str] = Query(None, description="Search tasks by title or description (case-insensitive partial match)"),
    start_date: Optional[str] = Query(None, description="Filter tasks created after this UTC datetime (ISO8601 format with 'Z' suffix)"),
    end_date: Optional[str] = Query(None, description="Filter tasks created before this UTC datetime (ISO8601 format with 'Z' suffix)"),
    db: AsyncSession = Depends(get_db)
):
    """Get tasks with optional filtering and pagination.
    
    Returns a paginated response with items, total count, page information.
    Search parameter matches against task title or description using case-insensitive partial matching.
    Date filtering expects UTC ISO8601 strings with 'Z' suffix (e.g., "2025-10-20T14:30:00Z").
    Tasks are filtered by created_at timestamp.
    """
    try:
        tasks = await task_service.get_tasks(
            db, skip=skip, limit=limit, status=status, assignee=assignee,
            case_id=case_id, search=search, start_date=start_date, end_date=end_date
        )
        return tasks
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching tasks: {str(e)}")


@router.get("/{task_id}", response_model=TaskRead)
@handle_human_id()
async def get_task(
    task_id: int,
    request: Request,  # pylint: disable=unused-argument
    include_linked_timelines: bool = Query(
        False,
        description="Include timeline items from linked cases and alerts as nested source_timeline_items"
    ),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific task by ID or human ID (TSK-0000001).
    
    When include_linked_timelines=true, case and alert timeline items will include
    a source_timeline_items field containing the timeline from the linked entity.
    """
    try:
        db_task = await task_service.get_task(db, task_id, include_linked_timelines=include_linked_timelines)
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        return db_task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching task: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching task: {str(e)}")


@router.put("/{task_id}", response_model=TaskRead)
@handle_human_id()
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Update a task.
    
    The updated_at timestamp is automatically refreshed on any update (per spec requirement).
    """
    try:
        db_task = await task_service.update_task(db, task_id, task_update, current_user.username)
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        return db_task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating task: {str(e)}")


@router.delete("/{task_id}")
@handle_human_id()
async def delete_task(
    task_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Delete a task."""
    try:
        success = await task_service.delete_task(db, task_id, current_user.username)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting task: {str(e)}")


# ---------------------------------------------------------------------------
# Timeline Endpoints
# ---------------------------------------------------------------------------


@router.post("/{task_id}/timeline", response_model=TaskRead)
@handle_human_id()
async def add_timeline_item(
    task_id: int,
    request: Request,  # pylint: disable=unused-argument
    timeline_item: dict,  # Using dict for now since we need to handle different timeline item types
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Add a timeline item to a task."""
    try:
        typed_item = convert_timeline_item(timeline_item)
        db_task = await task_service.add_timeline_item(db, task_id, typed_item, current_user.username)
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        return db_task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding timeline item to task: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding timeline item: {str(e)}")


@router.put("/{task_id}/timeline/{item_id}", response_model=TaskRead)
@handle_human_id()
async def update_timeline_item(
    task_id: int,
    request: Request,  # pylint: disable=unused-argument
    item_id: str,
    timeline_item: dict,  # Using dict for now since we need to handle different timeline item types
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Update a specific timeline item in a task."""
    try:
        typed_item = convert_timeline_item(timeline_item)
        db_task = await task_service.update_timeline_item(db, task_id, item_id, typed_item, current_user.username)
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        return db_task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating timeline item in task: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating timeline item: {str(e)}")


@router.delete("/{task_id}/timeline/{item_id}", response_model=TaskRead)
@handle_human_id()
async def remove_timeline_item(
    task_id: int,
    request: Request,  # pylint: disable=unused-argument
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Remove a specific timeline item from a task."""
    try:
        db_task = await task_service.remove_timeline_item(db, task_id, item_id, current_user.username)
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        return db_task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing timeline item from task: {e}")
        raise HTTPException(status_code=500, detail=f"Error removing timeline item: {str(e)}")


# ---------------------------------------------------------------------------
# Attachment Endpoints
# ---------------------------------------------------------------------------


@router.post("/{task_id}/timeline/attachments/upload-url", response_model=PresignedUploadResponse)
@handle_human_id()
async def generate_upload_url(
    task_id: int,
    request: Request,  # pylint: disable=unused-argument
    request_data: PresignedUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Generate presigned upload URL and create timeline attachment item."""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return await handle_generate_upload_url(
        entity_type="task", parent_id=task_id, request_data=request_data,
        current_user=current_user, db=db, service=task_service,
    )


@router.patch("/{task_id}/timeline/items/{item_id}/status", response_model=TaskRead)
@handle_human_id()
async def update_attachment_status(
    task_id: int,
    item_id: str,
    request: Request,  # pylint: disable=unused-argument
    update_data: AttachmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Update attachment upload status."""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return await handle_update_attachment_status(
        entity=task, entity_type="task", parent_id=task_id,
        item_id=item_id, update_data=update_data,
        current_user=current_user, db=db, service=task_service,
    )


@router.get("/{task_id}/timeline/items/{item_id}/download-url", response_model=PresignedDownloadResponse)
@handle_human_id()
async def generate_download_url(
    task_id: int,
    item_id: str,
    request: Request,  # pylint: disable=unused-argument
    download: bool = Query(False, description="Generate a forced-download URL"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Generate presigned download URL for an attachment."""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return await handle_generate_download_url(
        entity=task, entity_type="task", parent_id=task_id,
        item_id=item_id, as_download=download, current_user=current_user,
    )
