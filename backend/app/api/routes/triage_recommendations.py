"""
Triage Recommendation API Routes

API endpoints for managing AI-generated triage recommendations on alerts.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.core.database import get_db
from app.models.models import TriageRecommendationRead, UserAccount
from app.models.enums import RejectionCategory
from app.services import triage_recommendation_service
from app.api.route_utils import create_human_id_decorator
from app.api.routes.admin_auth import require_authenticated_user

logger = logging.getLogger(__name__)

ID_PREFIX = "ALT-"
router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_authenticated_user)]
)

# Human ID decorator configured for alerts
handle_human_id = create_human_id_decorator(ID_PREFIX, "alert_id")


class AcceptRecommendationRequest(BaseModel):
    """Request body for accepting a triage recommendation."""
    apply_status: bool = Field(default=True, description="Apply suggested status change")
    apply_priority: bool = Field(default=True, description="Apply suggested priority change")
    apply_assignee: bool = Field(default=True, description="Apply suggested assignee change")
    apply_tags: bool = Field(default=True, description="Apply suggested tag changes")


class RejectRecommendationRequest(BaseModel):
    """Request body for rejecting a triage recommendation."""
    category: RejectionCategory = Field(..., description="Rejection category (required)")
    reason: Optional[str] = Field(default=None, max_length=500, description="Additional details (optional, required if category is OTHER)")


class AcceptRecommendationResponse(BaseModel):
    """Response from accepting a triage recommendation."""
    recommendation: TriageRecommendationRead
    case_id: Optional[int] = Field(default=None, description="New case ID if escalated")
    case_human_id: Optional[str] = Field(default=None, description="New case human ID if escalated")
    tasks_created: int = Field(default=0, description="Number of tasks created from recommended actions")


@router.get("/{alert_id}/triage-recommendation", response_model=Optional[TriageRecommendationRead])
@handle_human_id()
async def get_triage_recommendation(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Get the current triage recommendation for an alert.
    
    Returns None if no recommendation exists.
    """
    recommendation = await triage_recommendation_service.get_by_alert_id(db, alert_id)
    return recommendation


@router.post("/{alert_id}/triage-recommendation/enqueue", response_model=TriageRecommendationRead)
@handle_human_id()
async def enqueue_triage_recommendation(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Enqueue AI triage for an alert.
    
    Creates a QUEUED placeholder recommendation and submits the triage job to the worker queue.
    If a QUEUED or FAILED recommendation already exists, it will be updated in-place.
    If a PENDING/ACCEPTED/REJECTED/SUPERSEDED recommendation exists, it will be superseded.
    
    Returns 400 if AI triage is not enabled (langflow.alert_triage_flow_id not configured).
    """
    recommendation = await triage_recommendation_service.enqueue_triage(
        db=db,
        alert_id=alert_id,
        enqueued_by=current_user.username
    )
    return recommendation


@router.post("/{alert_id}/triage-recommendation/accept", response_model=AcceptRecommendationResponse)
@handle_human_id()
async def accept_triage_recommendation(
    alert_id: int,
    request: AcceptRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Accept a triage recommendation and apply selected changes.
    
    By default, all suggested changes are applied. Use the request body
    to selectively disable specific changes.
    
    If request_escalate_to_case is true on the recommendation:
    - A new case is created from the alert
    - The alert is linked and set to ESCALATED status
    - Tasks are created from recommended_actions with case priority
    
    Returns the updated recommendation and case info if escalated.
    """
    result = await triage_recommendation_service.accept_recommendation(
        db=db,
        alert_id=alert_id,
        options={
            "apply_status": request.apply_status,
            "apply_priority": request.apply_priority,
            "apply_assignee": request.apply_assignee,
            "apply_tags": request.apply_tags,
        },
        reviewed_by=current_user.username
    )
    
    return AcceptRecommendationResponse(
        recommendation=result["recommendation"],
        case_id=result.get("case_id"),
        case_human_id=f"CAS-{result['case_id']:07d}" if result.get("case_id") else None,
        tasks_created=result.get("tasks_created", 0)
    )


@router.post("/{alert_id}/triage-recommendation/reject", response_model=TriageRecommendationRead)
@handle_human_id()
async def reject_triage_recommendation(
    alert_id: int,
    request: RejectRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user)
):
    """Reject a triage recommendation with a category and optional reason.
    
    The rejection category is required. Additional details are optional
    unless the category is OTHER, in which case a reason should be provided.
    """
    # Validate that OTHER category has a reason
    if request.category == RejectionCategory.OTHER and not request.reason:
        raise HTTPException(
            status_code=400,
            detail="Reason is required when category is OTHER"
        )
    
    recommendation = await triage_recommendation_service.reject_recommendation(
        db=db,
        alert_id=alert_id,
        category=request.category,
        reason=request.reason,
        reviewed_by=current_user.username
    )
    
    return recommendation
