from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import and_, cast, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.models.enums import CaseTemplateStatus, TaskStatus
from app.models.models import (
    AuditLog,
    Case,
    CaseTemplate,
    CaseTemplateApplyResponse,
    CaseTemplateApplyTaskWarning,
    CaseTemplateCreate,
    CaseTemplateRead,
    CaseTemplateUpdate,
    Task,
    TemplateTaskDefinition,
    TemplateTaskOverride,
)
from app.services.audit_service import get_audit_service
from app.services.case_template_planner import plan_case_template_application
from app.services.case_template_validation import (
    CaseTemplateValidationError,
    normalize_template_title,
    validate_case_template_payload,
)
from app.services.tag_filter_utils import normalize_persisted_tags
from app.services.timeline_service import timeline_service


def parse_case_template_id(raw: int | str) -> int:
    if isinstance(raw, int):
        return raw
    value = str(raw).strip()
    if value.isdigit():
        return int(value)
    if value.upper().startswith("TPL-") and value[4:].isdigit():
        return int(value[4:])
    raise ValueError("Invalid Case Template ID. Expected 123 or TPL-0000123")


class CaseTemplateService:
    async def _ensure_unique_title(
        self,
        db: AsyncSession,
        *,
        title: str | None,
        exclude_id: int | None = None,
    ) -> None:
        normalized = normalize_template_title(title)
        if not normalized:
            return
        filters = [
            CaseTemplate.title_normalized == normalized,
            CaseTemplate.status != CaseTemplateStatus.DELETED,
        ]
        if exclude_id is not None:
            filters.append(CaseTemplate.id != exclude_id)
        result = await db.execute(select(CaseTemplate.id).where(and_(*filters)).limit(1))
        if result.scalar_one_or_none() is not None:
            raise CaseTemplateValidationError("Case Template titles must be unique among non-deleted templates")

    def _to_task_definitions(self, raw_tasks: list[Any] | None) -> list[TemplateTaskDefinition]:
        return [
            task if isinstance(task, TemplateTaskDefinition) else TemplateTaskDefinition.model_validate(task)
            for task in (raw_tasks or [])
        ]

    def _task_json(self, tasks: list[TemplateTaskDefinition]) -> list[dict[str, Any]]:
        return [task.model_dump(mode="json", exclude_none=True) for task in tasks]

    async def create_template(
        self,
        db: AsyncSession,
        payload: CaseTemplateCreate,
        user: str,
    ) -> CaseTemplate:
        status = payload.status or CaseTemplateStatus.DRAFT
        tasks = self._to_task_definitions(payload.template_tasks)
        validate_case_template_payload(
            status=status,
            title=payload.title,
            description=payload.description,
            template_tasks=tasks,
        )
        await self._ensure_unique_title(db, title=payload.title)

        template = CaseTemplate(
            title=payload.title.strip() if payload.title else None,
            title_normalized=normalize_template_title(payload.title),
            description=payload.description,
            status=status,
            case_tags=normalize_persisted_tags(payload.case_tags),
            template_tasks=self._task_json(tasks),
            created_by=user,
            updated_by=user,
        )
        db.add(template)
        await db.flush()
        await get_audit_service(db).log_event(
            event_type="case_template.created",
            entity_type="case_template",
            entity_id=str(template.id),
            description="Case Template created",
            new_value=template,
            performed_by=user,
        )
        await db.commit()
        await db.refresh(template)
        return template

    async def list_templates(
        self,
        db: AsyncSession,
        *,
        statuses: list[CaseTemplateStatus] | None = None,
        search: str | None = None,
    ) -> Page[CaseTemplate]:
        selected_statuses = statuses or [CaseTemplateStatus.PUBLISHED]
        query = select(CaseTemplate).where(col(CaseTemplate.status).in_(selected_statuses))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    col(CaseTemplate.title).ilike(pattern),
                    cast(CaseTemplate.description, String).ilike(pattern),  # type: ignore[arg-type]
                    cast(CaseTemplate.template_tasks, String).ilike(pattern),  # type: ignore[arg-type]
                )
            )
        query = query.order_by(col(CaseTemplate.title).asc().nulls_last(), col(CaseTemplate.id).asc())
        return await apaginate(db, query)

    async def get_template(self, db: AsyncSession, template_id: int) -> CaseTemplate | None:
        result = await db.execute(select(CaseTemplate).where(CaseTemplate.id == template_id))
        return result.scalar_one_or_none()

    async def update_template(
        self,
        db: AsyncSession,
        template_id: int,
        payload: CaseTemplateUpdate,
        user: str,
    ) -> CaseTemplate | None:
        template = await self.get_template(db, template_id)
        if template is None:
            return None
        if template.status == CaseTemplateStatus.DELETED:
            raise CaseTemplateValidationError("Deleted Case Template tombstones cannot be edited")

        before = CaseTemplateRead.model_validate(template).model_dump(mode="json")
        data = payload.model_dump(exclude_unset=True)
        old_status = template.status
        next_status = data.get("status", template.status)
        next_title = data.get("title", template.title)
        next_description = data.get("description", template.description)
        next_tasks = self._to_task_definitions(data.get("template_tasks", template.template_tasks))

        validate_case_template_payload(
            status=next_status,
            title=next_title,
            description=next_description,
            template_tasks=next_tasks,
        )
        await self._ensure_unique_title(db, title=next_title, exclude_id=template_id)

        if "title" in data:
            template.title = next_title.strip() if next_title else None
            template.title_normalized = normalize_template_title(next_title)
        if "description" in data:
            template.description = next_description
        if "status" in data:
            template.status = next_status
        if "case_tags" in data:
            template.case_tags = normalize_persisted_tags(data["case_tags"])
        if "template_tasks" in data:
            template.template_tasks = self._task_json(next_tasks)
        template.updated_by = user
        template.updated_at = datetime.now(timezone.utc)

        status_changed = "status" in data and template.status != old_status
        event_type = (
            {
                CaseTemplateStatus.PUBLISHED: "case_template.published",
                CaseTemplateStatus.DISABLED: "case_template.disabled",
            }.get(template.status, "case_template.updated")
            if status_changed
            else "case_template.updated"
        )
        await get_audit_service(db).log_event(
            event_type=event_type,
            entity_type="case_template",
            entity_id=str(template.id),
            description=event_type.replace("_", " ").replace(".", " "),
            old_value=before,
            new_value=CaseTemplateRead.model_validate(template).model_dump(mode="json"),
            performed_by=user,
        )
        await db.commit()
        await db.refresh(template)
        return template

    async def delete_template(self, db: AsyncSession, template_id: int, user: str) -> CaseTemplate | None:
        template = await self.get_template(db, template_id)
        if template is None:
            return None
        before = CaseTemplateRead.model_validate(template).model_dump(mode="json")
        template.title = None
        template.title_normalized = None
        template.description = None
        template.status = CaseTemplateStatus.DELETED
        template.case_tags = []
        template.template_tasks = []
        template.updated_by = user
        template.updated_at = datetime.now(timezone.utc)
        await get_audit_service(db).log_event(
            event_type="case_template.deleted",
            entity_type="case_template",
            entity_id=str(template.id),
            description="Case Template deleted",
            old_value=before,
            new_value={"id": template.id, "status": template.status},
            performed_by=user,
        )
        await db.commit()
        await db.refresh(template)
        return template

    async def _get_case_for_application(self, db: AsyncSession, case_id: int) -> Case | None:
        result = await db.execute(
            select(Case)
            .options(selectinload(Case.tasks))
            .where(Case.id == case_id)
        )
        return result.scalar_one_or_none()

    async def apply_template(
        self,
        db: AsyncSession,
        *,
        case_id: int,
        template_id: int,
        overrides: list[TemplateTaskOverride],
        user: str,
        applied_at: datetime | None = None,
        commit: bool = True,
    ) -> CaseTemplateApplyResponse:
        template = await self.get_template(db, template_id)
        if template is None:
            raise LookupError("Case Template not found")
        if template.status != CaseTemplateStatus.PUBLISHED:
            raise CaseTemplateValidationError("Only published Case Templates can be applied")
        case = await self._get_case_for_application(db, case_id)
        if case is None:
            raise LookupError("Case not found")

        now = applied_at or datetime.now(timezone.utc)
        plan = plan_case_template_application(
            case=case,
            template=template,
            overrides=overrides,
            applied_by=user,
            applied_at=now,
        )

        created_task_ids: list[int] = []
        for planned in plan.tasks:
            task = Task(
                title=planned.definition.title,
                description=planned.definition.description,
                priority=planned.priority,
                due_date=planned.due_date,
                picerl_stage=planned.definition.picerl_stage,
                status=TaskStatus.TODO,
                assignee=planned.assignee,
                case_id=case_id,
                source_tpl=template_id,
                linked_at=planned.timestamp,
                created_at=planned.timestamp,
                updated_at=planned.timestamp,
                created_by=user,
                tags=normalize_persisted_tags(planned.definition.tags),
                timeline_items={},
            )
            db.add(task)
            await db.flush()
            if task.id is not None:
                created_task_ids.append(task.id)

        case.tags = plan.case_tags_after
        timeline_service.add_timeline_item(
            case,
            {
                "type": "note",
                "description": plan.audit_note,
                "created_at": now,
                "timestamp": now,
                "created_by": user,
                "tags": ["case-template"],
                "flagged": False,
                "highlighted": False,
            },
            created_by=user,
        )

        await get_audit_service(db).log_event(
            event_type="case_template.applied",
            entity_type="case",
            entity_id=str(case_id),
            description=plan.audit_note,
            new_value={
                "template_id": template_id,
                "created_task_ids": created_task_ids,
                "skipped_task_titles": plan.skipped_task_titles,
            },
            performed_by=user,
        )
        if commit:
            await db.commit()
        else:
            await db.flush()

        return CaseTemplateApplyResponse(
            case_id=case_id,
            case_human_id=f"CAS-{case_id:07d}",
            template_id=template_id,
            template_human_id=f"TPL-{template_id:07d}",
            created_task_ids=created_task_ids,
            skipped_task_titles=plan.skipped_task_titles,
            duplicate_warnings=[
                CaseTemplateApplyTaskWarning.model_validate(warning)
                for warning in plan.duplicate_warnings
            ],
        )


case_template_service = CaseTemplateService()
