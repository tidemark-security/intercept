"""Shared alert triage application helpers.

This module centralizes alert triage mutations so manual triage and
AI recommendation acceptance follow the same core state transitions.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertStatus, CaseStatus, Priority
from app.models.models import Alert, Case

TRIAGE_COMPLETION_STATUSES = {
    AlertStatus.ESCALATED,
    AlertStatus.CLOSED_TP,
    AlertStatus.CLOSED_BP,
    AlertStatus.CLOSED_FP,
    AlertStatus.CLOSED_UNRESOLVED,
    AlertStatus.CLOSED_DUPLICATE,
}


def is_triage_completion_status(status: Optional[AlertStatus]) -> bool:
    return status in TRIAGE_COMPLETION_STATUSES


def apply_triage_state(
    alert: Alert,
    *,
    triaged_by: str,
    status: Optional[AlertStatus] = None,
    triage_notes: Optional[str] = None,
    set_assignee: bool = True,
    now: Optional[datetime] = None,
) -> None:
    timestamp = now or datetime.now(timezone.utc)

    if status is not None:
        alert.status = status

    if triage_notes is not None:
        alert.triage_notes = triage_notes

    if set_assignee:
        alert.assignee = triaged_by

    alert.triaged_at = timestamp


def mark_alert_escalated(
    alert: Alert,
    *,
    case_id: int,
    now: Optional[datetime] = None,
    preserve_existing_linked_at: bool = False,
) -> None:
    timestamp = now or datetime.now(timezone.utc)
    alert.case_id = case_id
    alert.status = AlertStatus.ESCALATED
    if preserve_existing_linked_at and alert.linked_at:
        return

    alert.linked_at = timestamp


async def create_case_from_alert(
    db: AsyncSession,
    *,
    alert: Alert,
    created_by: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[Priority] = None,
    tags: Optional[list[str]] = None,
    assignee: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Case:
    timestamp = now or datetime.now(timezone.utc)
    case = Case(
        title=title or f"Case from Alert: {alert.title}",
        description=description if description is not None else alert.description,
        priority=priority or alert.priority or Priority.MEDIUM,
        tags=tags if tags is not None else (alert.tags or []),
        assignee=assignee,
        status=CaseStatus.IN_PROGRESS,
        timeline_items=[],
        created_by=created_by,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(case)
    await db.flush()
    return case
