from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional
from fastapi_pagination import Page
import logging

from app.core.database import get_db
from app.services.case_service import case_service
from app.models.models import (
    CaseCreate, CaseUpdate, CaseRead, 
    CaseReadWithAlerts, CaseTimelineItem, UserAccount,
    PresignedUploadRequest, PresignedUploadResponse,
    AttachmentStatusUpdate, PresignedDownloadResponse,
)
from app.models.enums import CaseStatus
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
    current_user: UserAccount = Depends(require_non_auditor_user)
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
    current_user: UserAccount = Depends(require_non_auditor_user)
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
    current_user: UserAccount = Depends(require_non_auditor_user)
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
    current_user: UserAccount = Depends(require_non_auditor_user)
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
    current_user: UserAccount = Depends(require_non_auditor_user)
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
    current_user: UserAccount = Depends(require_non_auditor_user)
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
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Generate presigned upload URL and create timeline attachment item."""
    case = await case_service.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return await handle_generate_upload_url(
        entity_type="case", parent_id=case_id, request_data=request_data,
        current_user=current_user, db=db, service=case_service,
    )


@router.patch("/{case_id}/timeline/items/{item_id}/status", response_model=CaseRead)
@handle_human_id()
async def update_attachment_status(
    case_id: int,
    item_id: str,
    update_data: AttachmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user)
):
    """Update attachment upload status."""
    case = await case_service.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return await handle_update_attachment_status(
        entity=case, entity_type="case", parent_id=case_id,
        item_id=item_id, update_data=update_data,
        current_user=current_user, db=db, service=case_service,
    )


@router.get("/{case_id}/timeline/items/{item_id}/download-url", response_model=PresignedDownloadResponse)
@handle_human_id()
async def generate_download_url(
    case_id: int,
    item_id: str,
    download: bool = Query(False, description="Generate a forced-download URL"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Generate presigned download URL for an attachment."""
    case = await case_service.get_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return await handle_generate_download_url(
        entity=case, entity_type="case", parent_id=case_id,
        item_id=item_id, as_download=download, current_user=current_user,
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
