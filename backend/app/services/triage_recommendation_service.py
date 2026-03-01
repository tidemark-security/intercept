"""Triage recommendation service for AI-assisted alert analysis.

Manages CRUD operations for TriageRecommendation records and handles
the recommendation acceptance/rejection workflow.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.models import (
    TriageRecommendation, Alert, Task, TaskCreate
)
from app.models.enums import (
    RecommendationStatus, TriageDisposition, AlertStatus, Priority, TaskStatus,
    RejectionCategory
)
from app.services.alert_triage_apply_service import (
    apply_triage_state,
    create_case_from_alert,
    mark_alert_escalated,
)
from app.services.timeline_service import timeline_service


CLOSED_ALERT_STATUSES = {
    AlertStatus.CLOSED_TP,
    AlertStatus.CLOSED_BP,
    AlertStatus.CLOSED_FP,
    AlertStatus.CLOSED_UNRESOLVED,
    AlertStatus.CLOSED_DUPLICATE,
}

DISPOSITION_TO_CLOSED_STATUS: Dict[TriageDisposition, AlertStatus] = {
    TriageDisposition.FALSE_POSITIVE: AlertStatus.CLOSED_FP,
    TriageDisposition.BENIGN: AlertStatus.CLOSED_BP,
    TriageDisposition.DUPLICATE: AlertStatus.CLOSED_DUPLICATE,
}


def get_effective_suggested_status(recommendation: TriageRecommendation) -> Optional[AlertStatus]:
    return recommendation.suggested_status or DISPOSITION_TO_CLOSED_STATUS.get(recommendation.disposition)


def _build_state_change_note(
    reviewed_by: str,
    before_status: Optional[AlertStatus],
    after_status: Optional[AlertStatus],
    before_priority: Optional[Priority],
    after_priority: Optional[Priority],
    before_assignee: Optional[str],
    after_assignee: Optional[str],
    before_tags: List[str],
    after_tags: List[str],
    before_case_id: Optional[int],
    after_case_id: Optional[int],
) -> Optional[str]:
    changes: List[str] = []

    if after_status != before_status and after_status is not None:
        changes.append(f"set status to {after_status.value}")

    if after_priority != before_priority and after_priority is not None:
        changes.append(f"set priority to `{after_priority.value}`")

    if after_assignee != before_assignee and after_assignee:
        changes.append(f"set assignee to `{after_assignee}`")

    before_tags_set = set(before_tags)
    after_tags_set = set(after_tags)
    added_tags = sorted(after_tags_set - before_tags_set)
    removed_tags = sorted(before_tags_set - after_tags_set)

    if added_tags:
        changes.append(f"added tags: {', '.join(f'`{tag}`' for tag in added_tags)}")
    if removed_tags:
        changes.append(f"removed tags: {', '.join(f'`{tag}`' for tag in removed_tags)}")

    if after_case_id != before_case_id and after_case_id is not None:
        changes.append(f"linked alert to case CAS-{after_case_id:07d}")

    if not changes:
        return None

    return f"accepted AI recommendation and " + "; ".join(changes) + "."


async def get_by_alert_id(
    db: AsyncSession,
    alert_id: int
) -> Optional[TriageRecommendation]:
    """Get current triage recommendation for an alert.
    
    Args:
        db: Database session
        alert_id: Alert ID
        
    Returns:
        TriageRecommendation if exists, None otherwise
    """
    query = select(TriageRecommendation).where(
        TriageRecommendation.alert_id == alert_id
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_or_replace_recommendation(
    db: AsyncSession,
    alert_id: int,
    data: Dict[str, Any],
    created_by: str
) -> TriageRecommendation:
    """Create or replace triage recommendation for an alert.
    
    Due to unique constraint on alert_id, we update the existing record in-place:
    - If a QUEUED/FAILED recommendation exists: Update it with new data and set to PENDING
    - If no recommendation exists: Create a new one with PENDING status
    
    Args:
        db: Database session
        alert_id: Alert ID
        data: Recommendation data (disposition, confidence, reasoning, etc.)
        created_by: Username of creator (from API key)
        
    Returns:
        TriageRecommendation with PENDING status
        
    Raises:
        HTTPException(404): Alert not found
        HTTPException(400): Invalid data
    """
    # Verify alert exists
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {alert_id} not found"
        )
    
    # Check for existing recommendation
    existing = await get_by_alert_id(db, alert_id)
    if existing:
        # Update the existing recommendation in-place (unique constraint on alert_id)
        existing.disposition = TriageDisposition(data.get("disposition"))
        existing.confidence = float(data.get("confidence", 0.0))
        existing.reasoning_bullets = data.get("reasoning_bullets", [])
        existing.recommended_actions = data.get("recommended_actions", [])
        existing.suggested_status = AlertStatus(data["suggested_status"]) if data.get("suggested_status") else None
        existing.suggested_priority = Priority(data["suggested_priority"]) if data.get("suggested_priority") else None
        existing.suggested_assignee = data.get("suggested_assignee")
        existing.suggested_tags_add = data.get("suggested_tags_add", [])
        existing.suggested_tags_remove = data.get("suggested_tags_remove", [])
        existing.request_escalate_to_case = data.get("request_escalate_to_case", False)
        existing.created_by = created_by
        existing.created_at = datetime.now(timezone.utc)
        existing.status = RecommendationStatus.PENDING
        existing.error_message = None  # Clear any previous error
        existing.reviewed_by = None  # Reset review fields
        existing.reviewed_at = None
        existing.rejection_reason = None
        existing.applied_changes = []
        
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing
    
    # Create new recommendation
    recommendation = TriageRecommendation(
        alert_id=alert_id,
        disposition=TriageDisposition(data.get("disposition")),
        confidence=float(data.get("confidence", 0.0)),
        reasoning_bullets=data.get("reasoning_bullets", []),
        recommended_actions=data.get("recommended_actions", []),
        suggested_status=AlertStatus(data["suggested_status"]) if data.get("suggested_status") else None,
        suggested_priority=Priority(data["suggested_priority"]) if data.get("suggested_priority") else None,
        suggested_assignee=data.get("suggested_assignee"),
        suggested_tags_add=data.get("suggested_tags_add", []),
        suggested_tags_remove=data.get("suggested_tags_remove", []),
        request_escalate_to_case=data.get("request_escalate_to_case", False),
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
        status=RecommendationStatus.PENDING,
    )
    
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)
    
    return recommendation


async def enqueue_triage(
    db: AsyncSession,
    alert_id: int,
    enqueued_by: str = "system"
) -> TriageRecommendation:
    """Create a QUEUED placeholder and enqueue triage task.
    
    If a recommendation already exists:
    - QUEUED/FAILED: Update in-place and re-enqueue
    - PENDING/ACCEPTED/REJECTED/SUPERSEDED: Mark as SUPERSEDED and create new QUEUED
    
    Args:
        db: Database session
        alert_id: Alert ID
        enqueued_by: Username of who triggered the enqueue
        
    Returns:
        TriageRecommendation with QUEUED status
        
    Raises:
        HTTPException(404): Alert not found
        HTTPException(400): AI triage not enabled
    """
    from app.services.settings_service import SettingsService
    from app.services.task_queue_service import get_task_queue_service
    from app.services.tasks import TASK_TRIAGE_ALERT
    
    settings = SettingsService(db)  # type: ignore[arg-type]
    
    # Check if triage is enabled
    flow_id = await settings.get_typed_value("langflow.alert_triage_flow_id")
    if not flow_id:
        raise HTTPException(
            status_code=400,
            detail="AI triage is not enabled. Configure 'langflow.alert_triage_flow_id' in settings."
        )
    
    # Verify alert exists
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {alert_id} not found"
        )
    
    # Check for existing recommendation
    existing = await get_by_alert_id(db, alert_id)
    
    if existing:
        if existing.status in [RecommendationStatus.QUEUED, RecommendationStatus.FAILED]:
            # Update in-place for retry
            existing.status = RecommendationStatus.QUEUED
            existing.error_message = None
            existing.created_by = enqueued_by
            existing.created_at = datetime.now(timezone.utc)
            db.add(existing)
            recommendation = existing
        else:
            # Mark existing as SUPERSEDED
            existing.status = RecommendationStatus.SUPERSEDED
            db.add(existing)
            
            # Create new QUEUED placeholder
            recommendation = TriageRecommendation(
                alert_id=alert_id,
                disposition=TriageDisposition.UNKNOWN,  # Placeholder
                confidence=0.0,
                reasoning_bullets=[],
                recommended_actions=[],
                created_by=enqueued_by,
                created_at=datetime.now(timezone.utc),
                status=RecommendationStatus.QUEUED,
            )
            db.add(recommendation)
    else:
        # Create new QUEUED placeholder
        recommendation = TriageRecommendation(
            alert_id=alert_id,
            disposition=TriageDisposition.UNKNOWN,  # Placeholder
            confidence=0.0,
            reasoning_bullets=[],
            recommended_actions=[],
            created_by=enqueued_by,
            created_at=datetime.now(timezone.utc),
            status=RecommendationStatus.QUEUED,
        )
        db.add(recommendation)
    
    await db.commit()
    await db.refresh(recommendation)
    
    # Enqueue the task
    try:
        task_queue = get_task_queue_service()
        await task_queue.enqueue(
            task_name=TASK_TRIAGE_ALERT,
            payload={"alert_id": alert_id}
        )
    except RuntimeError as e:
        # Task queue not available - mark as failed
        recommendation.status = RecommendationStatus.FAILED
        recommendation.error_message = f"Task queue not available: {str(e)}"
        db.add(recommendation)
        await db.commit()
        await db.refresh(recommendation)
    
    return recommendation


async def auto_reject_if_pending(
    db: AsyncSession,
    alert_id: int,
    reviewed_by: str
) -> Optional[TriageRecommendation]:
    """Auto-reject a pending triage recommendation when alert is manually triaged.
    
    Called when an alert's status is manually changed to a closed or escalated state.
    This ensures the recommendation reflects that manual triage superseded the AI suggestion.
    
    Args:
        db: Database session
        alert_id: Alert ID
        reviewed_by: Username of who performed the manual triage
        
    Returns:
        TriageRecommendation if one was rejected, None if no pending recommendation exists
    """
    recommendation = await get_by_alert_id(db, alert_id)
    if not recommendation or recommendation.status != RecommendationStatus.PENDING:
        return None
    
    recommendation.status = RecommendationStatus.REJECTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = datetime.now(timezone.utc)
    recommendation.rejection_category = RejectionCategory.SUPERSEDED_MANUAL_TRIAGE
    recommendation.rejection_reason = "Alert was manually triaged"
    
    db.add(recommendation)
    # Note: Caller is responsible for commit (usually part of larger transaction)
    
    return recommendation


async def accept_recommendation(
    db: AsyncSession,
    alert_id: int,
    options: Dict[str, Any],
    reviewed_by: str
) -> Dict[str, Any]:
    """Accept triage recommendation and apply changes to alert.
    
    If request_escalate_to_case is true:
    - Creates a new case from the alert
    - Links the alert to the case with ESCALATED status
    - Creates tasks from recommended_actions with case priority
    
    Args:
        db: Database session
        alert_id: Alert ID
        options: Acceptance options (e.g., which patches to apply)
        reviewed_by: Username of reviewer
        
    Returns:
        Dict with:
            - recommendation: TriageRecommendation with ACCEPTED status
            - case_id: Optional[int] - New case ID if escalated
            - tasks_created: int - Number of tasks created
        
    Raises:
        HTTPException(404): Recommendation not found
        HTTPException(409): Recommendation already reviewed
    """
    recommendation = await get_by_alert_id(db, alert_id)
    if not recommendation:
        raise HTTPException(
            status_code=404,
            detail=f"No triage recommendation found for alert {alert_id}"
        )
    
    if recommendation.status != RecommendationStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Recommendation already {recommendation.status.value}"
        )
    
    # Get alert
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    before_status = alert.status
    before_priority = alert.priority
    before_assignee = alert.assignee
    before_tags = list(alert.tags or [])
    before_case_id = alert.case_id
    
    # Track what was applied
    applied_changes = []
    result_case_id = None
    tasks_created = 0
    effective_suggested_status = get_effective_suggested_status(recommendation)
    
    # Apply suggested changes based on options (default: apply all)
    apply_status = options.get("apply_status", True)
    apply_priority = options.get("apply_priority", True)
    apply_tags = options.get("apply_tags", True)
    
    if apply_status and effective_suggested_status:
        alert.status = effective_suggested_status
        applied_changes.append({
            "field": "status",
            "value": effective_suggested_status.value
        })
    
    if apply_priority and recommendation.suggested_priority:
        alert.priority = recommendation.suggested_priority
        applied_changes.append({
            "field": "priority",
            "value": recommendation.suggested_priority.value
        })
    
    if apply_tags:
        # Apply tag changes
        current_tags = set(alert.tags or [])
        
        # Add tags
        for tag in recommendation.suggested_tags_add:
            current_tags.add(tag)
            applied_changes.append({
                "field": "tags",
                "action": "add",
                "value": tag
            })
        
        # Remove tags
        for tag in recommendation.suggested_tags_remove:
            current_tags.discard(tag)
            applied_changes.append({
                "field": "tags",
                "action": "remove",
                "value": tag
            })
        
        alert.tags = list(current_tags)

    apply_triage_state(
        alert,
        triaged_by=reviewed_by,
        set_assignee=True,
    )
    if alert.assignee != before_assignee:
        applied_changes.append({
            "field": "assignee",
            "value": reviewed_by,
        })
    
    accepted_with_closed_status = bool(
        apply_status
        and effective_suggested_status
        and effective_suggested_status in CLOSED_ALERT_STATUSES
    )

    # Accept outcomes must end in either a closed alert state or case-based investigation.
    should_escalate_to_case = recommendation.request_escalate_to_case or not accepted_with_closed_status
    if should_escalate_to_case and not recommendation.request_escalate_to_case:
        applied_changes.append({
            "field": "escalation",
            "action": "forced_case_escalation",
            "reason": "Accepted recommendation requires case-based investigation",
        })

    # Handle escalation to case when requested or when needed to satisfy acceptance outcome invariants.
    if should_escalate_to_case:
        if alert.case_id:
            # Already linked to a case, skip escalation but continue
            result_case_id = alert.case_id
            mark_alert_escalated(
                alert,
                case_id=alert.case_id,
                preserve_existing_linked_at=True,
            )
            applied_changes.append({
                "field": "escalation",
                "action": "skipped",
                "reason": "Alert already linked to case",
                "case_id": alert.case_id,
            })
        else:
            # Create new case from alert directly (not using case_service to avoid nested commits)
            case_priority = recommendation.suggested_priority or alert.priority or Priority.MEDIUM
            new_case = await create_case_from_alert(
                db,
                alert=alert,
                created_by=reviewed_by,
                priority=case_priority,
                assignee=reviewed_by,
            )
            
            # Link alert to case
            mark_alert_escalated(alert, case_id=new_case.id)  # type: ignore[arg-type]
            
            result_case_id = new_case.id
            applied_changes.append({
                "field": "escalation",
                "action": "created_case",
                "case_id": new_case.id
            })
            
            # Create tasks from recommended_actions using TaskCreate for validation
            for action in recommendation.recommended_actions:
                # Extract title and description from action object
                action_title = action.get("title", "") if isinstance(action, dict) else str(action)
                action_description = action.get("description", "") if isinstance(action, dict) else ""
                
                # Truncate title to fit TaskCreate max_length constraint
                task_title = action_title[:197] + "..." if len(action_title) > 200 else action_title
                
                # Build description: use action description if provided, otherwise use default
                if action_description:
                    task_description = f"AI-recommended action from triage of alert ALT-{alert_id:07d}\n\n{action_description}"
                else:
                    task_description = f"AI-recommended action from triage of alert ALT-{alert_id:07d}"
                
                # Use TaskCreate for Pydantic validation
                task_data = TaskCreate(
                    title=task_title,
                    description=task_description,
                    priority=case_priority,
                    case_id=new_case.id,
                    assignee=reviewed_by,
                    status=TaskStatus.TODO,
                )
                
                db_task = Task(
                    **task_data.model_dump(exclude_unset=False),
                    linked_at=datetime.now(timezone.utc),
                    created_by=reviewed_by,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(db_task)
                tasks_created += 1
            
            if tasks_created > 0:
                applied_changes.append({
                    "field": "tasks",
                    "action": "created",
                    "count": tasks_created
                })
    
    # Update recommendation status
    recommendation.status = RecommendationStatus.ACCEPTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = datetime.now(timezone.utc)
    recommendation.applied_changes = applied_changes

    state_change_note = _build_state_change_note(
        reviewed_by=reviewed_by,
        before_status=before_status,
        after_status=alert.status,
        before_priority=before_priority,
        after_priority=alert.priority,
        before_assignee=before_assignee,
        after_assignee=alert.assignee,
        before_tags=before_tags,
        after_tags=list(alert.tags or []),
        before_case_id=before_case_id,
        after_case_id=alert.case_id,
    )
    if state_change_note:
        timeline_service.add_timeline_item(
            alert,
            {
                "type": "note",
                "description": state_change_note,
                "timestamp": datetime.now(timezone.utc),
                "tags": ["triage-recommendation", "state-change"],
                "flagged": False,
                "highlighted": False,
                "replies": [],
            },
            created_by=reviewed_by,
        )
    
    db.add(alert)
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)
    
    return {
        "recommendation": recommendation,
        "case_id": result_case_id,
        "tasks_created": tasks_created
    }


async def reject_recommendation(
    db: AsyncSession,
    alert_id: int,
    category: RejectionCategory,
    reason: Optional[str],
    reviewed_by: str
) -> TriageRecommendation:
    """Reject triage recommendation with category and optional reason.
    
    Args:
        db: Database session
        alert_id: Alert ID
        category: Rejection category
        reason: Optional additional details
        reviewed_by: Username of reviewer
        
    Returns:
        TriageRecommendation with REJECTED status
        
    Raises:
        HTTPException(404): Recommendation not found
        HTTPException(409): Recommendation already reviewed
    """
    recommendation = await get_by_alert_id(db, alert_id)
    if not recommendation:
        raise HTTPException(
            status_code=404,
            detail=f"No triage recommendation found for alert {alert_id}"
        )
    
    if recommendation.status != RecommendationStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Recommendation already {recommendation.status.value}"
        )
    
    recommendation.status = RecommendationStatus.REJECTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = datetime.now(timezone.utc)
    recommendation.rejection_category = category
    recommendation.rejection_reason = reason
    
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)
    
    return recommendation
