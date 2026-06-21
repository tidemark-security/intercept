from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.models.enums import Priority
from app.models.models import Case, CaseTemplate, TemplateTaskDefinition, TemplateTaskOverride
from app.services.case_template_validation import normalize_template_title
from app.services.tag_filter_utils import merge_persisted_tags, normalize_persisted_tags


@dataclass(slots=True)
class PlannedTemplateTask:
    index: int
    definition: TemplateTaskDefinition
    assignee: str | None
    due_date: datetime | None
    priority: Priority
    timestamp: datetime
    duplicate: bool = False
    duplicate_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CaseTemplateApplicationPlan:
    tasks: list[PlannedTemplateTask]
    skipped_task_titles: list[str]
    case_tags_after: list[str]
    duplicate_warnings: list[dict[str, Any]]
    audit_note: str


def _task_defs(template: CaseTemplate) -> list[TemplateTaskDefinition]:
    return [
        task if isinstance(task, TemplateTaskDefinition) else TemplateTaskDefinition.model_validate(task)
        for task in (template.template_tasks or [])
    ]


def _overrides_by_index(overrides: list[TemplateTaskOverride]) -> dict[int, TemplateTaskOverride]:
    return {override.index: override for override in overrides}


def _case_task_items(case: Case) -> list[dict[str, Any]]:
    items = getattr(case, "timeline_items", None) or {}
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict) and item.get("type") == "task"]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict) and item.get("type") == "task"]
    return []


def _existing_task_titles(case: Case) -> set[str]:
    normalized: set[str] = set()
    for task in getattr(case, "tasks", None) or []:
        title = normalize_template_title(getattr(task, "title", None))
        if title:
            normalized.add(title)
    for item in _case_task_items(case):
        title = normalize_template_title(item.get("title"))
        if title:
            normalized.add(title)
    return normalized


def _case_has_template_source(case: Case, template_id: int) -> bool:
    for task in getattr(case, "tasks", None) or []:
        if getattr(task, "source_tpl", None) == template_id:
            return True
    for item in _case_task_items(case):
        if item.get("source_tpl") == template_id:
            return True
    return False


def plan_case_template_application(
    *,
    case: Case,
    template: CaseTemplate,
    overrides: list[TemplateTaskOverride],
    applied_by: str,
    applied_at: datetime,
) -> CaseTemplateApplicationPlan:
    task_defs = _task_defs(template)
    by_index = _overrides_by_index(overrides)
    existing_titles = _existing_task_titles(case)
    prior_template_application = template.id is not None and _case_has_template_source(case, template.id)

    planned: list[PlannedTemplateTask] = []
    skipped: list[str] = []
    duplicate_warnings: list[dict[str, Any]] = []

    for index, definition in enumerate(task_defs):
        override = by_index.get(index)
        if override is not None and not override.selected:
            skipped.append(definition.title)
            continue

        due_date = override.due_date if override and override.due_date else None
        if due_date is None and definition.relative_due_seconds is not None:
            due_date = applied_at + timedelta(seconds=definition.relative_due_seconds)

        priority = definition.priority or getattr(case, "priority", None) or Priority.MEDIUM
        timestamp = applied_at + timedelta(microseconds=len(planned))
        reasons: list[str] = []
        normalized_title = normalize_template_title(definition.title)
        if normalized_title and normalized_title in existing_titles:
            reasons.append("A case task with this title already exists")
        if prior_template_application:
            reasons.append("This Case Template has already created tasks on this case")

        planned_task = PlannedTemplateTask(
            index=index,
            definition=definition,
            assignee=override.assignee if override else None,
            due_date=due_date,
            priority=priority,
            timestamp=timestamp,
            duplicate=bool(reasons),
            duplicate_reasons=reasons,
        )
        planned.append(planned_task)
        if reasons:
            duplicate_warnings.append(
                {
                    "index": index,
                    "title": definition.title,
                    "duplicate": True,
                    "reasons": reasons,
                }
            )

    if not planned:
        raise ValueError("Applying a Case Template requires at least one selected Template Task")

    template_human_id = f"TPL-{template.id:07d}" if template.id is not None else "TPL-UNKNOWN"
    audit_note = (
        f"Applied Case Template {template_human_id} {template.title!r} by {applied_by}. "
        f"Created {len(planned)} task(s)."
    )
    if skipped:
        audit_note += f" Skipped: {', '.join(skipped)}."

    return CaseTemplateApplicationPlan(
        tasks=planned,
        skipped_task_titles=skipped,
        case_tags_after=merge_persisted_tags(case.tags, normalize_persisted_tags(template.case_tags)),
        duplicate_warnings=duplicate_warnings,
        audit_note=audit_note,
    )
