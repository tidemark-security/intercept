from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, cast, String, case
from sqlalchemy.orm import selectinload, defer
from sqlmodel import col
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import logging
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate

from app.core.entity_ids import CASE_PREFIX, format_entity_id
from app.models.models import (
    Case, Alert, Task,
    CaseCreate, CaseUpdate,
    CaseTimelineItem, CaseAlertClosureUpdate,
    CaseLinkedAlertResolutionRequest, AlertBulkActionResponse,
)
from app.models.enums import CaseStatus, AlertStatus, TaskStatus, RealtimeEventType
from app.services.alert_triage_apply_service import CLOSED_ALERT_STATUSES, apply_triage_state
from app.services.timeline_add_service import (
    TimelineItemConflict,
    add_timeline_item_and_commit,
    remove_timeline_item_and_commit,
    update_timeline_item_and_commit,
)
from app.services.timeline_service import TimelineValidationError, timeline_service
from app.services.audit_service import get_audit_service
from app.services.realtime_service import emit_event
from app.services import triage_recommendation_service
from app.services.date_filter_utils import DateFilterValidationError, parse_datetime_filter
from app.services.tag_filter_utils import (
    ProtectedTagMutationError,
    append_tag_filters,
    normalize_persisted_tags,
    validate_protected_tag_mutation,
)
from app.services.committed_response import load_committed_response

logger = logging.getLogger(__name__)


class CaseValidationError(ValueError):
    """A case operation violates a client-facing domain rule."""


CASE_DELETE_AUDIT_DESCRIPTION_MAX_CHARS = 2048
CASE_DELETE_AUDIT_MAX_TAGS = 50
CASE_DELETE_AUDIT_TAG_MAX_CHARS = 128

# Human-readable descriptions for alert closure statuses
ALERT_STATUS_DESCRIPTIONS = {
    AlertStatus.CLOSED_TP: "True Positive",
    AlertStatus.CLOSED_BP: "Benign Positive",
    AlertStatus.CLOSED_FP: "False Positive",
    AlertStatus.CLOSED_UNRESOLVED: "Unresolved",
    AlertStatus.CLOSED_DUPLICATE: "Duplicate"
}


