"""Analyst workflow tools backed by the same transactional operations as the web UI."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import HTTPException
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.entity_ids import CASE_PREFIX, format_entity_id
from app.core.id_parser import EntityIdParseError, parse_entity_id
from app.mcp.tools import _require_mcp_non_auditor_user
from app.models.enums import AlertStatus, CaseStatus, RecommendationStatus, RejectionCategory, TaskStatus
from app.models.models import (
    Alert,
    AlertTriageRequest,
    AlertUpdate,
    Case,
    CaseUpdate,
    Task,
    TaskUpdate,
    TriageRecommendationRead,
)
from app.models.search_schemas import EntityType
from app.services import triage_recommendation_service as triage
from app.services.alert_service import AlertValidationError, alert_service
from app.services.case_service import CaseValidationError, case_service
from app.services.date_filter_utils import parse_utc_datetime
from app.services.task_service import TaskValidationError, task_service


@asynccontextmanager
async def _workflow_session():
    try:
        async with async_session_factory() as db:
            yield db
    except (triage.TriageRecommendationError, AlertValidationError, CaseValidationError, TaskValidationError) as exc:
        raise ToolError(str(exc)) from exc


def _actor() -> str:
    try:
        return _require_mcp_non_auditor_user()
    except HTTPException as exc:
        raise ToolError(exc.detail) from exc


def _id(value: str, kind: str) -> int:
    try:
        return parse_entity_id(value, kind)[0]
    except EntityIdParseError as exc:
        raise ToolError(str(exc)) from exc


def _revision(value: str) -> datetime:
    try:
        return parse_utc_datetime(value)
    except ValueError as exc:
        raise ToolError("Use the ISO-8601 created_at from get_triage_recommendation") from exc


async def set_status(
    kind: EntityType, id: str, status: AlertStatus | CaseStatus | TaskStatus, commit: bool = False,
) -> dict:
    """Change an alert, case or task status. Case closure also resolves linked work. Closing an alert
    completes manual triage and can reject a pending recommendation. Use escalate_alert_to_case for ESCALATED.

    Args:
        kind: Parent kind (alert, case or task).
        id: Numeric or prefixed work item ID.
        status: Alert NEW, IN_PROGRESS or CLOSED_* resolution. Case NEW, IN_PROGRESS or CLOSED. Task TODO, IN_PROGRESS or DONE.
        commit: False previews the requested status. True applies it as the authenticated analyst.
    """
    actor = _actor() if commit else None
    entity_id = _id(id, kind)
    model, statuses = {
        EntityType.ALERT: (Alert, AlertStatus),
        EntityType.CASE: (Case, CaseStatus),
        EntityType.TASK: (Task, TaskStatus),
    }[kind]
    if status not in list(statuses):
        raise ToolError(f"Invalid {kind.value} status. Choose from {', '.join(s.value for s in statuses)}")
    if status == AlertStatus.ESCALATED:
        raise ToolError("Use escalate_alert_to_case to create and link a case")
    async with _workflow_session() as db:
        if actor is None:
            entity = await db.get(model, entity_id)
        elif kind == EntityType.ALERT:
            entity = await alert_service.update_alert(db, entity_id, AlertUpdate(status=AlertStatus(status)), actor)
        elif kind == EntityType.CASE:
            entity = await case_service.update_case(db, entity_id, CaseUpdate(status=CaseStatus(status)), actor)
        else:
            entity = await task_service.update_task(db, entity_id, TaskUpdate(status=TaskStatus(status)), actor)
        if entity is None:
            raise ToolError(f"{kind.value} {id} not found")
        result = {
            "mode": "committed" if commit else "dry_run",
            "kind": kind.value,
            "id": entity_id,
            "status": entity.status.value,
            "requested_status": status.value,
        }
        if not commit and kind == EntityType.CASE and status == CaseStatus.CLOSED:
            result["closure_impact"] = await case_service.preview_closure_impact(
                db, entity_id, entity.status,
            )
        return result


async def escalate_alert_to_case(
    alert_id: str, case_title: Annotated[str, Field(min_length=1, max_length=200)] | None = None,
    case_description: str | None = None, triage_notes: str | None = None, commit: bool = False,
) -> dict:
    """Manually triage an alert, create a case and link it. Pending recommendations are auto-rejected.
    To apply a recommendation and its runbook or tasks, use accept_triage_recommendation.

    Args:
        alert_id: Numeric or prefixed alert ID.
        case_title: Optional title for the new case. Defaults to a title derived from the alert.
        case_description: Optional case description. Defaults to the alert description.
        triage_notes: Optional analyst notes for manual triage.
        commit: False previews the escalation. True creates and links the case.
    """
    actor = _actor() if commit else None
    numeric_id = _id(alert_id, "alert")
    async with _workflow_session() as db:
        if actor is None:
            alert = await db.get(Alert, numeric_id)
            if alert is not None and alert.case_id is not None:
                raise ToolError("Alert is already escalated to a case")
        else:
            alert = await alert_service.triage_alert(
                db,
                numeric_id,
                AlertTriageRequest(
                    status=AlertStatus.ESCALATED,
                    escalate_to_case=True,
                    case_title=case_title,
                    case_description=case_description,
                    triage_notes=triage_notes,
                ),
                actor,
            )
        if alert is None:
            raise ToolError(f"Alert {alert_id} not found")
        return {
            "mode": "committed" if commit else "dry_run",
            "alert_id": numeric_id,
            "status": alert.status.value,
            "requested_status": AlertStatus.ESCALATED.value,
            "case_id": alert.case_id,
            "case_human_id": format_entity_id(alert.case_id, CASE_PREFIX) if alert.case_id else None,
        }


class AcceptanceOutcome(BaseModel):
    alert_status: AlertStatus
    case_action: Literal["create", "reuse", "none"]
    case_human_id: str | None = None


class AcceptanceOutcomes(BaseModel):
    apply_status: AcceptanceOutcome
    skip_status: AcceptanceOutcome


class GetTriageRecommendationOutput(TriageRecommendationRead):
    acceptance_outcomes: AcceptanceOutcomes | None = None


def _acceptance_outcome(decision: triage.AcceptanceStatusDecision) -> AcceptanceOutcome:
    case_id = decision.existing_case_id
    if case_id is not None:
        return AcceptanceOutcome(
            alert_status=decision.alert_status, case_action="reuse",
            case_human_id=format_entity_id(case_id, CASE_PREFIX),
        )
    return AcceptanceOutcome(
        alert_status=decision.alert_status, case_action="create" if decision.should_escalate else "none",
    )


async def get_triage_recommendation(alert_id: str) -> GetTriageRecommendationOutput:
    """Read the current recommendation, reasoning, suggested patches, and review status.
    Pending recommendations include the alert status and case outcome for both apply_status choices.
    Use its created_at as expected_created_at to review this exact revision.

    Args:
        alert_id: Numeric or prefixed alert ID.
    """
    numeric_id = _id(alert_id, "alert")
    async with _workflow_session() as db:
        recommendation = await triage.get_by_alert_id(db, numeric_id)
        if recommendation is None:
            raise ToolError(f"No triage recommendation found for alert {alert_id}")
        output = GetTriageRecommendationOutput.model_validate(recommendation)
        if recommendation.status == RecommendationStatus.PENDING:
            case_id = await db.scalar(select(Alert.case_id).where(Alert.id == numeric_id))
            output.acceptance_outcomes = AcceptanceOutcomes(
                apply_status=_acceptance_outcome(
                    triage.acceptance_status_decision(recommendation, case_id, apply_status=True)
                ),
                skip_status=_acceptance_outcome(
                    triage.acceptance_status_decision(recommendation, case_id, apply_status=False)
                ),
            )
        return output


async def accept_triage_recommendation(
    alert_id: str, expected_created_at: str, apply_status: bool = True, apply_priority: bool = True,
    apply_assignee: bool = True, apply_tags: bool = True, case_runbook_id: int | None = None,
    skip_case_runbook: bool = False,
) -> dict:
    """Accept the reviewed pending revision immediately. An accepted dismissal applies the closing
    status. An investigation, or declining to apply the closing status, escalates to a case.
    Returns the applied changes, case ID and number of tasks created.

    Args:
        alert_id: Numeric or prefixed alert ID.
        expected_created_at: Exact created_at from get_triage_recommendation.
        apply_status: Apply the suggested status. Skipping closure triggers case-based investigation.
        apply_priority: Apply the suggested priority.
        apply_assignee: Apply the triage assignee.
        apply_tags: Apply suggested tag changes.
        case_runbook_id: Published runbook override for escalation.
        skip_case_runbook: Skip the recommended runbook. Mutually exclusive with case_runbook_id.
    """
    actor = _actor()
    async with _workflow_session() as db:
        result = await triage.accept_recommendation(
            db,
            _id(alert_id, "alert"),
            triage.AcceptRecommendationOptions(
                apply_status=apply_status,
                apply_priority=apply_priority,
                apply_assignee=apply_assignee,
                apply_tags=apply_tags,
                case_runbook_id=case_runbook_id,
                skip_case_runbook=skip_case_runbook,
            ),
            reviewed_by=actor,
            expected_created_at=_revision(expected_created_at),
        )
        return {
            "recommendation": result.recommendation.model_dump(mode="json"),
            "case_id": result.case_id,
            "case_human_id": format_entity_id(result.case_id, CASE_PREFIX) if result.case_id else None,
            "tasks_created": result.tasks_created,
        }


async def reject_triage_recommendation(
    alert_id: str, expected_created_at: str, category: RejectionCategory,
    reason: Annotated[str, Field(max_length=500)] | None = None,
) -> TriageRecommendationRead:
    """Immediately reject the reviewed pending revision, recording the reviewer and reason.

    Args:
        alert_id: Numeric or prefixed alert ID.
        expected_created_at: Exact created_at from get_triage_recommendation.
        category: Reason category for this review.
        reason: Optional details up to 500 characters. Required for OTHER.
    """
    actor = _actor()
    async with _workflow_session() as db:
        return await triage.reject_recommendation(
            db, _id(alert_id, "alert"), category, reason, reviewed_by=actor,
            expected_created_at=_revision(expected_created_at),
        )
