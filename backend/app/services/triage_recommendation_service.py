"""Triage recommendation service for AI-assisted alert analysis.

Manages CRUD operations for TriageRecommendation records and handles
the recommendation acceptance/rejection workflow.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
import math
from typing import Any, Dict, List, Optional, TypeVar

import asyncpg
from pgqueuer.errors import DuplicateJobError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.entity_ids import ALERT_PREFIX, CASE_PREFIX, format_entity_id
from app.models.models import (
    TriageRecommendation,
    TriageRecommendationRead,
    Alert,
    CaseRunbook,
    Task,
    TaskCreate,
)
from app.models.enums import (
    AlertStatus,
    CaseRunbookStatus,
    Priority,
    RealtimeEventType,
    RecommendationStatus,
    RejectionCategory,
    TaskStatus,
    TriageDisposition,
)
from app.services.alert_triage_apply_service import (
    CLOSED_ALERT_STATUSES,
    apply_triage_state,
    create_case_from_alert,
    mark_alert_escalated,
)
from app.services.case_runbook_service import case_runbook_service
from app.services.committed_response import reset_post_commit_session
from app.services.realtime_service import emit_event
from app.services.tag_filter_utils import (
    merge_persisted_tags,
    normalize_persisted_tags,
    persisted_tag_delta,
)
from app.services.timeline_service import timeline_service


logger = logging.getLogger(__name__)


class TriageRecommendationError(ValueError):
    """Base class for expected triage recommendation rejections."""


class TriageRecommendationValidationError(TriageRecommendationError):
    """Raised when recommendation input violates the triage contract."""


class TriageRecommendationNotFoundError(TriageRecommendationError):
    """Raised when a requested alert or recommendation does not exist."""


class TriageRecommendationConflictError(TriageRecommendationError):
    """Raised when current state prevents a recommendation operation."""


DISPOSITION_TO_CLOSED_STATUS: Dict[TriageDisposition, AlertStatus] = {
    TriageDisposition.FALSE_POSITIVE: AlertStatus.CLOSED_FP,
    TriageDisposition.BENIGN: AlertStatus.CLOSED_BP,
    TriageDisposition.DUPLICATE: AlertStatus.CLOSED_DUPLICATE,
}

ESCALATING_TRIAGE_DISPOSITIONS = {
    TriageDisposition.TRUE_POSITIVE,
    TriageDisposition.NEEDS_INVESTIGATION,
    TriageDisposition.UNKNOWN,
}

DISPOSITION_TO_CANONICAL_STATUS: Dict[TriageDisposition, AlertStatus] = {
    TriageDisposition.TRUE_POSITIVE: AlertStatus.ESCALATED,
    TriageDisposition.FALSE_POSITIVE: AlertStatus.CLOSED_FP,
    TriageDisposition.BENIGN: AlertStatus.CLOSED_BP,
    TriageDisposition.NEEDS_INVESTIGATION: AlertStatus.ESCALATED,
    TriageDisposition.DUPLICATE: AlertStatus.CLOSED_DUPLICATE,
    TriageDisposition.UNKNOWN: AlertStatus.ESCALATED,
}


EnumT = TypeVar("EnumT", bound=Enum)


def _parse_enum(value: Any, enum_type: type[EnumT], field_name: str) -> EnumT:
    raw_value = value.value if isinstance(value, Enum) else value
    try:
        return enum_type(raw_value)
    except (TypeError, ValueError) as exc:
        raise TriageRecommendationValidationError(
            f"Invalid {field_name}: {raw_value}"
        ) from exc


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise TriageRecommendationValidationError(
            f"Invalid confidence: {value}"
        ) from exc
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise TriageRecommendationValidationError(f"Invalid confidence: {value}")
    return confidence


@dataclass(frozen=True)
class _AlertState:
    status: Optional[AlertStatus]
    priority: Optional[Priority]
    assignee: Optional[str]
    tags: List[str]
    case_id: Optional[int]


@dataclass(frozen=True)
class AcceptRecommendationResult:
    """Committed result of accepting a triage recommendation."""

    recommendation: TriageRecommendationRead
    case_id: Optional[int]
    tasks_created: int


@dataclass(frozen=True)
class AcceptRecommendationOptions:
    """Analyst-selected patches to apply while accepting a recommendation."""

    apply_status: bool = True
    apply_priority: bool = True
    apply_assignee: bool = True
    apply_tags: bool = True
    case_runbook_id: Optional[int] = None
    skip_case_runbook: bool = False

    def __post_init__(self) -> None:
        if self.case_runbook_id is not None and self.skip_case_runbook:
            raise TriageRecommendationValidationError(
                "case_runbook_id and skip_case_runbook are mutually exclusive"
            )


def _snapshot_alert(alert: Alert) -> _AlertState:
    return _AlertState(
        status=alert.status,
        priority=alert.priority,
        assignee=alert.assignee,
        tags=list(alert.tags or []),
        case_id=alert.case_id,
    )


def _parse_triage_disposition(value: Any) -> TriageDisposition:
    return _parse_enum(value, TriageDisposition, "disposition")


def _validate_suggested_status(value: Any) -> None:
    if value is None:
        return
    _parse_enum(value, AlertStatus, "suggested_status")


def normalize_recommendation_contract(data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply canonical disposition-derived case path and status rules."""
    normalized = dict(data)
    disposition = _parse_triage_disposition(data.get("disposition"))
    _validate_suggested_status(data.get("suggested_status"))
    suggested_priority = data.get("suggested_priority")
    if suggested_priority is not None:
        normalized["suggested_priority"] = _parse_enum(
            suggested_priority,
            Priority,
            "suggested_priority",
        ).value
    normalized["confidence"] = _normalize_confidence(data.get("confidence", 0.0))

    should_escalate = disposition in ESCALATING_TRIAGE_DISPOSITIONS
    recommended_actions = normalized.get("recommended_actions") or []
    recommended_case_runbook_id = normalized.get("recommended_case_runbook_id")

    if recommended_actions and recommended_case_runbook_id is not None:
        raise TriageRecommendationValidationError(
            "recommended_case_runbook_id and recommended_actions are mutually exclusive"
        )
    if (recommended_actions or recommended_case_runbook_id is not None) and not should_escalate:
        raise TriageRecommendationValidationError(
            "Dismissal recommendations cannot include work recommendations"
        )

    normalized["disposition"] = disposition.value
    normalized["request_escalate_to_case"] = should_escalate
    normalized["suggested_status"] = DISPOSITION_TO_CANONICAL_STATUS[disposition].value
    return normalized


