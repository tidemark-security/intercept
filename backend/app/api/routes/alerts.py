"""
Alert API Routes

This module contains the FastAPI routes for alert management.

Note: To get untriaged alerts, use GET /alerts?status=new&sort_by=created_at&sort_order=asc
The dedicated /untriaged endpoint has been removed in favor of the enhanced filtering capabilities.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from fastapi_pagination import Page
import logging
import uuid
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.services.alert_service import alert_service
from app.services.storage_service import storage_service
from app.core.storage_config import storage_config
from app.models.models import (
    AlertCreate, AlertUpdate, AlertTriageRequest,
    AlertRead, AlertReadWithCase, AlertTimelineItem, UserAccount,
    PresignedUploadRequest, PresignedUploadResponse,
    AttachmentStatusUpdate, PresignedDownloadResponse,
    AttachmentItem
)
from app.models.enums import AlertStatus, Priority, UploadStatus
from app.api.route_utils import get_timeline_item_types, create_timeline_converter, create_human_id_decorator
from app.api.routes.admin_auth import require_authenticated_user

logger = logging.getLogger(__name__)

ID_PREFIX = "ALT-"
router = APIRouter(
    prefix="/alerts", 
    tags=["alerts"],
    dependencies=[Depends(require_authenticated_user)]
)

# Dynamically discovered timeline item types and converter
TIMELINE_ITEM_TYPES = get_timeline_item_types(AlertTimelineItem)
convert_timeline_item = create_timeline_converter(TIMELINE_ITEM_TYPES)

# Human ID decorator configured for alerts
handle_human_id = create_human_id_decorator(ID_PREFIX, "alert_id")

@router.post("", response_model=AlertRead)
async def create_alert(
    alert_data: AlertCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new alert."""
    try:
        db_alert = await alert_service.create_alert(db, alert_data)
        return db_alert
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating alert: {str(e)}")


