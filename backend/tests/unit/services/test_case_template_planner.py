from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.enums import CaseTemplateStatus, PICERLStage, Priority
from app.models.models import Case, CaseTemplate, Task, TemplateTaskDefinition, TemplateTaskOverride
from app.services.case_template_planner import plan_case_template_application


def _template() -> CaseTemplate:
    return CaseTemplate(
        id=7,
        title="DLP exfiltration response",
        description="Investigate possible exfiltration",
        status=CaseTemplateStatus.PUBLISHED,
        case_tags=["dlp", "exfiltration"],
        template_tasks=[
            TemplateTaskDefinition(
                title="Collect evidence",
                description="Gather DLP event context",
                picerl_stage=PICERLStage.IDENTIFICATION,
                relative_due_seconds=3600,
                tags=["evidence"],
            ).model_dump(mode="json"),
            TemplateTaskDefinition(
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

    with pytest.raises(ValueError, match="at least one"):
        plan_case_template_application(
            case=case,
            template=_template(),
            overrides=[
                TemplateTaskOverride(index=0, selected=False),
                TemplateTaskOverride(index=1, selected=False),
            ],
            applied_by="analyst",
            applied_at=applied_at,
        )


def test_planner_computes_due_dates_order_priority_and_unassigned_default() -> None:
    case = Case(title="Case", priority=Priority.CRITICAL, created_by="analyst", tags=["existing"])
    applied_at = datetime(2026, 6, 21, 1, 2, 3, tzinfo=timezone.utc)

    plan = plan_case_template_application(
        case=case,
        template=_template(),
        overrides=[TemplateTaskOverride(index=1, assignee="ir-lead")],
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
    case.tasks = [Task(title="collect   evidence", created_by="analyst", source_tpl=7)]
    applied_at = datetime(2026, 6, 21, 1, 2, 3, tzinfo=timezone.utc)

    plan = plan_case_template_application(
        case=case,
        template=_template(),
        overrides=[],
        applied_by="analyst",
        applied_at=applied_at,
    )

    assert len(plan.tasks) == 2
    assert plan.duplicate_warnings[0]["title"] == "Collect evidence"
    assert "already exists" in plan.duplicate_warnings[0]["reasons"][0]
    assert any("already created" in reason for reason in plan.duplicate_warnings[0]["reasons"])
