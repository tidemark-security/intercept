from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from fastapi_pagination import Page
from datetime import datetime, timezone, timedelta
import logging

from app.core.database import get_db
from app.services.task_service import task_service
from app.services.storage_service import storage_service
from app.core.storage_config import storage_config
from app.models.models import TaskCreate, TaskUpdate, TaskRead, TaskTimelineItem, UserAccount, PresignedDownloadResponse
from app.models.enums import TaskStatus
from app.api.route_utils import get_timeline_item_types, create_timeline_converter, create_human_id_decorator
from app.api.routes.admin_auth import require_authenticated_user

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
    current_user: UserAccount = Depends(require_authenticated_user)
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
    current_user: UserAccount = Depends(require_authenticated_user)
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
    current_user: UserAccount = Depends(require_authenticated_user)
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
    current_user: UserAccount = Depends(require_authenticated_user)
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
    current_user: UserAccount = Depends(require_authenticated_user)
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
    current_user: UserAccount = Depends(require_authenticated_user)
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
# Attachment Download Endpoints
# ---------------------------------------------------------------------------


@router.get("/{task_id}/timeline/items/{item_id}/download-url", response_model=PresignedDownloadResponse)
@handle_human_id()
async def generate_download_url(
    task_id: int,
    item_id: str,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """
    Generate presigned download URL for an attachment.
    
    This endpoint:
    1. Verifies the timeline item exists and is an attachment
    2. Verifies upload is complete
    3. Generates a presigned GET URL for download
    4. Returns the URL and file metadata
    """
    try:
        # Get task
        task = await task_service.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Find timeline item
        timeline_item = None
        for item in task.timeline_items if task.timeline_items else []:
            if item.get("id") == item_id and item.get("type") == "attachment":
                timeline_item = item
                break
        
        if not timeline_item:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment item {item_id} not found"
            )
        
        # Verify upload is complete
        upload_status = timeline_item.get("upload_status", "complete")
        if upload_status != "complete":
            raise HTTPException(
                status_code=400,
                detail=f"Attachment upload still in progress (status: {upload_status})"
            )
        
        # Get storage key
        storage_key = timeline_item.get("storage_key")
        if not storage_key:
            raise HTTPException(
                status_code=400,
                detail="Attachment has no storage key"
            )
        
        # Verify file exists
        file_exists = await storage_service.verify_file_exists(storage_key)
        if not file_exists:
            raise HTTPException(
                status_code=410,
                detail="File no longer available in storage"
            )
        
        # Generate presigned download URL
        download_url = await storage_service.generate_presigned_download_url(
            storage_key,
            expires_minutes=storage_config.download_timeout_minutes
        )
        
        # Calculate expiration timestamp
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=storage_config.download_timeout_minutes
        )
        
        # Log download URL generation
        logger.info(
            f"Generated presigned download URL for task {task_id}, "
            f"item {item_id}, file {timeline_item.get('file_name')}, "
            f"user {current_user.username}, "
            f"expires {expires_at}"
        )
        
        return PresignedDownloadResponse(
            download_url=download_url,
            filename=timeline_item.get("file_name", "attachment"),
            mime_type=timeline_item.get("mime_type", "application/octet-stream"),
            file_size=timeline_item.get("file_size", 0),
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating download URL for task {task_id}, item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {str(e)}"
        )