class CaseService:
    
    async def create_case(
        self, 
        db: AsyncSession, 
        case_data: CaseCreate, 
        created_by: str,
        created_at_override: Optional[datetime] = None,
        closed_at_override: Optional[datetime] = None,
    ) -> Case:
        """Create a new case."""
        try:
            try:
                normalized_tags = validate_protected_tag_mutation(None, case_data.tags)
            except ProtectedTagMutationError as exc:
                raise CaseValidationError(str(exc)) from exc
            # Create case
            case_kwargs = {
                "title": case_data.title,
                "description": case_data.description,
                "priority": case_data.priority,
                "assignee": case_data.assignee,
                "tags": normalized_tags,
                "timeline_items": {},  # Initialize empty timeline as object-backed storage
                "created_by": created_by,
            }
            if created_at_override is not None:
                case_kwargs["created_at"] = created_at_override
            if "closed_at" in case_data.model_fields_set:
                case_kwargs["closed_at"] = closed_at_override

            db_case = Case(**case_kwargs)
            
            db.add(db_case)
            await db.flush()  # Get the ID without committing
            
            # Create audit log
            await self._create_audit_log(
                db, db_case.id, "created", "Case created", None, None, created_by  # type: ignore[arg-type]
            )
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating case: {e}")
            raise

        case_id = db_case.id  # type: ignore[assignment]
        logger.info(f"Case created by {created_by}")
        return await load_committed_response(
            db,
            lambda: self.get_case(db, case_id),
            db_case,
            logger=logger,
            entity_type="case",
            entity_id=case_id,
            operation="creation",
        )
    
    async def _get_case_model(
        self,
        db: AsyncSession,
        case_id: int,
    ) -> Optional[Case]:
        """Get the tracked case model with related entities loaded."""
        query = (
            select(Case)
            .options(
                selectinload(Case.alerts).selectinload(Alert.triage_recommendation),
                selectinload(Case.tasks)
            )
            .where(Case.id == case_id)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def lock_case_for_update(
        self,
        db: AsyncSession,
        case_id: int,
    ) -> Optional[Case]:
        """Lock and refresh a case before mutating it."""
        result = await db.execute(
            select(Case)
            .where(Case.id == case_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_case(
        self, 
        db: AsyncSession, 
        case_id: int,
        include_linked_timelines: bool = False
    ) -> Optional[Case]:
        """Get case by ID with related data.
        
        Args:
            db: Database session
            case_id: Case ID to fetch
            include_linked_timelines: If True, alert and task timeline items will include
                source_timeline_items from the linked entity
        """
        db_case = await self._get_case_model(db, case_id)
        if not db_case:
            return None

        return await timeline_service.prepare_entity_detail_timeline(
            db,
            entity_type="case",
            entity_id=case_id,
            entity=db_case,
            human_prefix=CASE_PREFIX,
            include_linked_timelines=include_linked_timelines,
        )
    
    async def get_case_minimal(self, db: AsyncSession, case_id: int) -> Optional[Case]:
        """Get case by ID without denormalization (for injection into other timelines)."""
        result = await db.execute(select(Case).where(Case.id == case_id))
        return result.scalar_one_or_none()


    async def _load_timeline_mutation_response(
        self,
        db: AsyncSession,
        case_id: int,
    ) -> Optional[Case]:
        db_case = await self._get_case_model(db, case_id)
        if db_case is None:
            return None
        db_case = await timeline_service.denormalize_entity_timeline(
            db,
            db_case,
            human_prefix=CASE_PREFIX,
        )
        return await timeline_service.coalesce_timeline_audit(
            db,
            entity_type="case",
            entity_id=case_id,
            entity=db_case,
        )
    
    async def get_cases(
        self, 
        db: AsyncSession, 
        status: Optional[List[CaseStatus]] = None,
        assignee: Optional[str] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Page[Case]:
        """Get cases with optional filtering and pagination.
        
        Args:
            status: Filter by case status (can filter by multiple statuses)
            assignee: Filter by assignee username (exact match)
            include_tags: Tags cases must include
            exclude_tags: Tags cases must exclude
            search: Search string to match against case ID, human ID, title, or description (case-insensitive partial match)
            start_date: Filter cases created after this UTC datetime (ISO8601 format with 'Z' suffix)
            end_date: Filter cases created before this UTC datetime (ISO8601 format with 'Z' suffix)
        """
        # Defer timeline_items because list responses do not need the potentially
        # malformed legacy JSON that detail views normalize separately.
        query = select(Case).options(defer(Case.timeline_items))
        filters = []
        if status:
            filters.append(col(Case.status).in_(status))
        if assignee:
            filters.append(
                Case.assignee.is_(None)  # type: ignore
                if assignee == "__unassigned__"
                else Case.assignee == assignee
            )

        append_tag_filters(filters, Case.tags, include_tags, exclude_tags)
        try:
            start_dt = parse_datetime_filter(start_date, parameter="start_date")
            end_dt = parse_datetime_filter(end_date, parameter="end_date")
        except DateFilterValidationError as exc:
            raise CaseValidationError(str(exc)) from exc

        if start_dt is not None:
            filters.append(Case.created_at >= start_dt)
        if end_dt is not None:
            filters.append(Case.created_at <= end_dt)
        if search:
            search_pattern = f"%{search}%"
            case_id_text = cast(Case.id, String)
            padded_case_id = case(
                (func.length(case_id_text) < 7, func.lpad(case_id_text, 7, "0")),
                else_=case_id_text,
            )
            filters.append(
                or_(
                    case_id_text.ilike(search_pattern),  # type: ignore[arg-type]
                    func.concat(
                        f"{CASE_PREFIX}-",
                        padded_case_id,
                    ).ilike(search_pattern),
                    col(Case.title).ilike(search_pattern),
                    cast(Case.description, String).ilike(search_pattern),  # type: ignore[arg-type]
                )
            )
        if filters:
            query = query.where(and_(*filters))

        allowed_sort_columns = {
            "id": Case.id,
            "title": Case.title,
            "status": Case.status,
            "priority": Case.priority,
            "assignee": Case.assignee,
            "created_at": Case.created_at,
            "updated_at": Case.updated_at,
        }
        try:
            sort_column = allowed_sort_columns[sort_by]
        except KeyError as exc:
            raise CaseValidationError(
                f"Unsupported case sort column: {sort_by}"
            ) from exc
        ordering = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()
        return await apaginate(db, query.order_by(ordering))

    async def update_case(
        self, 
        db: AsyncSession, 
        case_id: int, 
        case_update: CaseUpdate, 
        updated_by: str,
        closed_at_override: Optional[datetime] = None,
        closed_at_override_supplied: bool = False,
    ) -> Optional[Case]:
        """Update a case and create audit logs."""
        try:
            # Get existing case
            db_case = await self.lock_case_for_update(db, case_id)
            if not db_case:
                return None
            
            # Track changes for audit
            changes = []
            update_data = case_update.model_dump(exclude_unset=True)
            update_data.pop("closed_at", None)
            
            # Track if status changed to CLOSED
            status_changed_to_closed = False
            old_status = db_case.status
            
            for field, new_value in update_data.items():
                if hasattr(db_case, field):
                    if field == "tags":
                        try:
                            new_value = validate_protected_tag_mutation(
                                db_case.tags,
                                new_value,
                            )
                        except ProtectedTagMutationError as exc:
                            raise CaseValidationError(str(exc)) from exc
                    old_value = getattr(db_case, field)
                    if old_value != new_value:
                        changes.append((field, str(old_value), str(new_value)))
                        setattr(db_case, field, new_value)
                        # Track specific changes for metrics
                        if field == 'status' and new_value == CaseStatus.CLOSED:
                            status_changed_to_closed = True
            
            # Handle status change special case
            if closed_at_override_supplied:
                old_value = db_case.closed_at
                if old_value != closed_at_override:
                    changes.append(("closed_at", str(old_value), str(closed_at_override)))
                    db_case.closed_at = closed_at_override
            elif status_changed_to_closed:
                db_case.closed_at = datetime.now(timezone.utc)
            
            # Create audit logs for changes
            for field, old_val, new_val in changes:
                await self._create_audit_log(
                    db, case_id, f"{field}_changed", 
                    f"{field.title()} changed from {old_val} to {new_val}",
                    old_val, new_val, updated_by
                )
            
            # If case status changed to CLOSED, close all linked tasks and alerts
            if status_changed_to_closed and old_status != CaseStatus.CLOSED:
                self._add_case_closure_summary_note(
                    db_case, case_update.closure_summary, updated_by
                )

                # Extract alert closure statuses if provided
                alert_closure_statuses = self._build_alert_closure_status_map(
                    case_update.alert_closure_updates
                )
                
                closure_results = await self._close_linked_items(
                    db, case_id, updated_by, alert_closure_statuses
                )

                # Create audit log for linked item closures
                summary = (
                    f"Closed {closure_results['tasks_closed']} linked tasks and "
                    f"{closure_results['alerts_closed']} linked alerts."
                )

                await self._create_audit_log(
                    db, case_id, "linked_items_closed",
                    summary,
                    None, None, updated_by
                )
            
            await emit_event(
                db,
                entity_type="case",
                entity_id=case_id,
                event_type=RealtimeEventType.ENTITY_UPDATED,
                performed_by=updated_by,
            )

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating case {case_id}: {e}")
            raise

        logger.info(f"Case updated by {updated_by}")
        return await load_committed_response(
            db,
            lambda: self.get_case(db, case_id),
            db_case,
            logger=logger,
            entity_type="case",
            entity_id=case_id,
            operation="update",
        )
    
    def _close_linked_task(
        self,
        task: Task,
        case_human_id: str,
        closed_by: str
    ) -> bool:
        """
        Close a single linked task and add a note to its timeline.
        Returns whether the task status changed.
        """
        if task.status == TaskStatus.DONE:
            return False

        task.status = TaskStatus.DONE
        task.updated_at = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        closure_note = timeline_service.build_note_item(
            description=f"Task closed automatically due to case {case_human_id} closure",
            created_by=closed_by,
            created_at=now.isoformat(),
            timestamp=now.isoformat(),
            tags=["auto-close", "case-closure"],
        )
        timeline_service.add_timeline_item(task, closure_note, created_by=closed_by)

        logger.info(f"Task {task.id} closed due to case {case_human_id} closure")
        return True
    
    def _close_linked_alert(
        self,
        alert: Alert,
        case_human_id: str,
        closed_by: str,
        custom_status: Optional[AlertStatus] = None
    ) -> bool:
        """
        Close a single linked alert with the specified status.
        Returns whether the alert status changed.
        
        Args:
            alert: Alert to close
            case_human_id: Human-readable case ID for logging
            closed_by: Username of the user closing the alert
            custom_status: Optional custom closure status. If not provided, defaults to CLOSED_UNRESOLVED
        """
        if alert.status in CLOSED_ALERT_STATUSES:
            return False

        closure_status = custom_status or AlertStatus.CLOSED_UNRESOLVED
        if closure_status not in CLOSED_ALERT_STATUSES:
            raise CaseValidationError(
                f"Invalid closure status for alert {alert.id}: {closure_status}"
            )

        alert.status = closure_status
        alert.updated_at = datetime.now(timezone.utc)
        status_desc = ALERT_STATUS_DESCRIPTIONS.get(closure_status, str(closure_status))

        now = datetime.now(timezone.utc)
        closure_note = timeline_service.build_note_item(
            description=f"Alert closed automatically as {status_desc} due to case {case_human_id} closure",
            created_by=closed_by,
            created_at=now.isoformat(),
            timestamp=now.isoformat(),
            tags=["auto-close", "case-closure"],
        )
        timeline_service.add_timeline_item(alert, closure_note, created_by=closed_by)

        logger.info(f"Alert {alert.id} closed as {status_desc} due to case {case_human_id} closure")
        return True
    
    async def _close_linked_items(
        self,
        db: AsyncSession,
        case_id: int,
        closed_by: str,
        alert_closure_statuses: Optional[Dict[int, AlertStatus]] = None
    ) -> Dict[str, Any]:
        """
        Close all linked tasks and alerts when a case is closed.
        
        Args:
            db: Database session
            case_id: ID of the case being closed
            closed_by: Username of the user closing the case
            alert_closure_statuses: Optional dict mapping alert IDs to their desired closure statuses
        
        Returns a dictionary with closure results and any errors.
        """
        results = {
            "tasks_closed": 0,
            "alerts_closed": 0,
        }
        
        # Convert None to empty dict (avoid mutable default argument)
        alert_closure_statuses = alert_closure_statuses or {}
        
        tasks, alerts = await self._load_linked_items_for_update(db, case_id)

        case_human_id = format_entity_id(case_id, CASE_PREFIX)

        for task in tasks:
            if self._close_linked_task(task, case_human_id, closed_by):
                results["tasks_closed"] += 1

        for alert in alerts:
            custom_status = alert_closure_statuses.get(alert.id)
            if self._close_linked_alert(
                alert,
                case_human_id,
                closed_by,
                custom_status,
            ):
                results["alerts_closed"] += 1

        await db.flush()
        logger.info(
            "Case %s closure: closed %s tasks and %s alerts",
            case_id,
            results["tasks_closed"],
            results["alerts_closed"],
        )
        return results

    async def _load_linked_items_for_update(
        self,
        db: AsyncSession,
        case_id: int,
    ) -> tuple[list[Task], list[Alert]]:
        """Lock and refresh linked entities before a case closure mutates them."""
        task_result = await db.execute(
            select(Task)
            .where(Task.case_id == case_id)
            .order_by(Task.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        alert_result = await db.execute(
            select(Alert)
            .where(Alert.case_id == case_id)
            .order_by(Alert.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(task_result.scalars().all()), list(alert_result.scalars().all())

    def _build_alert_closure_status_map(
        self,
        alert_closure_updates: Optional[List[CaseAlertClosureUpdate]]
    ) -> Dict[int, AlertStatus]:
        """Normalize array-based alert closure updates into an alert_id -> status map."""
        if not alert_closure_updates:
            return {}

        closure_status_map: Dict[int, AlertStatus] = {}
        for alert_update in alert_closure_updates:
            closure_status_map[alert_update.alert_id] = alert_update.status

        return closure_status_map

    def _add_case_closure_summary_note(
        self,
        db_case: Case,
        closure_summary: Optional[str],
        closed_by: str,
    ) -> None:
        """Append an analyst-provided closure summary to the case timeline."""
        summary = (closure_summary or "").strip()
        if not summary:
            return

        closure_note = timeline_service.build_note_item(
            description=summary,
            created_by=closed_by,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tags=["case-closure"],
        )
        timeline_service.add_timeline_item(db_case, closure_note, created_by=closed_by)

    async def resolve_linked_alerts(
        self,
        db: AsyncSession,
        case_id: int,
        resolution: CaseLinkedAlertResolutionRequest,
        resolved_by: str,
    ) -> Optional[AlertBulkActionResponse]:
        """Apply selected closure statuses to selected open alerts linked to a case."""
        for alert_update in resolution.alert_updates:
            if alert_update.status not in CLOSED_ALERT_STATUSES:
                raise CaseValidationError("status must be a closed alert resolution")

        try:
            # Hold the parent lock before locking linked alerts. This matches
            # case closure/deletion and prevents parent-child lock inversions.
            if await self.lock_case_for_update(db, case_id) is None:
                return None

            result = await db.execute(
                select(Alert)
                .options(selectinload(Alert.triage_recommendation))  # type: ignore
                .where(Alert.case_id == case_id)
                .order_by(Alert.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            linked_alerts = list(result.scalars().all())
            linked_alerts_by_id = {
                alert.id: alert for alert in linked_alerts if alert.id is not None
            }
            requested_alert_ids = [update.alert_id for update in resolution.alert_updates]
            if len(set(requested_alert_ids)) != len(requested_alert_ids):
                raise CaseValidationError("alert_updates contains duplicate alerts")

            unknown_alert_ids = [
                alert_id
                for alert_id in requested_alert_ids
                if alert_id not in linked_alerts_by_id
            ]
            if unknown_alert_ids:
                raise CaseValidationError(
                    "alert_updates contains alerts not linked to this case"
                )

            changed_alert_ids: list[int] = []
            case_human_id = format_entity_id(case_id, CASE_PREFIX)

            for alert_update in resolution.alert_updates:
                alert = linked_alerts_by_id[alert_update.alert_id]
                if alert.status in CLOSED_ALERT_STATUSES:
                    raise CaseValidationError(
                        "alert_updates contains already closed alerts"
                    )

                before = self._alert_resolution_audit_snapshot(alert)
                apply_triage_state(
                    alert,
                    triaged_by=resolved_by,
                    status=alert_update.status,
                    triage_notes=resolution.note,
                    set_assignee=True,
                )
                alert.updated_at = datetime.now(timezone.utc)
                self._add_linked_alert_resolution_note(
                    alert, case_human_id, alert_update.status, resolution.note, resolved_by
                )

                await triage_recommendation_service.auto_reject_if_pending(
                    db, alert.id, resolved_by  # type: ignore[arg-type]
                )
                await self._audit_alert_resolution(db, alert, before, resolved_by)
                await emit_event(
                    db,
                    entity_type="alert",
                    entity_id=alert.id,  # type: ignore[arg-type]
                    event_type=RealtimeEventType.ENTITY_UPDATED,
                    performed_by=resolved_by,
                )
                if alert.id is not None:
                    changed_alert_ids.append(alert.id)

            committed_alerts = [
                linked_alerts_by_id[alert_id]
                for alert_id in changed_alert_ids
            ]
            fallback_response = self._linked_alert_resolution_response(
                committed_alerts,
                case_id,
                case_human_id,
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error resolving linked alerts for case {case_id}: {e}")
            raise

        return await load_committed_response(
            db,
            lambda: self._load_linked_alert_resolution_response(
                db,
                changed_alert_ids,
                case_id,
                case_human_id,
            ),
            fallback_response,
            logger=logger,
            entity_type="case",
            entity_id=case_id,
            operation="linked alert resolution",
        )

    @staticmethod
    def _alert_resolution_audit_snapshot(alert: Alert) -> dict[str, Any]:
        return {
            "status": alert.status,
            "assignee": alert.assignee,
            "triaged_at": alert.triaged_at,
            "triage_notes": alert.triage_notes,
        }

    async def _audit_alert_resolution(
        self,
        db: AsyncSession,
        alert: Alert,
        before: dict[str, Any],
        resolved_by: str,
    ) -> None:
        after = self._alert_resolution_audit_snapshot(alert)
        changed_before = {
            field: value for field, value in before.items() if value != after.get(field)
        }
        if not changed_before:
            return

        await get_audit_service(db).log_entity_updated(
            entity_type="alert",
            entity_id=alert.id,  # type: ignore[arg-type]
            before=changed_before,
            after={field: after.get(field) for field in changed_before},
            user=resolved_by,
        )

    @staticmethod
    def _add_linked_alert_resolution_note(
        alert: Alert,
        case_human_id: str,
        status: AlertStatus,
        note: Optional[str],
        resolved_by: str,
    ) -> None:
        status_desc = ALERT_STATUS_DESCRIPTIONS.get(
            status, status.value
        )
        description = (
            note
            or f"Alert resolved as {status_desc} during case {case_human_id} closure"
        )
        now = datetime.now(timezone.utc)
        timeline_service.add_timeline_item(
            alert,
            timeline_service.build_note_item(
                description=description,
                created_by=resolved_by,
                created_at=now.isoformat(),
                timestamp=now.isoformat(),
                tags=["bulk-action", "case-closure"],
            ),
            created_by=resolved_by,
        )

    async def _load_resolved_alerts(
        self,
        db: AsyncSession,
        alert_ids: list[int],
    ) -> list[Alert]:
        if not alert_ids:
            return []

        result = await db.execute(
            select(Alert)
            .options(selectinload(Alert.triage_recommendation))  # type: ignore
            .where(col(Alert.id).in_(alert_ids))
        )
        alerts_by_id = {alert.id: alert for alert in result.scalars().all()}
        return [
            alerts_by_id[alert_id]
            for alert_id in alert_ids
            if alert_id in alerts_by_id
        ]

    async def _load_linked_alert_resolution_response(
        self,
        db: AsyncSession,
        alert_ids: list[int],
        case_id: int,
        case_human_id: str,
    ) -> AlertBulkActionResponse:
        updated_alerts = await self._load_resolved_alerts(db, alert_ids)
        if len(updated_alerts) != len(alert_ids):
            raise RuntimeError("One or more resolved alerts could not be reloaded")
        return self._linked_alert_resolution_response(
            updated_alerts,
            case_id,
            case_human_id,
        )

    @staticmethod
    def _linked_alert_resolution_response(
        alerts: list[Alert],
        case_id: int,
        case_human_id: str,
    ) -> AlertBulkActionResponse:
        return AlertBulkActionResponse(
            updated_alerts=alerts,  # type: ignore[arg-type]
            updated_count=len(alerts),
            case_id=case_id,
            case_human_id=case_human_id,
        )
    
    async def delete_case(self, db: AsyncSession, case_id: int, deleted_by: str) -> bool:
        """Permanently delete a case after recording an audit snapshot."""
        try:
            db_case = await self.lock_case_for_update(db, case_id)
            if not db_case:
                return False

            await self._create_audit_log(
                db,
                case_id,
                "deleted",
                "Case permanently deleted",
                self._build_delete_audit_snapshot(db_case),
                None,
                deleted_by,
            )

            await db.delete(db_case)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting case {case_id}: {e}")
            raise

        logger.warning("Case %s permanently deleted by admin %s", case_id, deleted_by)
        return True

    @staticmethod
    def _truncate_audit_text(value: Optional[str], max_chars: int) -> Optional[str]:
        if value is None or len(value) <= max_chars:
            return value
        return value[:max_chars]

    def _build_delete_audit_snapshot(self, db_case: Case) -> dict[str, Any]:
        description = self._truncate_audit_text(
            db_case.description,
            CASE_DELETE_AUDIT_DESCRIPTION_MAX_CHARS,
        )
        tags = list(db_case.tags or [])
        sampled_tags = [
            self._truncate_audit_text(str(tag), CASE_DELETE_AUDIT_TAG_MAX_CHARS)
            for tag in tags[:CASE_DELETE_AUDIT_MAX_TAGS]
        ]

        return {
            "id": db_case.id,
            "title": db_case.title,
            "description": description,
            "description_length": len(db_case.description or ""),
            "description_truncated": bool(
                db_case.description
                and len(db_case.description) > CASE_DELETE_AUDIT_DESCRIPTION_MAX_CHARS
            ),
            "status": db_case.status,
            "priority": db_case.priority,
            "assignee": db_case.assignee,
            "created_by": db_case.created_by,
            "tags": sampled_tags,
            "tags_count": len(tags),
            "tags_truncated": len(tags) > CASE_DELETE_AUDIT_MAX_TAGS,
        }
    
    async def add_timeline_item(
        self, 
        db: AsyncSession, 
        case_id: int, 
        timeline_item: CaseTimelineItem, 
        created_by: str,
        created_at_override: Optional[datetime] = None,
        preserve_item_id: bool = False,
        idempotent: bool = False,
    ) -> Optional[Case]:
        """Add a timeline item to a case."""
        try:
            committed_case = await self._get_case_model(db, case_id)
            if committed_case is None:
                return None
            added_item = await add_timeline_item_and_commit(
                db,
                entity_id=case_id,
                entity_type="case",
                timeline_item=timeline_item,
                performed_by=created_by,
                created_at_override=created_at_override,
                preserve_item_id=preserve_item_id,
                idempotent=idempotent,
            )
            if added_item is None:
                return None
        except TimelineValidationError as exc:
            await db.rollback()
            raise CaseValidationError(str(exc)) from exc
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding timeline item to case {case_id}: {e}")
            raise

        logger.info(f"Timeline item added to case by {created_by}")
        return await load_committed_response(
            db,
            lambda: self._load_timeline_mutation_response(db, case_id),
            committed_case,
            logger=logger,
            entity_type="case",
            entity_id=case_id,
            operation="timeline item addition",
        )
    
    async def update_timeline_item(
        self, 
        db: AsyncSession, 
        case_id: int, 
        item_id: str, 
        timeline_item: CaseTimelineItem, 
        updated_by: str,
        companion_timeline_item: CaseTimelineItem | None = None,
        expected_item_fields: dict[str, Any] | None = None,
    ) -> Optional[Case]:
        """Update a timeline item in a case."""
        try:
            committed_case = await self._get_case_model(db, case_id)
            if committed_case is None:
                return None
            updated_item = await update_timeline_item_and_commit(
                db,
                entity_id=case_id,
                entity_type="case",
                item_id=item_id,
                timeline_item=timeline_item,
                performed_by=updated_by,
                companion_timeline_item=companion_timeline_item,
                expected_item_fields=expected_item_fields,
            )

            if updated_item is None:
                return None
        except TimelineValidationError as exc:
            await db.rollback()
            raise CaseValidationError(str(exc)) from exc
        except TimelineItemConflict:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating timeline item {item_id} in case {case_id}: {e}")
            raise

        logger.info(f"Timeline item {item_id} updated in case by {updated_by}")
        return await load_committed_response(
            db,
            lambda: self._load_timeline_mutation_response(db, case_id),
            committed_case,
            logger=logger,
            entity_type="case",
            entity_id=case_id,
            operation="timeline item update",
        )
    
    async def remove_timeline_item(
        self, 
        db: AsyncSession, 
        case_id: int, 
        item_id: str, 
        deleted_by: str
    ) -> Optional[Case]:
        """Remove a timeline item from a case and clean up associated resources."""
        try:
            committed_case = await self._get_case_model(db, case_id)
            if committed_case is None:
                return None
            removed_item = await remove_timeline_item_and_commit(
                db,
                entity_id=case_id,
                entity_type="case",
                item_id=item_id,
                performed_by=deleted_by,
            )
            if removed_item is None:
                return None
        except TimelineValidationError as exc:
            await db.rollback()
            raise CaseValidationError(str(exc)) from exc
        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting timeline item {item_id} from case {case_id}: {e}")
            raise

        logger.info(f"Timeline item {item_id} deleted from case by {deleted_by}")
        return await load_committed_response(
            db,
            lambda: self._load_timeline_mutation_response(db, case_id),
            committed_case,
            logger=logger,
            entity_type="case",
            entity_id=case_id,
            operation="timeline item removal",
        )
    
    async def _create_audit_log(
        self,
        db: AsyncSession,
        case_id: int,
        action: str,
        description: str,
        old_value: Any,
        new_value: Any,
        performed_by: str
    ) -> None:
        """Create an audit log entry."""
        event_type_map = {
            "created": "case.created",
            "deleted": "case.deleted",
            "linked_items_closed": "case.linked_items_closed",
            "status_changed": "case.status_changed",
            "priority_changed": "case.priority_changed",
            "assignee_changed": "case.assignee_changed",
            "title_changed": "case.title_changed",
            "description_changed": "case.description_changed",
            "tags_changed": "case.tags_changed",
        }
        event_type = event_type_map.get(action, f"case.{action}")
        await get_audit_service(db).log_event(
            event_type=event_type,
            entity_type="case",
            entity_id=str(case_id),
            description=description,
            old_value=old_value,
            new_value=new_value,
            performed_by=performed_by,
        )


case_service = CaseService()
