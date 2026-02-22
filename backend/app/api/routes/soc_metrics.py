"""
SOC Metrics API Routes

JSON API for querying SOC operational metrics from materialized views.
Supports three metric types:
- soc: SOC-level summary metrics (MTTT, MTTR, TP/FP rates)
- analyst: Per-analyst performance metrics (admin-only)
- alert: Alert performance/detection engineering metrics
"""
from datetime import datetime, timezone
from typing import Optional, Literal
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    UserAccount,
    SOCMetricsResponse,
    AnalystMetricsResponse,
    AlertMetricsResponse,
    AITriageMetricsResponse,
    AIChatMetricsResponse,
    TriageRecommendationDrillDownResponse,
    ChatFeedbackDrillDownResponse,
)
from app.models.enums import Priority, RejectionCategory, TriageDisposition, RecommendationStatus, MessageFeedback
from app.services.metrics_service import metrics_service
from app.api.routes.admin_auth import require_authenticated_user, require_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
)


MetricType = Literal["soc", "analyst", "alert"]


def parse_datetime(value: Optional[str], param_name: str) -> Optional[datetime]:
    """Parse ISO8601 datetime string with timezone awareness."""
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {param_name} format. Use ISO8601 (e.g., '2025-12-01T00:00:00Z'): {e}"
        )