@router.get("", response_model=Page[AlertRead])
async def get_alerts(
    status: Optional[List[AlertStatus]] = Query(None, description="Filter by multiple alert statuses"),
    assignee: Optional[List[str]] = Query(None, description="Filter by multiple assignee usernames"),
    case_id: Optional[int] = None,
    priority: Optional[List[Priority]] = Query(None, description="Filter by multiple priorities"),
    source: Optional[str] = None,
    has_case: Optional[bool] = None,
    start_date: Optional[str] = Query(None, description="Filter alerts created after this UTC datetime (ISO8601 format with 'Z' suffix)"),
    end_date: Optional[str] = Query(None, description="Filter alerts created before this UTC datetime (ISO8601 format with 'Z' suffix)"),
    search: Optional[str] = Query(None, description="Search alerts by ID, title, or description (case-insensitive partial match)"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    db: AsyncSession = Depends(get_db)
):
    """Get alerts with comprehensive filtering and cursor pagination.
    
    Date filtering expects UTC ISO8601 strings with 'Z' suffix (e.g., "2025-10-20T14:30:00Z").
    Alerts are filtered by created_at timestamp.
    Search parameter matches against alert ID, title, or description using case-insensitive partial matching.
    """
    try:
        alerts = await alert_service.get_alerts(
            db=db, 
            status=status,
            assignee=assignee,
            case_id=case_id,
            priority=priority,
            source=source,
            has_case=has_case,
            start_date=start_date,
            end_date=end_date,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )
        return alerts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching alerts: {str(e)}")


@router.get("/{alert_id}", response_model=AlertReadWithCase)
@handle_human_id()
async def get_alert(
    alert_id: int,
    request: Request, # pylint: disable=unused-argument
    include_linked_timelines: bool = Query(
        False,
        description="Include timeline items from linked cases and tasks as nested source_timeline_items"
    ),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific alert with case relationship.
    
    When include_linked_timelines=true, case and task timeline items will include
    a source_timeline_items field containing the timeline from the linked entity.
    """
    try:
        db_alert = await alert_service.get_alert(db, alert_id, include_linked_timelines=include_linked_timelines)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching alert: {str(e)}")


@router.put("/{alert_id}", response_model=AlertRead)
@handle_human_id()
async def update_alert(
    alert_id: int,
    request: Request, # pylint: disable=unused-argument
    alert_update: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Update an alert."""
    try:
        db_alert = await alert_service.update_alert(db, alert_id, alert_update, updated_by=current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating alert: {str(e)}")


@router.post("/{alert_id}/triage", response_model=AlertRead)
@handle_human_id()
async def triage_alert(
    alert_id: int,
    request: Request, # pylint: disable=unused-argument
    triage_request: AlertTriageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Triage an alert and optionally escalate to case."""
    try:
        db_alert = await alert_service.triage_alert(db, alert_id, triage_request, current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triaging alert: {str(e)}")


@router.post("/{alert_id}/link-case/{case_id}", response_model=AlertRead)
@handle_human_id()
async def link_alert_to_case(
    alert_id: int,
    request: Request,  # pylint: disable=unused-argument
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Link an alert to an existing case."""
    try:
        db_alert = await alert_service.link_alert_to_case(db, alert_id, case_id, current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error linking alert to case: {str(e)}")


@router.post("/{alert_id}/unlink-case", response_model=AlertRead)
@handle_human_id()
async def unlink_alert_from_case(
    alert_id: int,
    request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Unlink an alert from its associated case.
    
    This will remove the case association and change the status from ESCALATED back to IN_PROGRESS.
    """
    try:
        db_alert = await alert_service.unlink_alert_from_case(db, alert_id, current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error unlinking alert from case: {str(e)}")


@router.post("/{alert_id}/timeline", response_model=AlertRead)
@handle_human_id()
async def add_timeline_item(
    alert_id: int,
    request: Request, # pylint: disable=unused-argument
    timeline_item: dict,  # Using dict for now since we need to handle different timeline item types
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Add a timeline item to an alert."""
    try:
        typed_item = convert_timeline_item(timeline_item)
        db_alert = await alert_service.add_timeline_item(db, alert_id, typed_item, current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding timeline item: {str(e)}")


@router.put("/{alert_id}/timeline/{item_id}", response_model=AlertRead)
@handle_human_id()
async def update_timeline_item(
    alert_id: int,
    request: Request, # pylint: disable=unused-argument
    item_id: str,
    timeline_item: dict,  # Using dict for now since we need to handle different timeline item types
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Update a specific timeline item in an alert."""
    try:
        typed_item = convert_timeline_item(timeline_item)
        db_alert = await alert_service.update_timeline_item(db, alert_id, item_id, typed_item, current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating timeline item: {str(e)}")


@router.delete("/{alert_id}/timeline/{item_id}", response_model=AlertRead)
@handle_human_id()
async def remove_timeline_item(
    alert_id: int,
    request: Request, # pylint: disable=unused-argument
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Remove a specific timeline item from an alert."""
    try:
        db_alert = await alert_service.remove_timeline_item(db, alert_id, item_id, current_user.username)
        if not db_alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return db_alert
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing timeline item: {str(e)}")


# ---------------------------------------------------------------------------
# File Upload Endpoints
# ---------------------------------------------------------------------------

@router.post("/{alert_id}/timeline/attachments/upload-url", response_model=PresignedUploadResponse)
@handle_human_id()
async def generate_upload_url(
    alert_id: int,
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
        # Verify alert exists and user has access
        alert = await alert_service.get_alert(db, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        
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
            alert_id, item_id, sanitized_filename
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
        
        # Add to alert timeline
        alert = await alert_service.add_timeline_item(
            db, alert_id, attachment_item, current_user.username
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
            f"Generated presigned upload URL for alert {alert_id}, "
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
        logger.error(f"Error generating upload URL for alert {alert_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate upload URL: {str(e)}"
        )


@router.patch("/{alert_id}/timeline/items/{item_id}/status", response_model=AlertRead)
@handle_human_id()
async def update_attachment_status(
    alert_id: int,
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
    4. Returns the updated alert
    """
    try:
        # Get alert
        alert = await alert_service.get_alert(db, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        
        # Find timeline item
        timeline_item = None
        for item in alert.timeline_items if alert.timeline_items else []:
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
        
        # Save updated alert
        alert = await alert_service.update_timeline_item(
            db, alert_id, item_id, attachment_item, current_user.username
        )
        
        # Log status update
        logger.info(
            f"Updated attachment status for alert {alert_id}, "
            f"item {item_id}, status {update_data.status}, "
            f"user {current_user.username}"
        )
        
        return alert
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating attachment status for alert {alert_id}, item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update attachment status: {str(e)}"
        )


@router.get("/{alert_id}/timeline/items/{item_id}/download-url", response_model=PresignedDownloadResponse)
@handle_human_id()
async def generate_download_url(
    alert_id: int,
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
        # Get alert
        alert = await alert_service.get_alert(db, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        
        # Find timeline item
        timeline_item = None
        for item in alert.timeline_items if alert.timeline_items else []:
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
            f"Generated presigned download URL for alert {alert_id}, "
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
        logger.error(f"Error generating download URL for alert {alert_id}, item {item_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {str(e)}"
        )
