from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import and_, cast, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.models.enums import CaseRunbookStatus, TaskStatus
from app.models.models import (
    AuditLog,
    Case,
    CaseRunbook,
    CaseRunbookApplyResponse,
    CaseRunbookApplyTaskWarning,
    CaseRunbookCreate,
    CaseRunbookRead,
    CaseRunbookUpdate,
    Task,
    RunbookTaskDefinition,
    RunbookTaskOverride,
)
from app.services.audit_service import get_audit_service
from app.services.case_runbook_planner import plan_case_runbook_application
from app.services.case_runbook_validation import (
    CaseRunbookValidationError,
    normalize_runbook_title,
    validate_case_runbook_payload,
)
from app.services.tag_filter_utils import normalize_persisted_tags
from app.services.timeline_service import timeline_service


def parse_case_runbook_id(raw: int | str) -> int:
    if isinstance(raw, int):
        return raw
    value = str(raw).strip()
    if value.isdigit():
        return int(value)
    if value.upper().startswith("RUN-") and value[4:].isdigit():
        return int(value[4:])
    raise ValueError("Invalid Case Runbook ID. Expected 123 or RUN-0000123")


class CaseRunbookService:
    async def _ensure_unique_title(
        self,
        db: AsyncSession,
        *,
        title: str | None,
        exclude_id: int | None = None,
    ) -> None:
        normalized = normalize_runbook_title(title)
        if not normalized:
            return
        filters = [
            CaseRunbook.title_normalized == normalized,
            CaseRunbook.status != CaseRunbookStatus.DELETED,
        ]
        if exclude_id is not None:
            filters.append(CaseRunbook.id != exclude_id)
        result = await db.execute(select(CaseRunbook.id).where(and_(*filters)).limit(1))
        if result.scalar_one_or_none() is not None:
            raise CaseRunbookValidationError("Case Runbook titles must be unique among non-deleted runbooks")

    def _to_task_definitions(self, raw_tasks: list[Any] | None) -> list[RunbookTaskDefinition]:
        return [
            task if isinstance(task, RunbookTaskDefinition) else RunbookTaskDefinition.model_validate(task)
            for task in (raw_tasks or [])
        ]

    def _task_json(self, tasks: list[RunbookTaskDefinition]) -> list[dict[str, Any]]:
        return [task.model_dump(mode="json", exclude_none=True) for task in tasks]

    async def create_runbook(
        self,
        db: AsyncSession,
        payload: CaseRunbookCreate,
        user: str,
    ) -> CaseRunbook:
        status = payload.status or CaseRunbookStatus.DRAFT
        tasks = self._to_task_definitions(payload.runbook_tasks)
        validate_case_runbook_payload(
            status=status,
            title=payload.title,
            description=payload.description,
            runbook_tasks=tasks,
        )
        await self._ensure_unique_title(db, title=payload.title)

        runbook = CaseRunbook(
            title=payload.title.strip() if payload.title else None,
            title_normalized=normalize_runbook_title(payload.title),
            description=payload.description,
            status=status,
            case_tags=normalize_persisted_tags(payload.case_tags),
            runbook_tasks=self._task_json(tasks),
            created_by=user,
            updated_by=user,
        )
        db.add(runbook)
        await db.flush()
        await get_audit_service(db).log_event(
            event_type="case_runbook.created",
            entity_type="case_runbook",
            entity_id=str(runbook.id),
            description="Case Runbook created",
            new_value=runbook,
            performed_by=user,
        )
        await db.commit()
        await db.refresh(runbook)
        return runbook

    async def list_runbooks(
        self,
        db: AsyncSession,
        *,
        statuses: list[CaseRunbookStatus] | None = None,
        search: str | None = None,
    ) -> Page[CaseRunbook]:
        selected_statuses = statuses or [CaseRunbookStatus.PUBLISHED]
        query = select(CaseRunbook).where(col(CaseRunbook.status).in_(selected_statuses))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    col(CaseRunbook.title).ilike(pattern),
                    cast(CaseRunbook.description, String).ilike(pattern),  # type: ignore[arg-type]
                    cast(CaseRunbook.runbook_tasks, String).ilike(pattern),  # type: ignore[arg-type]
                )
            )
        query = query.order_by(col(CaseRunbook.title).asc().nulls_last(), col(CaseRunbook.id).asc())
        return await apaginate(db, query)

    async def get_runbook(self, db: AsyncSession, runbook_id: int) -> CaseRunbook | None:
        result = await db.execute(select(CaseRunbook).where(CaseRunbook.id == runbook_id))
        return result.scalar_one_or_none()

    async def update_runbook(
        self,
        db: AsyncSession,
        runbook_id: int,
        payload: CaseRunbookUpdate,
        user: str,
    ) -> CaseRunbook | None:
        runbook = await self.get_runbook(db, runbook_id)
        if runbook is None:
            return None
        if runbook.status == CaseRunbookStatus.DELETED:
            raise CaseRunbookValidationError("Deleted Case Runbook tombstones cannot be edited")

        before = CaseRunbookRead.model_validate(runbook).model_dump(mode="json")
        data = payload.model_dump(exclude_unset=True)
        old_status = runbook.status
        next_status = data.get("status", runbook.status)
        next_title = data.get("title", runbook.title)
        next_description = data.get("description", runbook.description)
        next_tasks = self._to_task_definitions(data.get("runbook_tasks", runbook.runbook_tasks))

        validate_case_runbook_payload(
            status=next_status,
            title=next_title,
            description=next_description,
            runbook_tasks=next_tasks,
        )
        await self._ensure_unique_title(db, title=next_title, exclude_id=runbook_id)

        if "title" in data:
            runbook.title = next_title.strip() if next_title else None
            runbook.title_normalized = normalize_runbook_title(next_title)
        if "description" in data:
            runbook.description = next_description
        if "status" in data:
            runbook.status = next_status
        if "case_tags" in data:
            runbook.case_tags = normalize_persisted_tags(data["case_tags"])
        if "runbook_tasks" in data:
            runbook.runbook_tasks = self._task_json(next_tasks)
        runbook.updated_by = user
        runbook.updated_at = datetime.now(timezone.utc)

        status_changed = "status" in data and runbook.status != old_status
        event_type = (
            {
                CaseRunbookStatus.PUBLISHED: "case_runbook.published",
                CaseRunbookStatus.DISABLED: "case_runbook.disabled",
            }.get(runbook.status, "case_runbook.updated")
            if status_changed
            else "case_runbook.updated"
        )
        await get_audit_service(db).log_event(
            event_type=event_type,
            entity_type="case_runbook",
            entity_id=str(runbook.id),
            description=event_type.replace("_", " ").replace(".", " "),
            old_value=before,
            new_value=CaseRunbookRead.model_validate(runbook).model_dump(mode="json"),
            performed_by=user,
        )
        await db.commit()
        await db.refresh(runbook)
        return runbook

    async def delete_runbook(self, db: AsyncSession, runbook_id: int, user: str) -> CaseRunbook | None:
        runbook = await self.get_runbook(db, runbook_id)
        if runbook is None:
            return None
        before = CaseRunbookRead.model_validate(runbook).model_dump(mode="json")
        runbook.title = None
        runbook.title_normalized = None
        runbook.description = None
        runbook.status = CaseRunbookStatus.DELETED
        runbook.case_tags = []
        runbook.runbook_tasks = []
        runbook.updated_by = user
        runbook.updated_at = datetime.now(timezone.utc)
        await get_audit_service(db).log_event(
            event_type="case_runbook.deleted",
            entity_type="case_runbook",
            entity_id=str(runbook.id),
            description="Case Runbook deleted",
            old_value=before,
            new_value={"id": runbook.id, "status": runbook.status},
            performed_by=user,
        )
        await db.commit()
        await db.refresh(runbook)
        return runbook

    async def _get_case_for_application(self, db: AsyncSession, case_id: int) -> Case | None:
        result = await db.execute(
            select(Case)
            .options(selectinload(Case.tasks))
            .where(Case.id == case_id)
        )
        return result.scalar_one_or_none()

    async def apply_runbook(
        self,
        db: AsyncSession,
        *,
        case_id: int,
        runbook_id: int,
        overrides: list[RunbookTaskOverride],
        user: str,
        applied_at: datetime | None = None,
        commit: bool = True,
    ) -> CaseRunbookApplyResponse:
        runbook = await self.get_runbook(db, runbook_id)
        if runbook is None:
            raise LookupError("Case Runbook not found")
        if runbook.status != CaseRunbookStatus.PUBLISHED:
            raise CaseRunbookValidationError("Only published Case Runbooks can be applied")
        case = await self._get_case_for_application(db, case_id)
        if case is None:
            raise LookupError("Case not found")

        now = applied_at or datetime.now(timezone.utc)
        plan = plan_case_runbook_application(
            case=case,
            runbook=runbook,
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
                source_runbook=runbook_id,
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
                "created_by": "system",
                "tags": ["case-runbook", "system"],
                "flagged": False,
                "highlighted": False,
            },
            created_by="system",
        )

        await get_audit_service(db).log_event(
            event_type="case_runbook.applied",
            entity_type="case",
            entity_id=str(case_id),
            description=plan.audit_note,
            new_value={
                "runbook_id": runbook_id,
                "created_task_ids": created_task_ids,
                "skipped_task_titles": plan.skipped_task_titles,
            },
            performed_by=user,
        )
        if commit:
            await db.commit()
        else:
            await db.flush()

        return CaseRunbookApplyResponse(
            case_id=case_id,
            case_human_id=f"CAS-{case_id:07d}",
            runbook_id=runbook_id,
            runbook_human_id=f"RUN-{runbook_id:07d}",
            created_task_ids=created_task_ids,
            skipped_task_titles=plan.skipped_task_titles,
            duplicate_warnings=[
                CaseRunbookApplyTaskWarning.model_validate(warning)
                for warning in plan.duplicate_warnings
            ],
        )


case_runbook_service = CaseRunbookService()
