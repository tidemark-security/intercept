from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional
from fastapi_pagination import Page
import uuid
from datetime import datetime, timezone, timedelta
import logging

from app.core.database import get_db
from app.services.case_service import case_service
from app.services.storage_service import storage_service
from app.core.storage_config import storage_config
from app.models.models import (
    CaseCreate, CaseUpdate, CaseRead, 
    CaseReadWithAlerts, CaseTimelineItem, UserAccount,
    PresignedUploadRequest, PresignedUploadResponse,
    AttachmentStatusUpdate, PresignedDownloadResponse,
    AttachmentItem
)
from app.models.enums import CaseStatus, UploadStatus
from app.api.route_utils import get_timeline_item_types, create_timeline_converter, create_human_id_decorator
from app.api.routes.admin_auth import require_authenticated_user

logger = logging.getLogger(__name__)

ID_PREFIX = "CAS-"
router = APIRouter(
    prefix="/cases", 
    tags=["cases"],
    dependencies=[Depends(require_authenticated_user)]
)

# Dynamically discovered timeline item types and converter
TIMELINE_ITEM_TYPES = get_timeline_item_types(CaseTimelineItem)
convert_timeline_item = create_timeline_converter(TIMELINE_ITEM_TYPES)

# Human ID decorator configured for cases
handle_human_id = create_human_id_decorator(ID_PREFIX, "case_id")