def get_effective_suggested_status(
    recommendation: TriageRecommendation,
) -> Optional[AlertStatus]:
    return recommendation.suggested_status or DISPOSITION_TO_CLOSED_STATUS.get(
        recommendation.disposition
    )


def _reset_for_enqueue(
    recommendation: TriageRecommendation,
    *,
    enqueued_by: str,
    queued_at: datetime,
) -> None:
    """Reset a recommendation row to the canonical queued placeholder state."""
    recommendation.disposition = TriageDisposition.UNKNOWN
    recommendation.confidence = 0.0
    recommendation.reasoning_bullets = []
    recommendation.recommended_actions = []
    recommendation.recommended_case_runbook_id = None
    recommendation.suggested_status = None
    recommendation.suggested_priority = None
    recommendation.suggested_assignee = None
    recommendation.suggested_tags_add = []
    recommendation.suggested_tags_remove = []
    recommendation.request_escalate_to_case = False
    recommendation.applied_context_entries = []
    recommendation.created_by = enqueued_by
    recommendation.created_at = queued_at
    recommendation.status = RecommendationStatus.QUEUED
    recommendation.reviewed_by = None
    recommendation.reviewed_at = None
    recommendation.rejection_category = None
    recommendation.rejection_reason = None
    recommendation.applied_changes = []
    recommendation.error_message = None


