from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.enums import CaseRunbookStatus, PICERLStage, Priority
from app.models.models import Case, CaseRunbook, Task, RunbookTaskDefinition, RunbookTaskOverride
from app.services.case_runbook_planner import plan_case_runbook_application
from app.services.case_runbook_validation import CaseRunbookValidationError


def _runbook() -> CaseRunbook:
    return CaseRunbook(
        id=7,
        title="DLP exfiltration response",
        description="Investigate possible exfiltration",
        status=CaseRunbookStatus.PUBLISHED,
        case_tags=["dlp", "exfiltration"],
        runbook_tasks=[
            RunbookTaskDefinition(
                title="Collect evidence",
                description="Gather DLP event context",
                picerl_stage=PICERLStage.IDENTIFICATION,
                relative_due_seconds=3600,
                tags=["evidence"],
            ).model_dump(mode="json"),
            RunbookTaskDefinition(
                title="Contain account",
                picerl_stage=PICERLStage.CONTAINMENT,
                priority=Priority.HIGH,
            ).model_dump(mode="json"),
        ],
        created_by="admin",
        updated_by="admin",
    )


def test_planner_rejects_no_selected_tasks() -> None:
    case = Case(title="Case", priority=Priority.MEDIUM, created_by="analyst")
    applied_at = datetime(2026, 6, 21, 1, 2, 3, tzinfo=timezone.utc)

    with pytest.raises(CaseRunbookValidationError, match="at least one"):
        plan_case_runbook_application(
            case=case,
            runbook=_runbook(),
            overrides=[
                RunbookTaskOverride(index=0, selected=False),
                RunbookTaskOverride(index=1, selected=False),
            ],
            applied_by="analyst",
            applied_at=applied_at,
        )


def test_planner_computes_due_dates_order_priority_and_unassigned_default() -> None:
    case = Case(title="Case", priority=Priority.CRITICAL, created_by="analyst", tags=["existing"])
    applied_at = datetime(2026, 6, 21, 1, 2, 3, tzinfo=timezone.utc)

    plan = plan_case_runbook_application(
        case=case,
        runbook=_runbook(),
        overrides=[RunbookTaskOverride(index=1, assignee="ir-lead")],
        applied_by="analyst",
        applied_at=applied_at,
    )

    assert len(plan.tasks) == 2
    assert plan.tasks[0].due_date == datetime(2026, 6, 21, 2, 2, 3, tzinfo=timezone.utc)
    assert plan.tasks[0].timestamp == applied_at
    assert plan.tasks[1].timestamp > plan.tasks[0].timestamp
    assert plan.tasks[0].priority == Priority.CRITICAL
    assert plan.tasks[1].priority == Priority.HIGH
    assert plan.tasks[0].assignee is None
    assert plan.tasks[1].assignee == "ir-lead"
    assert plan.case_tags_after == ["existing", "dlp", "exfiltration"]
    assert "Created 2 task(s)" in plan.audit_note


def test_planner_detects_duplicate_titles_without_blocking() -> None:
    case = Case(title="Case", priority=Priority.MEDIUM, created_by="analyst")
    case.tasks = [Task(title="collect   evidence", created_by="analyst", source_runbook=7)]
    applied_at = datetime(2026, 6, 21, 1, 2, 3, tzinfo=timezone.utc)

    plan = plan_case_runbook_application(
        case=case,
        runbook=_runbook(),
        overrides=[],
        applied_by="analyst",
        applied_at=applied_at,
    )

    assert len(plan.tasks) == 2
    assert plan.duplicate_warnings[0]["title"] == "Collect evidence"
    assert "already exists" in plan.duplicate_warnings[0]["reasons"][0]
    assert any("already created" in reason for reason in plan.duplicate_warnings[0]["reasons"])