@router.get(
    "",
    response_model=SOCMetricsResponse | AnalystMetricsResponse | AlertMetricsResponse,
    summary="Get SOC operational metrics",
    description="""
Query SOC operational metrics aggregated in 15-minute windows.

**Metric Types:**
- `soc` - SOC-level summary: MTTT, MTTR, TP/FP/BP rates, case/alert/task counts
- `analyst` - Per-analyst performance: triage volume, outcome mix, timing comparison (ADMIN ONLY)
- `alert` - Alert performance: volume by source, hourly patterns, FP rates by rule

**Time Range:**
- Start and end times are automatically binned to 15-minute boundaries
- Default range is last 7 days if not specified
- Format: ISO8601 with timezone (e.g., '2025-12-01T00:00:00Z')

**Filters:**
- `priority` - Filter by priority level (INFO, LOW, MEDIUM, HIGH, CRITICAL, EXTREME)
- `source` - Filter by alert source (for soc and alert types)
- `analyst` - Filter by analyst username (for analyst type, admin only)
""",
)
async def get_metrics(
    type: MetricType = Query(
        ...,
        description="Metric type: 'soc' for SOC summary, 'analyst' for per-analyst (admin only), 'alert' for detection engineering"
    ),
    start: Optional[str] = Query(
        None,
        description="Period start (ISO8601 with 'Z' suffix, e.g., '2025-12-01T00:00:00Z'). Defaults to 7 days ago."
    ),
    end: Optional[str] = Query(
        None,
        description="Period end (ISO8601 with 'Z' suffix). Defaults to now."
    ),
    priority: Optional[Priority] = Query(
        None,
        description="Filter by priority level"
    ),
    source: Optional[str] = Query(
        None,
        description="Filter by alert source (for type=soc or type=alert)"
    ),
    analyst: Optional[str] = Query(
        None,
        description="Filter by analyst username (for type=analyst, admin only)"
    ),
    group_by: Optional[str] = Query(
        "source",
        description="Dimension to group by for type=alert: 'source', 'title', or 'tag'"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Get SOC operational metrics based on type.
    
    - **soc**: Available to all authenticated users
    - **analyst**: Restricted to admin users only
    - **alert**: Available to all authenticated users
    """
    # Parse datetime parameters
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    # Validate time range
    if start_time and end_time and start_time >= end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be before end"
        )

    try:
        if type == "soc":
            return await metrics_service.get_soc_metrics(
                db=db,
                start_time=start_time,
                end_time=end_time,
                priority=priority,
                source=source,
            )
        
        elif type == "analyst":
            # Analyst metrics require admin role
            if current_user.role.value != "ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Analyst metrics require admin role"
                )
            return await metrics_service.get_analyst_metrics(
                db=db,
                start_time=start_time,
                end_time=end_time,
                analyst=analyst,
            )
        
        elif type == "alert":
            # Validate group_by parameter
            valid_group_by = {"source", "title", "tag"}
            if group_by not in valid_group_by:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid group_by: {group_by}. Must be one of: {', '.join(valid_group_by)}"
                )
            return await metrics_service.get_alert_metrics(
                db=db,
                start_time=start_time,
                end_time=end_time,
                source=source,
                priority=priority,
                group_by=group_by,
            )
        
        else:
            # Should not reach here due to Literal type
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid metric type: {type}. Must be one of: soc, analyst, alert"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching {type} metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching metrics: {str(e)}"
        )


@router.get(
    "/soc",
    response_model=SOCMetricsResponse,
    summary="Get SOC summary metrics",
    description="Shorthand for GET /metrics?type=soc",
)
async def get_soc_metrics(
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    priority: Optional[Priority] = Query(None, description="Filter by priority"),
    source: Optional[str] = Query(None, description="Filter by alert source"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get SOC-level summary metrics."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    return await metrics_service.get_soc_metrics(
        db=db,
        start_time=start_time,
        end_time=end_time,
        priority=priority,
        source=source,
    )


@router.get(
    "/analyst",
    response_model=AnalystMetricsResponse,
    summary="Get analyst performance metrics (admin only)",
    description="Per-analyst performance metrics. Requires admin role.",
    dependencies=[Depends(require_admin_user)],
)
async def get_analyst_metrics(
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    analyst: Optional[str] = Query(None, description="Filter by analyst username"),
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
):
    """Get per-analyst performance metrics (admin only)."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    return await metrics_service.get_analyst_metrics(
        db=db,
        start_time=start_time,
        end_time=end_time,
        analyst=analyst,
    )


@router.get(
    "/alert",
    response_model=AlertMetricsResponse,
    summary="Get alert performance metrics",
    description="Alert performance metrics for detection engineering analysis.",
)
async def get_alert_metrics(
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    source: Optional[str] = Query(None, description="Filter by alert source"),
    priority: Optional[Priority] = Query(None, description="Filter by priority"),
    group_by: str = Query("source", description="Dimension to group by: 'source', 'title', or 'tag'"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get alert performance metrics for detection engineering."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    # Validate group_by parameter
    valid_group_by = {"source", "title", "tag"}
    if group_by not in valid_group_by:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid group_by: {group_by}. Must be one of: {', '.join(valid_group_by)}"
        )
    
    return await metrics_service.get_alert_metrics(
        db=db,
        start_time=start_time,
        end_time=end_time,
        source=source,
        priority=priority,
        group_by=group_by,
    )


@router.get(
    "/ai-triage",
    response_model=AITriageMetricsResponse,
    summary="Get AI triage accuracy metrics",
    description="""
AI triage recommendation accuracy metrics for agent performance monitoring.

Includes:
- Acceptance/rejection rates
- Rejection breakdown by category
- Disposition accuracy
- Confidence correlation with acceptance
- Weekly trending for tracking improvements
""",
)
async def get_ai_triage_metrics(
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get AI triage accuracy metrics."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    return await metrics_service.get_ai_triage_metrics(
        db=db,
        start_time=start_time,
        end_time=end_time,
    )


@router.get(
    "/ai-chat",
    response_model=AIChatMetricsResponse,
    summary="Get AI chat feedback metrics",
    description="""
AI chat assistant feedback metrics for agent performance monitoring.

Includes:
- Positive/negative feedback counts
- Satisfaction rate
- Feedback engagement rate
- Weekly trending for tracking improvements
""",
)
async def get_ai_chat_metrics(
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """Get AI chat feedback metrics."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    return await metrics_service.get_ai_chat_metrics(
        db=db,
        start_time=start_time,
        end_time=end_time,
    )


# ============================================================================
# AI Report Drill-Down Endpoints (Admin-only)
# ============================================================================

@router.get(
    "/ai-triage/recommendations",
    response_model=TriageRecommendationDrillDownResponse,
    summary="Get AI triage recommendations drill-down (admin only)",
    description="""
Drill-down endpoint for AI triage recommendations. Returns individual recommendations
with linked alert information for detailed analysis.

**Admin Only**: This endpoint exposes detailed triage data across all users.

**Filters:**
- `disposition` - Filter by recommended disposition
- `rejection_category` - Filter by rejection category
- `status` - Filter by recommendation status
- `start/end` - Time range for created_at

**Pagination:**
- `limit` - Maximum items to return (default 50, max 200)
- `offset` - Number of items to skip
""",
    dependencies=[Depends(require_admin_user)],
)
async def get_ai_triage_recommendations_drilldown(
    disposition: Optional[TriageDisposition] = Query(None, description="Filter by disposition"),
    rejection_category: Optional[RejectionCategory] = Query(None, description="Filter by rejection category"),
    status: Optional[RecommendationStatus] = Query(None, description="Filter by status"),
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
):
    """Get paginated triage recommendations with alert details (admin only)."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    return await metrics_service.get_triage_recommendations_drilldown(
        db=db,
        start_time=start_time,
        end_time=end_time,
        disposition=disposition,
        rejection_category=rejection_category,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ai-chat/feedback-messages",
    response_model=ChatFeedbackDrillDownResponse,
    summary="Get AI chat feedback messages drill-down (admin only)",
    description="""
Drill-down endpoint for AI chat messages with feedback. Returns individual messages
with session and user information for detailed analysis.

**Admin Only**: This endpoint exposes message content across all users.

**Filters:**
- `feedback` - Filter by feedback type (POSITIVE or NEGATIVE)
- `start/end` - Time range for created_at

**Pagination:**
- `limit` - Maximum items to return (default 50, max 200)
- `offset` - Number of items to skip
""",
    dependencies=[Depends(require_admin_user)],
)
async def get_ai_chat_feedback_drilldown(
    feedback: Optional[MessageFeedback] = Query(None, description="Filter by feedback type"),
    start: Optional[str] = Query(None, description="Period start (ISO8601)"),
    end: Optional[str] = Query(None, description="Period end (ISO8601)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    db: AsyncSession = Depends(get_db),
    admin_user: UserAccount = Depends(require_admin_user),
):
    """Get paginated chat messages with feedback (admin only)."""
    start_time = parse_datetime(start, "start")
    end_time = parse_datetime(end, "end")
    
    return await metrics_service.get_chat_feedback_drilldown(
        db=db,
        start_time=start_time,
        end_time=end_time,
        feedback=feedback,
        limit=limit,
        offset=offset,
    )