@router.post("", response_model=CaseRead)
async def create_case(
    case_data: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Create a new case."""
    try:
        db_case = await case_service.create_case(db, case_data, current_user.username)
        return db_case
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating case: {str(e)}")


@router.get("", response_model=Page[CaseRead])
async def get_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    status: Optional[List[CaseStatus]] = Query(None, description="Filter by multiple case statuses"),
    assignee: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search cases by title or description (case-insensitive partial match)"),
    start_date: Optional[str] = Query(None, description="Filter cases created after this UTC datetime (ISO8601 format with 'Z' suffix)"),
    end_date: Optional[str] = Query(None, description="Filter cases created before this UTC datetime (ISO8601 format with 'Z' suffix)"),
    db: AsyncSession = Depends(get_db)
):
    """Get cases with optional filtering and pagination.
    
    Returns a paginated response with items, total count, page information.
    Search parameter matches against case title or description using case-insensitive partial matching.
    Date filtering expects UTC ISO8601 strings with 'Z' suffix (e.g., "2025-10-20T14:30:00Z").
    Cases are filtered by created_at timestamp.
    """
    try:
        cases = await case_service.get_cases(
            db, skip=skip, limit=limit, status=status, assignee=assignee, search=search,
            start_date=start_date, end_date=end_date
        )
        return cases
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cases: {str(e)}")


@router.get("/{case_id}", response_model=CaseReadWithAlerts)
@handle_human_id()
async def get_case(
    case_id: int,
    request: Request, # pylint: disable=unused-argument
    include_linked_timelines: bool = Query(
        False,
        description="Include timeline items from linked alerts and tasks as nested source_timeline_items"
    ),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific case with alerts and audit logs.
    
    When include_linked_timelines=true, alert and task timeline items will include
    a source_timeline_items field containing the timeline from the linked entity.
    """
    try:
        db_case = await case_service.get_case(db, case_id, include_linked_timelines=include_linked_timelines)
        if not db_case:
            raise HTTPException(status_code=404, detail="Case not found")
        return db_case
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching case: {str(e)}")


@router.put("/{case_id}", response_model=CaseRead)
@handle_human_id()
async def update_case(
    case_id: int,
    request: Request, # pylint: disable=unused-argument
    case_update: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Update a case."""
    try:
        db_case = await case_service.update_case(db, case_id, case_update, current_user.username)
        if not db_case:
            raise HTTPException(status_code=404, detail="Case not found")
        return db_case
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating case: {str(e)}")


@router.delete("/{case_id}")
@handle_human_id()
async def delete_case(
    case_id: int,
    request: Request, # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Delete a case."""
    try:
        success = await case_service.delete_case(db, case_id, current_user.username)
        if not success:
            raise HTTPException(status_code=404, detail="Case not found")
        return {"message": "Case deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting case: {str(e)}")


# Timeline endpoints
@router.post("/{case_id}/timeline", response_model=CaseRead)
@handle_human_id()
async def add_timeline_item(
    case_id: int,
    request: Request, # pylint: disable=unused-argument
    timeline_item: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Add a timeline item to a case."""
    try:
        typed_item = convert_timeline_item(timeline_item)
        db_case = await case_service.add_timeline_item(db, case_id, typed_item, current_user.username)
        if not db_case:
            raise HTTPException(status_code=404, detail="Case not found")
        return db_case
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding timeline item: {str(e)}")


@router.put("/{case_id}/timeline/{item_id}", response_model=CaseRead)
@handle_human_id()
async def update_timeline_item(
    case_id: int,
    request: Request, # pylint: disable=unused-argument
    item_id: str,
    timeline_item: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Update a timeline item in a case."""
    try:
        typed_item = convert_timeline_item(timeline_item)
        db_case = await case_service.update_timeline_item(db, case_id, item_id, typed_item, current_user.username)
        if not db_case:
            raise HTTPException(status_code=404, detail="Case or timeline item not found")
        return db_case
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating timeline item: {str(e)}")


@router.delete("/{case_id}/timeline/{item_id}", response_model=CaseRead)
@handle_human_id()
async def remove_timeline_item(
    case_id: int,
    request: Request, # pylint: disable=unused-argument
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Remove a timeline item from a case."""
    try:
        db_case = await case_service.remove_timeline_item(db, case_id, item_id, current_user.username)
        if not db_case:
            raise HTTPException(status_code=404, detail="Case or timeline item not found")
        return db_case
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing timeline item: {str(e)}")


# ---------------------------------------------------------------------------
# File Upload Endpoints
# ---------------------------------------------------------------------------

@router.post("/{case_id}/timeline/attachments/upload-url", response_model=PresignedUploadResponse)
@handle_human_id()
async def generate_upload_url(
    case_id: int,
    request_data: PresignedUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """
    Generate presigned upload URL and create timeline attachment item.
    
    This endpoint:
    1. Validates file size and type
    2. Creates an AttachmentItem with 'uploading' status
    3. Generates a presigned PUT URL for direct upload to storage
    4. Returns the URL and item metadata
    """
    try:
        # Verify case exists
        case = await case_service.get_case(db, case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
        # Validate file size
        if not storage_service.validate_file_size(request_data.file_size):
            max_size_mb = storage_config.max_upload_size_mb
            raise HTTPException(
                status_code=413,
                detail=f"File size {request_data.file_size} exceeds limit {max_size_mb}MB"
            )
        
        # Validate file type (if provided by client)
        if request_data.mime_type and not storage_service.validate_file_type(request_data.mime_type):
            raise HTTPException(
                status_code=415,
                detail=f"File type {request_data.mime_type} not allowed"
            )
        
        # Sanitize filename
        sanitized_filename = storage_service.sanitize_filename(request_data.filename)
        
        # Generate unique item ID and storage key
        item_id = str(uuid.uuid4())
        storage_key = storage_service.generate_storage_key(
            case_id, item_id, sanitized_filename, parent_type="cases"
        )
        
        # Create attachment timeline item with "uploading" status
        attachment_item = AttachmentItem(
            id=item_id,
            type="attachment",
            file_name=sanitized_filename,
            mime_type=request_data.mime_type,
            file_size=request_data.file_size,
            storage_key=storage_key,
            upload_status=UploadStatus.UPLOADING,
            uploaded_by=current_user.username,
            created_by=current_user.username,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add to case timeline
        case = await case_service.add_timeline_item(
            db, case_id, attachment_item, current_user.username
        )
        
        # Generate presigned upload URL
        upload_url = await storage_service.generate_presigned_upload_url(
            storage_key,
            expires_minutes=storage_config.upload_timeout_minutes
        )
        
        # Calculate expiration timestamp
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=storage_config.upload_timeout_minutes
        )
        
        # Log upload URL generation
        logger.info(
            f"Generated presigned upload URL for case {case_id}, "
            f"item {item_id}, file {sanitized_filename}, "
            f"size {request_data.file_size} bytes, "
            f"user {current_user.username}, "
            f"expires {expires_at}"
        )
        
        return PresignedUploadResponse(
            item_id=item_id,
            upload_url=upload_url,
            storage_key=storage_key,
            expires_at=expires_at,
            max_file_size=storage_config.max_upload_size_mb * 1024 * 1024
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating upload URL for case {case_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate upload URL: {str(e)}"
        )


@router.patch("/{case_id}/timeline/items/{item_id}/status", response_model=CaseRead)
@handle_human_id()
async def update_attachment_status(
    case_id: int,
    item_id: str,
    update_data: AttachmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """
    Update attachment upload status.
    
    This endpoint:
    1. Verifies the timeline item exists and is an attachment
    2. If status is 'complete', verifies file exists in storage
    3. Updates the upload_status field
    4. Returns the updated case
    """
    try:
        # Get case
        case = await case_service.get_case(db, case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
        # Find timeline item
        timeline_item = None
        for item in case.timeline_items if case.timeline_items else []:
            if item.get("id") == item_id and item.get("type") == "attachment":
                timeline_item = item
                break
        
        if not timeline_item:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment item {item_id} not found"
            )
        
        # Verify user owns the upload (only uploader can update status)
        if timeline_item.get("uploaded_by") != current_user.username:
            raise HTTPException(
                status_code=403,
                detail="Only upload owner can update status"
            )
        
        # Verify state transition is valid
        current_status = timeline_item.get("upload_status", "complete")
        if current_status in ["complete", "failed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {current_status} to {update_data.status}"
            )
        
        # If marking as complete, verify file exists in storage
        if update_data.status == UploadStatus.COMPLETE:
            storage_key = timeline_item.get("storage_key")
            if not storage_key:
                raise HTTPException(
                    status_code=400,
                    detail="Attachment has no storage key"
                )
            
            file_exists = await storage_service.verify_file_exists(storage_key)
            if not file_exists:
                raise HTTPException(
                    status_code=409,
                    detail="File not found in storage"
                )
        
        # Update timeline item
        timeline_item["upload_status"] = update_data.status.value
        if update_data.file_hash:
            timeline_item["file_hash"] = update_data.file_hash
        
        # Convert dict to AttachmentItem model for service
        attachment_item = AttachmentItem(**timeline_item)
        
        # Save updated case
        case = await case_service.update_timeline_item(
            db, case_id, item_id, attachment_item, current_user.username
        )
        
        # Log status update
        logger.info(
            f"Updated attachment status for case {case_id}, "
            f"item {item_id}, status {update_data.status}, "
            f"user {current_user.username}"
        )
        
        return case
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating attachment status for case {case_id}, item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update attachment status: {str(e)}"
        )


@router.get("/{case_id}/timeline/items/{item_id}/download-url", response_model=PresignedDownloadResponse)
@handle_human_id()
async def generate_download_url(
    case_id: int,
    item_id: str,
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
        # Get case
        case = await case_service.get_case(db, case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
        # Find timeline item
        timeline_item = None
        for item in case.timeline_items if case.timeline_items else []:
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
            f"Generated presigned download URL for case {case_id}, "
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
        logger.error(f"Error generating download URL for case {case_id}, item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {str(e)}"
        )


@router.post("/bulk-update", response_model=List[CaseRead])
async def bulk_update_cases(
    case_ids: List[str],
    case_update: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Bulk update multiple cases."""
    try:
        updated_cases = []
        for case_id_str in case_ids:
            # Convert human ID to numeric if needed
            if isinstance(case_id_str, str) and case_id_str.startswith(ID_PREFIX):
                try:
                    case_id = int(case_id_str[len(ID_PREFIX):])
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid case ID format: {case_id_str}")
            else:
                case_id = int(case_id_str)
                
            db_case = await case_service.update_case(db, case_id, case_update, current_user.username)
            if db_case:
                updated_cases.append(db_case)
        return updated_cases
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error bulk updating cases: {str(e)}")
