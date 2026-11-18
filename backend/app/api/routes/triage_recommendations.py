"""
Triage Recommendation API Routes

API endpoints for managing AI-generated triage recommendations on alerts.
"""
from typing import NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.entity_ids import ALERT_PREFIX, CASE_PREFIX, format_entity_id
from app.models.models import TriageRecommendationRead, UserAccount
from app.models.enums import RejectionCategory
from app.services import triage_recommendation_service
from app.api.route_utils import create_human_id_decorator
from app.api.routes.admin_auth import (
    require_authenticated_user,
    require_non_auditor_user,
)
from app.services.triage_recommendation_service import (
    AcceptRecommendationOptions,
    TriageRecommendationConflictError,
    TriageRecommendationError,
    TriageRecommendationNotFoundError,
)


router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_authenticated_user)],
)

# Human ID decorator configured for alerts
handle_human_id = create_human_id_decorator(ALERT_PREFIX, "alert_id")


def _raise_triage_recommendation_http_error(
    error: TriageRecommendationError,
) -> NoReturn:
    """Translate an expected triage failure at the HTTP seam."""
    if isinstance(error, TriageRecommendationNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, TriageRecommendationConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=str(error)) from error


class AcceptRecommendationRequest(BaseModel):
    """Request body for accepting a triage recommendation."""

    apply_status: bool = Field(
        default=True, description="Apply suggested status change"
    )
    apply_priority: bool = Field(
        default=True, description="Apply suggested priority change"
    )
    apply_assignee: bool = Field(
        default=True, description="Apply suggested assignee change"
    )
    apply_tags: bool = Field(default=True, description="Apply suggested tag changes")
    case_runbook_id: Optional[int] = Field(
        default=None,
        description="Published Case Runbook ID to apply instead of the recommended runbook",
    )
    skip_case_runbook: bool = Field(
        default=False,
        description="Continue escalation without applying the recommended Case Runbook",
    )


class RejectRecommendationRequest(BaseModel):
    """Request body for rejecting a triage recommendation."""

    category: RejectionCategory = Field(
        ..., description="Rejection category (required)"
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Additional details (optional, required if category is OTHER)",
    )


class AcceptRecommendationResponse(BaseModel):
    """Response from accepting a triage recommendation."""

    recommendation: TriageRecommendationRead
    case_id: Optional[int] = Field(default=None, description="New case ID if escalated")
    case_human_id: Optional[str] = Field(
        default=None, description="New case human ID if escalated"
    )
    tasks_created: int = Field(
        default=0, description="Number of tasks created from recommended actions"
    )


@router.get(
    "/{alert_id}/triage-recommendation",
    response_model=Optional[TriageRecommendationRead],
)
@handle_human_id()
async def get_triage_recommendation(
    alert_id: int,
    http_request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    _current_user: UserAccount = Depends(require_authenticated_user),
) -> Optional[TriageRecommendationRead]:
    """Get the current triage recommendation for an alert.

    Returns None if no recommendation exists.
    """
    recommendation = await triage_recommendation_service.get_by_alert_id(db, alert_id)
    return recommendation


@router.post(
    "/{alert_id}/triage-recommendation/enqueue", response_model=TriageRecommendationRead
)
@handle_human_id()
async def enqueue_triage_recommendation(
    alert_id: int,
    http_request: Request,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> TriageRecommendationRead:
    """Enqueue AI triage for an alert.

    Creates a QUEUED placeholder recommendation and submits the triage job to the worker queue.
    If a recommendation already exists, its single per-alert row is reset in-place.

    Returns 400 if AI triage is not enabled (langflow.alert_triage_flow_id not configured).
    """
    try:
        return await triage_recommendation_service.enqueue_triage(
            db=db,
            alert_id=alert_id,
            enqueued_by=current_user.username,
        )
    except TriageRecommendationError as error:
        _raise_triage_recommendation_http_error(error)


@router.post(
    "/{alert_id}/triage-recommendation/accept",
    response_model=AcceptRecommendationResponse,
)
@handle_human_id()
async def accept_triage_recommendation(
    alert_id: int,
    http_request: Request,  # pylint: disable=unused-argument
    payload: AcceptRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> AcceptRecommendationResponse:
    """Accept a triage recommendation and apply selected changes.

    By default, all suggested changes are applied. Use the request body
    to selectively disable specific changes.

    If request_escalate_to_case is true on the recommendation:
    - A new case is created from the alert
    - The alert is linked and set to ESCALATED status
    - Tasks are created from recommended_actions with case priority

    Returns the updated recommendation and case info if escalated.
    """
    try:
        result = await triage_recommendation_service.accept_recommendation(
            db=db,
            alert_id=alert_id,
            options=AcceptRecommendationOptions(
                apply_status=payload.apply_status,
                apply_priority=payload.apply_priority,
                apply_assignee=payload.apply_assignee,
                apply_tags=payload.apply_tags,
                case_runbook_id=payload.case_runbook_id,
                skip_case_runbook=payload.skip_case_runbook,
            ),
            reviewed_by=current_user.username,
        )
    except TriageRecommendationError as error:
        _raise_triage_recommendation_http_error(error)

    return AcceptRecommendationResponse(
        recommendation=result.recommendation,
        case_id=result.case_id,
        case_human_id=(
            format_entity_id(result.case_id, CASE_PREFIX)
            if result.case_id
            else None
        ),
        tasks_created=result.tasks_created,
    )


@router.post(
    "/{alert_id}/triage-recommendation/reject", response_model=TriageRecommendationRead
)
@handle_human_id()
async def reject_triage_recommendation(
    alert_id: int,
    http_request: Request,  # pylint: disable=unused-argument
    payload: RejectRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_non_auditor_user),
) -> TriageRecommendationRead:
    """Reject a triage recommendation with a category and optional reason.

    The rejection category is required. Additional details are optional
    unless the category is OTHER, in which case a reason should be provided.
    """
    try:
        return await triage_recommendation_service.reject_recommendation(
            db=db,
            alert_id=alert_id,
            category=payload.category,
            reason=payload.reason,
            reviewed_by=current_user.username,
        )
    except TriageRecommendationError as error:
        _raise_triage_recommendation_http_error(error)