def _pending_recommendation_values(
    data: Dict[str, Any],
    *,
    created_by: str,
    created_at: datetime,
    default_context_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the canonical mutable state for a newly pending recommendation."""
    return {
        "disposition": TriageDisposition(data["disposition"]),
        "confidence": data["confidence"],
        "reasoning_bullets": data.get("reasoning_bullets", []),
        "recommended_actions": data.get("recommended_actions", []),
        "recommended_case_runbook_id": data.get("recommended_case_runbook_id"),
        "suggested_status": AlertStatus(data["suggested_status"]),
        "suggested_priority": (
            Priority(data["suggested_priority"])
            if data.get("suggested_priority")
            else None
        ),
        "suggested_assignee": data.get("suggested_assignee"),
        "suggested_tags_add": normalize_persisted_tags(
            data.get("suggested_tags_add", [])
        ),
        "suggested_tags_remove": normalize_persisted_tags(
            data.get("suggested_tags_remove", [])
        ),
        "request_escalate_to_case": data.get("request_escalate_to_case", False),
        "applied_context_entries": data.get(
            "applied_context_entries",
            default_context_entries,
        ),
        "created_by": created_by,
        "created_at": created_at,
        "status": RecommendationStatus.PENDING,
        "reviewed_by": None,
        "reviewed_at": None,
        "rejection_category": None,
        "rejection_reason": None,
        "applied_changes": [],
        "error_message": None,
    }


async def _lock_alert(db: AsyncSession, alert_id: int) -> Optional[Alert]:
    result = await db.execute(
        select(Alert)
        .where(Alert.id == alert_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _lock_acceptance_state(
    db: AsyncSession,
    alert_id: int,
) -> tuple[Alert, TriageRecommendation]:
    """Lock mutable acceptance state in the shared Alert-then-child order."""
    if await get_by_alert_id(db, alert_id) is None:
        raise TriageRecommendationNotFoundError(
            f"No triage recommendation found for alert {alert_id}"
        )

    alert = await _lock_alert(db, alert_id)
    if alert is None:
        raise TriageRecommendationNotFoundError(f"Alert {alert_id} not found")

    recommendation = await get_by_alert_id(db, alert_id, for_update=True)
    if recommendation is None:
        raise TriageRecommendationNotFoundError(
            f"No triage recommendation found for alert {alert_id}"
        )
    return alert, recommendation


def _build_state_change_note(
    before: _AlertState,
    alert: Alert,
) -> Optional[str]:
    changes: List[str] = []

    if alert.status != before.status and alert.status is not None:
        changes.append(f"set status to {alert.status.value}")

    if alert.priority != before.priority and alert.priority is not None:
        changes.append(f"set priority to `{alert.priority.value}`")

    if alert.assignee != before.assignee and alert.assignee:
        changes.append(f"set assignee to `{alert.assignee}`")

    added_tags, removed_tags = persisted_tag_delta(before.tags, alert.tags)

    if added_tags:
        changes.append(f"added tags: {', '.join(f'`{tag}`' for tag in added_tags)}")
    if removed_tags:
        changes.append(f"removed tags: {', '.join(f'`{tag}`' for tag in removed_tags)}")

    if alert.case_id != before.case_id and alert.case_id is not None:
        changes.append(
            f"linked alert to case {format_entity_id(alert.case_id, CASE_PREFIX)}"
        )

    if not changes:
        return None

    return "accepted AI recommendation and " + "; ".join(changes) + "."


async def get_by_alert_id(
    db: AsyncSession,
    alert_id: int,
    *,
    for_update: bool = False,
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
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_or_replace_recommendation(
    db: AsyncSession,
    alert_id: int,
    data: Dict[str, Any],
    created_by: str,
) -> TriageRecommendationRead:
    """Create or replace triage recommendation for an alert.

    Due to unique constraint on alert_id, we update the existing record in-place:
    - If a recommendation exists: Replace its data and set it to PENDING
    - If no recommendation exists: Create a new one with PENDING status

    Args:
        db: Database session
        alert_id: Alert ID
        data: Recommendation data (disposition, confidence, reasoning, etc.)
        created_by: Username of creator (from API key)

    Returns:
        TriageRecommendation with PENDING status

    Raises:
        TriageRecommendationNotFoundError: Alert not found
        TriageRecommendationValidationError: Invalid recommendation data
    """
    alert = await _lock_alert(db, alert_id)
    if alert is None:
        raise TriageRecommendationNotFoundError(f"Alert {alert_id} not found")
    data = normalize_recommendation_contract(data)
    created_at = datetime.now(timezone.utc)

    existing = await get_by_alert_id(db, alert_id, for_update=True)
    if existing is not None:
        recommendation = existing
        values = _pending_recommendation_values(
            data,
            created_by=created_by,
            created_at=created_at,
            default_context_entries=existing.applied_context_entries or [],
        )
        for field, value in values.items():
            setattr(recommendation, field, value)
    else:
        values = _pending_recommendation_values(
            data,
            created_by=created_by,
            created_at=created_at,
            default_context_entries=[],
        )
        recommendation = TriageRecommendation(alert_id=alert_id, **values)

    db.add(recommendation)
    if existing is None:
        await db.flush()
    await emit_event(
        db,
        entity_type="alert",
        entity_id=alert_id,
        event_type=RealtimeEventType.TRIAGE_COMPLETED,
        performed_by=created_by,
    )
    response = TriageRecommendationRead.model_validate(recommendation)
    await db.commit()
    return response


async def _compensate_failed_enqueue(
    db: AsyncSession,
    *,
    alert_id: int,
    queued_at: datetime,
    queued_response: TriageRecommendationRead,
) -> TriageRecommendationRead:
    """Mark this enqueue generation failed without overwriting a newer one."""
    try:
        current = await get_by_alert_id(db, alert_id, for_update=True)
    except Exception:
        # The QUEUED row is already durable. Recovery is deliberately
        # best-effort so a recovery defect cannot report that commit as undone.
        await reset_post_commit_session(db, logger)
        logger.exception(
            "Triage enqueue was persisted for alert %s, but queue failure "
            "compensation could not load the current recommendation",
            alert_id,
        )
        return queued_response

    if (
        current is not None
        and current.status == RecommendationStatus.QUEUED
        and current.created_at == queued_at
    ):
        current.status = RecommendationStatus.FAILED
        current.error_message = "Task queue unavailable"
        failed_response = TriageRecommendationRead.model_validate(current)
        try:
            await db.commit()
        except Exception:
            # Preserve the truthful committed QUEUED snapshot if the optional
            # FAILED-state compensation cannot itself be committed.
            await reset_post_commit_session(db, logger)
            logger.exception(
                "Triage enqueue was persisted for alert %s, but queue "
                "failure compensation could not be committed",
                alert_id,
            )
            return queued_response
        return failed_response

    current_response = (
        TriageRecommendationRead.model_validate(current)
        if current is not None
        else queued_response
    )
    await reset_post_commit_session(db, logger)
    return current_response


async def enqueue_triage(
    db: AsyncSession,
    alert_id: int,
    enqueued_by: str = "system"
) -> TriageRecommendationRead:
    """Create a QUEUED placeholder and enqueue triage task.

    If a recommendation already exists, reset it in-place and re-enqueue it. The
    database enforces one recommendation row per alert.

    Args:
        db: Database session
        alert_id: Alert ID
        enqueued_by: Username of who triggered the enqueue

    Returns:
        TriageRecommendation with QUEUED status

    Raises:
        TriageRecommendationNotFoundError: Alert not found
        TriageRecommendationValidationError: AI triage is not enabled
    """
    from app.services.settings_service import SettingsService
    from app.services.task_queue_service import (
        TaskQueueNotInitializedError,
        get_task_queue_service,
    )
    from app.services.tasks import TASK_TRIAGE_ALERT

    settings = SettingsService(db)  # type: ignore[arg-type]

    # Check if triage is enabled
    flow_id = await settings.get("langflow.alert_triage_flow_id")
    if not flow_id:
        raise TriageRecommendationValidationError(
            "AI triage is not enabled. Configure "
            "'langflow.alert_triage_flow_id' in settings."
        )

    # Lock the owning alert so every recommendation writer serializes on one row.
    alert = await _lock_alert(db, alert_id)
    if not alert:
        raise TriageRecommendationNotFoundError(f"Alert {alert_id} not found")

    # Check for existing recommendation
    existing = await get_by_alert_id(db, alert_id, for_update=True)
    queued_at = datetime.now(timezone.utc)

    if existing:
        recommendation = existing
    else:
        recommendation = TriageRecommendation(
            alert_id=alert_id,
            disposition=TriageDisposition.UNKNOWN,
            confidence=0.0,
            reasoning_bullets=[],
            recommended_actions=[],
            created_by=enqueued_by,
            created_at=queued_at,
            status=RecommendationStatus.QUEUED,
        )
    _reset_for_enqueue(
        recommendation,
        enqueued_by=enqueued_by,
        queued_at=queued_at,
    )
    db.add(recommendation)
    await db.flush()
    queued_response = TriageRecommendationRead.model_validate(recommendation)
    await db.commit()

    # Enqueue the task
    try:
        task_queue = get_task_queue_service()
        await task_queue.enqueue(
            task_name=TASK_TRIAGE_ALERT,
            payload={"alert_id": alert_id},
            dedupe_key=f"triage_alert:{alert_id}",
        )
    except (
        TaskQueueNotInitializedError,
        ConnectionError,
        TimeoutError,
        OSError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
        DuplicateJobError,
    ):
        return await _compensate_failed_enqueue(
            db,
            alert_id=alert_id,
            queued_at=queued_at,
            queued_response=queued_response,
        )

    return queued_response


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
    recommendation = await get_by_alert_id(db, alert_id, for_update=True)
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


async def _resolve_acceptance_runbook(
    db: AsyncSession,
    recommendation: TriageRecommendation,
    options: AcceptRecommendationOptions,
    applied_changes: List[Dict[str, Any]],
) -> Optional[CaseRunbook]:
    """Validate the analyst's runbook choice and record any override."""
    requested_runbook_id = options.case_runbook_id
    skip_case_runbook = options.skip_case_runbook
    if (
        requested_runbook_id is not None or skip_case_runbook
    ) and not recommendation.request_escalate_to_case:
        raise TriageRecommendationValidationError(
            "Case Runbook overrides require an escalating recommendation"
        )

    effective_runbook_id = (
        requested_runbook_id
        if requested_runbook_id is not None
        else recommendation.recommended_case_runbook_id
    )
    if effective_runbook_id is not None and not skip_case_runbook:
        runbook = await db.get(CaseRunbook, effective_runbook_id)
        if runbook is None or runbook.status != CaseRunbookStatus.PUBLISHED:
            subject = "selected" if requested_runbook_id is not None else "recommended"
            raise TriageRecommendationConflictError(
                f"The {subject} Case Runbook is no longer published. "
                "Choose another published runbook or continue without a runbook."
            )
        if (
            requested_runbook_id is not None
            and requested_runbook_id != recommendation.recommended_case_runbook_id
        ):
            applied_changes.append({
                "field": "case_runbook",
                "action": "replaced_recommended_runbook",
                "runbook_id": requested_runbook_id,
            })
        return runbook

    if skip_case_runbook and recommendation.recommended_case_runbook_id is not None:
        applied_changes.append({
            "field": "case_runbook",
            "action": "skipped",
            "reason": (
                "Analyst continued without the unavailable recommended Case Runbook"
            ),
            "runbook_id": recommendation.recommended_case_runbook_id,
        })
    return None


def _apply_recommendation_to_alert(
    alert: Alert,
    recommendation: TriageRecommendation,
    options: AcceptRecommendationOptions,
    *,
    reviewed_by: str,
    accepted_at: datetime,
    before: _AlertState,
    applied_changes: List[Dict[str, Any]],
) -> bool:
    """Apply selected alert patches and return whether a case is required."""
    effective_status = get_effective_suggested_status(recommendation)
    apply_status = options.apply_status

    if apply_status and effective_status and alert.status != effective_status:
        alert.status = effective_status
        applied_changes.append({"field": "status", "value": effective_status.value})

    if (
        options.apply_priority
        and recommendation.suggested_priority
        and alert.priority != recommendation.suggested_priority
    ):
        alert.priority = recommendation.suggested_priority
        applied_changes.append({
            "field": "priority",
            "value": recommendation.suggested_priority.value,
        })

    if options.apply_tags:
        before_tags = normalize_persisted_tags(alert.tags)
        add_tags = normalize_persisted_tags(recommendation.suggested_tags_add)
        remove_tags = normalize_persisted_tags(recommendation.suggested_tags_remove)
        current_tags = merge_persisted_tags(before_tags, add_tags)
        remove_tag_keys = {tag.lower() for tag in remove_tags}
        after_tags = [
            tag for tag in current_tags if tag.lower() not in remove_tag_keys
        ]
        added_tags, removed_tags = persisted_tag_delta(before_tags, after_tags)
        applied_changes.extend(
            {"field": "tags", "action": "add", "value": tag}
            for tag in added_tags
        )
        applied_changes.extend(
            {"field": "tags", "action": "remove", "value": tag}
            for tag in removed_tags
        )
        alert.tags = after_tags

    apply_triage_state(
        alert,
        triaged_by=reviewed_by,
        set_assignee=options.apply_assignee,
        now=accepted_at,
    )
    if options.apply_assignee and recommendation.suggested_assignee:
        alert.assignee = recommendation.suggested_assignee
    if alert.assignee != before.assignee:
        applied_changes.append({"field": "assignee", "value": alert.assignee})

    accepted_with_closed_status = bool(
        apply_status
        and effective_status
        and effective_status in CLOSED_ALERT_STATUSES
    )
    should_escalate = (
        recommendation.request_escalate_to_case or not accepted_with_closed_status
    )
    if should_escalate and not recommendation.request_escalate_to_case:
        applied_changes.append({
            "field": "escalation",
            "action": "forced_case_escalation",
            "reason": "Accepted recommendation requires case-based investigation",
        })
    return should_escalate


def _create_recommended_action_tasks(
    db: AsyncSession,
    recommendation: TriageRecommendation,
    *,
    case_id: int,
    case_priority: Priority,
    alert_id: int,
    reviewed_by: str,
    accepted_at: datetime,
) -> int:
    """Stage validated tasks for a newly created investigation case."""
    alert_human_id = format_entity_id(alert_id, ALERT_PREFIX)
    created_count = 0
    for action in recommendation.recommended_actions:
        action_title = action.get("title", "") if isinstance(action, dict) else str(action)
        action_description = (
            action.get("description", "") if isinstance(action, dict) else ""
        )
        task_title = action_title[:197] + "..." if len(action_title) > 200 else action_title
        task_description = f"AI-recommended action from triage of alert {alert_human_id}"
        if action_description:
            task_description = f"{task_description}\n\n{action_description}"

        task_data = TaskCreate(
            title=task_title,
            description=task_description,
            priority=case_priority,
            case_id=case_id,
            assignee=reviewed_by,
            status=TaskStatus.TODO,
        )
        db.add(Task(
            **task_data.model_dump(exclude_unset=False, exclude={"created_at"}),
            linked_at=accepted_at,
            created_by=reviewed_by,
            created_at=accepted_at,
            updated_at=accepted_at,
        ))
        created_count += 1
    return created_count


async def _apply_case_escalation(
    db: AsyncSession,
    alert: Alert,
    recommendation: TriageRecommendation,
    runbook: Optional[CaseRunbook],
    *,
    alert_id: int,
    reviewed_by: str,
    accepted_at: datetime,
    applied_changes: List[Dict[str, Any]],
) -> tuple[Optional[int], int]:
    """Stage the complete case-based investigation outcome."""
    new_case = None
    case_priority = recommendation.suggested_priority or alert.priority or Priority.MEDIUM
    if alert.case_id:
        result_case_id = alert.case_id
        mark_alert_escalated(
            alert,
            case_id=alert.case_id,
            now=accepted_at,
            preserve_existing_linked_at=True,
        )
        applied_changes.append({
            "field": "escalation",
            "action": "skipped",
            "reason": "Alert already linked to case",
            "case_id": alert.case_id,
        })
    else:
        new_case = await create_case_from_alert(
            db,
            alert=alert,
            created_by=reviewed_by,
            priority=case_priority,
            assignee=reviewed_by,
            now=accepted_at,
        )
        mark_alert_escalated(
            alert,
            case_id=new_case.id,  # type: ignore[arg-type]
            now=accepted_at,
        )
        result_case_id = new_case.id
        applied_changes.append({
            "field": "escalation",
            "action": "created_case",
            "case_id": new_case.id,
        })

    tasks_created = 0
    if runbook is not None and result_case_id is not None:
        apply_response = await case_runbook_service.apply_runbook(
            db,
            case_id=result_case_id,
            runbook_id=runbook.id,  # type: ignore[arg-type]
            overrides=[],
            user=reviewed_by,
            commit=False,
        )
        tasks_created = len(apply_response.created_task_ids)
        applied_changes.append({
            "field": "case_runbook",
            "action": "applied",
            "runbook_id": runbook.id,
            "created_task_ids": apply_response.created_task_ids,
        })

    if new_case is not None:
        if runbook is None:
            tasks_created += _create_recommended_action_tasks(
                db,
                recommendation,
                case_id=new_case.id,  # type: ignore[arg-type]
                case_priority=case_priority,
                alert_id=alert_id,
                reviewed_by=reviewed_by,
                accepted_at=accepted_at,
            )
        if tasks_created > 0:
            applied_changes.append({
                "field": "tasks",
                "action": "created",
                "count": tasks_created,
            })

    return result_case_id, tasks_created


async def accept_recommendation(
    db: AsyncSession,
    alert_id: int,
    options: AcceptRecommendationOptions,
    reviewed_by: str,
) -> AcceptRecommendationResult:
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

    Raises:
        TriageRecommendationNotFoundError: Recommendation or alert not found
        TriageRecommendationConflictError: Recommendation is already reviewed
        TriageRecommendationValidationError: Acceptance options are invalid
    """
    alert, recommendation = await _lock_acceptance_state(db, alert_id)
    if recommendation.status != RecommendationStatus.PENDING:
        raise TriageRecommendationConflictError(
            f"Recommendation already {recommendation.status.value}"
        )

    before = _snapshot_alert(alert)
    applied_changes: List[Dict[str, Any]] = []
    recommended_runbook = await _resolve_acceptance_runbook(
        db,
        recommendation,
        options,
        applied_changes,
    )
    accepted_at = datetime.now(timezone.utc)
    should_escalate_to_case = _apply_recommendation_to_alert(
        alert,
        recommendation,
        options,
        reviewed_by=reviewed_by,
        accepted_at=accepted_at,
        before=before,
        applied_changes=applied_changes,
    )

    result_case_id = None
    tasks_created = 0
    if should_escalate_to_case:
        result_case_id, tasks_created = await _apply_case_escalation(
            db,
            alert,
            recommendation,
            recommended_runbook,
            alert_id=alert_id,
            reviewed_by=reviewed_by,
            accepted_at=accepted_at,
            applied_changes=applied_changes,
        )

    # Update recommendation status
    recommendation.status = RecommendationStatus.ACCEPTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = accepted_at
    recommendation.applied_changes = applied_changes

    state_change_note = _build_state_change_note(before, alert)
    if state_change_note:
        timeline_service.add_timeline_item(
            alert,
            timeline_service.build_note_item(
                description=state_change_note,
                created_by=reviewed_by,
                timestamp=accepted_at,
                tags=["triage-recommendation", "state-change"],
            ),
            created_by=reviewed_by,
        )

    db.add(alert)
    db.add(recommendation)
    await emit_event(
        db,
        entity_type="alert",
        entity_id=alert_id,
        event_type=RealtimeEventType.TRIAGE_COMPLETED,
        performed_by=reviewed_by,
    )
    recommendation_response = TriageRecommendationRead.model_validate(recommendation)
    await db.commit()

    return AcceptRecommendationResult(
        recommendation=recommendation_response,
        case_id=result_case_id,
        tasks_created=tasks_created,
    )


async def reject_recommendation(
    db: AsyncSession,
    alert_id: int,
    category: RejectionCategory,
    reason: Optional[str],
    reviewed_by: str
) -> TriageRecommendationRead:
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
        TriageRecommendationNotFoundError: Recommendation not found
        TriageRecommendationConflictError: Recommendation is already reviewed
        TriageRecommendationValidationError: Rejection details are invalid
    """
    if category == RejectionCategory.OTHER and not (reason and reason.strip()):
        raise TriageRecommendationValidationError(
            "Reason is required when category is OTHER"
        )

    recommendation = await get_by_alert_id(db, alert_id, for_update=True)
    if not recommendation:
        raise TriageRecommendationNotFoundError(
            f"No triage recommendation found for alert {alert_id}"
        )

    if recommendation.status != RecommendationStatus.PENDING:
        raise TriageRecommendationConflictError(
            f"Recommendation already {recommendation.status.value}"
        )

    recommendation.status = RecommendationStatus.REJECTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = datetime.now(timezone.utc)
    recommendation.rejection_category = category
    recommendation.rejection_reason = reason

    db.add(recommendation)
    response = TriageRecommendationRead.model_validate(recommendation)
    await db.commit()

    return response
