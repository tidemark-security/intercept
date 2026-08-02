from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, String
from sqlalchemy.orm import selectinload, defer
from sqlmodel import col
from typing import Callable, List, Optional, Dict, Any
from datetime import datetime, timezone
import logging
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate

from app.core.entity_ids import ALERT_PREFIX, CASE_PREFIX, format_entity_id
from app.models.models import (
    Alert, Case,
    AlertCreate, AlertUpdate, AlertTriageRequest,
    AlertBulkActionRequest, AlertBulkActionResponse,
    AlertTimelineItem,
)
from app.models.enums import AlertStatus, Priority, TriageDisposition, RealtimeEventType
from app.services.case_service import case_service
from app.services.alert_triage_apply_service import (
    apply_triage_state,
    create_case_from_alert,
    is_triage_completion_status,
    mark_alert_escalated,
)
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
    merge_persisted_tags,
    normalize_persisted_tags,
    validate_protected_tag_mutation,
)
from app.services.committed_response import (
    detach_committed_state,
    load_committed_response,
    reset_post_commit_session,
)

logger = logging.getLogger(__name__)


class AlertValidationError(ValueError):
    """An alert operation violates a client-facing domain rule."""


class AlertRelatedEntityNotFoundError(AlertValidationError):
    """An entity referenced by an alert operation does not exist."""


_ALERT_STATUS_CHANGE_DESCRIPTIONS: Dict[AlertStatus, str] = {
    AlertStatus.NEW: "Alert status changed to New",
    AlertStatus.IN_PROGRESS: "Alert status changed to In Progress",
    AlertStatus.ESCALATED: "Alert status changed to Escalated",
    AlertStatus.CLOSED_TP: "Alert closed as True Positive",
    AlertStatus.CLOSED_BP: "Alert closed as True Positive Benign",
    AlertStatus.CLOSED_FP: "Alert closed as False Positive",
    AlertStatus.CLOSED_UNRESOLVED: "Alert closed as Unresolved",
    AlertStatus.CLOSED_DUPLICATE: "Alert closed as Duplicate",
}


def _status_change_description(status: AlertStatus) -> str:
    return _ALERT_STATUS_CHANGE_DESCRIPTIONS.get(
        status,
        f"Alert status changed to {status}",
    )


@dataclass(slots=True)
class _BulkActionContext:
    status: Optional[AlertStatus] = None
    target_alert: Optional[Alert] = None
    created_case: Optional[Case] = None


_BulkActionHandler = Callable[[Alert, AlertBulkActionRequest, _BulkActionContext, str], None]


class AlertService:
    
    async def create_alert(
        self, 
        db: AsyncSession, 
        alert_data: AlertCreate,
        created_at_override: Optional[datetime] = None,
    ) -> Alert:
        """Create a new alert.
        
        If AI triage is enabled (langflow.alert_triage_flow_id is set) and
        auto-enqueue is enabled (triage.auto_enqueue is True or unset),
        automatically enqueues the alert for AI triage.
        """
        try:
            alert_kwargs = {
                "title": alert_data.title,
                "description": alert_data.description,
                "priority": alert_data.priority,
                "source": alert_data.source,
            }
            if created_at_override is not None:
                alert_kwargs["created_at"] = created_at_override

            db_alert = Alert(**alert_kwargs)
            # Keep the post-commit fallback response-safe if its richer reload
            # fails and the session must be rolled back and detached.
            db_alert.triage_recommendation = None
            
            db.add(db_alert)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating alert: {e}")
            raise

        logger.info("Alert created")
        alert_id = db_alert.id  # type: ignore[assignment]
        await detach_committed_state(db, logger)
        await self._auto_enqueue_triage(db, alert_id)
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            db_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="creation",
        )
    
    async def _auto_enqueue_triage(self, db: AsyncSession, alert_id: int):
        """Auto-enqueue alert for AI triage if enabled.
        
        Checks both langflow.alert_triage_flow_id and triage.auto_enqueue settings.
        Fails silently if triage is not enabled or task queue is unavailable.
        """
        from app.services.settings_service import SettingsService
        try:
            settings = SettingsService(db)  # type: ignore[arg-type]
            
            # Check if triage flow is configured
            flow_id = await settings.get("langflow.alert_triage_flow_id")
            if not flow_id:
                logger.debug(f"AI triage not enabled - skipping auto-enqueue for alert {alert_id}")
                return
            
            # Check if auto-enqueue is enabled (defaults to False)
            auto_enqueue = await settings.get("triage.auto_enqueue")
            if auto_enqueue is not True:
                logger.debug(f"Auto-enqueue disabled - skipping for alert {alert_id}")
                return
            
            await triage_recommendation_service.enqueue_triage(
                db,
                alert_id,
                enqueued_by="system",
            )
            logger.info("Auto-enqueued AI triage for alert %s", alert_id)
                
        except Exception as e:
            # Don't fail alert creation if triage enqueue fails
            await reset_post_commit_session(db, logger)
            logger.warning("Auto-enqueue triage failed for alert %s: %s", alert_id, e)
    
    async def _get_alert_model(self, db: AsyncSession, alert_id: int) -> Optional[Alert]:
        """Get the tracked alert model with related entities loaded."""
        query = (
            select(Alert)
            .options(
                selectinload(Alert.case),  # type: ignore
                selectinload(Alert.triage_recommendation)  # type: ignore
            )
            .where(Alert.id == alert_id)  # type: ignore
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _get_alert_for_update(
        self,
        db: AsyncSession,
        alert_id: int,
    ) -> Optional[Alert]:
        """Lock and refresh an alert before mutating it."""
        result = await db.execute(
            select(Alert)
            .options(
                selectinload(Alert.case),  # type: ignore
                selectinload(Alert.triage_recommendation),  # type: ignore
            )
            .where(Alert.id == alert_id)  # type: ignore
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_alert(self, db: AsyncSession, alert_id: int, include_linked_timelines: bool = False) -> Optional[Alert]:
        """Get alert by ID with case and triage_recommendation relationships.
        
        Args:
            db: Database session
            alert_id: Alert ID
            include_linked_timelines: If True, case and task timeline items will include
                source_timeline_items from the linked entity
        """
        db_alert = await self._get_alert_model(db, alert_id)
        if not db_alert:
            return None

        prepared_alert = await timeline_service.prepare_entity_detail_timeline(
            db,
            entity_type="alert",
            entity_id=alert_id,
            entity=db_alert,
            human_prefix=ALERT_PREFIX,
            include_linked_timelines=include_linked_timelines,
        )

        from app.services.context_service import ContextService

        context_items = await ContextService(db).get_matching_context_for_alert(alert_id)
        object.__setattr__(
            prepared_alert,
            "context",
            {
                "items": context_items,
                "total_count": len(context_items),
                "omitted_count": 0,
            },
        )
        return prepared_alert
    
    async def get_alerts(
        self, 
        db: AsyncSession, 
        status: Optional[List[AlertStatus]] = None,
        assignee: Optional[List[str]] = None,
        case_id: Optional[int] = None,
        priority: Optional[List[Priority]] = None,
        source: Optional[str] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        has_case: Optional[bool] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Page[Alert]:
        """Get alerts with comprehensive filtering and pagination.
        
        Args:
            start_date: UTC ISO8601 string (e.g., "2025-10-20T14:30:00Z") - filter alerts created after this time
            end_date: UTC ISO8601 string (e.g., "2025-10-20T18:30:00Z") - filter alerts created before this time
            assignee: Filter by multiple assignee usernames (exact match, OR logic)
            search: Search string to match against alert ID, title, or description (case-insensitive partial match)
        """
        # Defer timeline_items because list responses do not need the potentially
        # malformed legacy JSON that detail views normalize separately.
        query = select(Alert).options(
            selectinload(Alert.case),  # type: ignore
            selectinload(Alert.triage_recommendation),  # type: ignore
            defer(Alert.timeline_items),  # type: ignore[arg-type]
        )
        filters = []
        if status:
            filters.append(Alert.status.in_(status))  # type: ignore
        if assignee:
            unassigned_requested = "__unassigned__" in assignee
            regular_assignees = [
                username for username in assignee if username != "__unassigned__"
            ]
            if unassigned_requested and regular_assignees:
                filters.append(
                    or_(
                        Alert.assignee.is_(None),  # type: ignore
                        Alert.assignee.in_(regular_assignees),  # type: ignore
                    )
                )
            elif unassigned_requested:
                filters.append(Alert.assignee.is_(None))  # type: ignore
            elif regular_assignees:
                filters.append(Alert.assignee.in_(regular_assignees))  # type: ignore
        if case_id:
            filters.append(Alert.case_id == case_id)
        if priority:
            filters.append(Alert.priority.in_(priority))  # type: ignore
        if source:
            filters.append(Alert.source.ilike(f"%{source}%"))  # type: ignore
        append_tag_filters(filters, Alert.tags, include_tags, exclude_tags)
        if has_case is not None:
            filters.append(
                Alert.case_id.is_not(None)  # type: ignore
                if has_case
                else Alert.case_id.is_(None)  # type: ignore
            )

        try:
            start_dt = parse_datetime_filter(start_date, parameter="start_date")
            end_dt = parse_datetime_filter(end_date, parameter="end_date")
        except DateFilterValidationError as exc:
            raise AlertValidationError(str(exc)) from exc

        if start_dt is not None:
            filters.append(Alert.created_at >= start_dt)  # type: ignore
        if end_dt is not None:
            filters.append(Alert.created_at <= end_dt)  # type: ignore
        if search:
            search_pattern = f"%{search}%"
            filters.append(
                or_(
                    cast(Alert.id, String).ilike(search_pattern),  # type: ignore
                    Alert.title.ilike(search_pattern),  # type: ignore
                    Alert.description.ilike(search_pattern),  # type: ignore
                )
            )
        if filters:
            query = query.where(*filters)

        allowed_sort_columns = {
            "id": Alert.id,
            "title": Alert.title,
            "status": Alert.status,
            "priority": Alert.priority,
            "source": Alert.source,
            "assignee": Alert.assignee,
            "created_at": Alert.created_at,
            "updated_at": Alert.updated_at,
        }
        try:
            sort_column = allowed_sort_columns[sort_by]
        except KeyError as exc:
            raise AlertValidationError(
                f"Unsupported alert sort column: {sort_by}"
            ) from exc
        ordering = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()
        return await apaginate(db, query.order_by(ordering))

    async def update_alert(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        alert_update: AlertUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[Alert]:
        """Update an alert."""
        try:
            db_alert = await self._get_alert_for_update(db, alert_id)
            if not db_alert:
                return None
            
            # Track status changes for timeline
            old_status = db_alert.status
            status_changed = False
            new_status = None
            
            update_data = alert_update.model_dump(exclude_unset=True)
            # Capture original values before mutating for audit logging
            original_values = {field: getattr(db_alert, field, None) for field in update_data if hasattr(db_alert, field)}
            for field, value in update_data.items():
                if hasattr(db_alert, field):
                    if field == "tags":
                        try:
                            value = validate_protected_tag_mutation(db_alert.tags, value)
                        except ProtectedTagMutationError as exc:
                            raise AlertValidationError(str(exc)) from exc
                    if field == 'status' and value != old_status:
                        status_changed = True
                        new_status = value
                    setattr(db_alert, field, value)
            
            # Update the updated_at timestamp
            db_alert.updated_at = datetime.now(timezone.utc)
            
            # Add timeline item for status changes
            if status_changed and updated_by:
                description = _status_change_description(db_alert.status)
                
                # Create a note timeline item for the status change
                now = datetime.now(timezone.utc)
                status_change_item = timeline_service.build_note_item(
                    description=description,
                    created_by=updated_by,
                    created_at=now.isoformat(),
                    timestamp=now.isoformat(),
                    tags=["status-change"],
                )
                
                timeline_service.add_timeline_item(db_alert, status_change_item, created_by=updated_by)
                
                if is_triage_completion_status(new_status):
                    apply_triage_state(
                        db_alert,
                        triaged_by=updated_by,
                        set_assignee=True,
                    )
                    await triage_recommendation_service.auto_reject_if_pending(
                        db, alert_id, updated_by
                    )
            
            # Audit log all field-level changes
            if updated_by and update_data:
                audit_changes = [
                    {"field": field, "before": original_values.get(field), "after": value}
                    for field, value in update_data.items()
                    if field in original_values and original_values.get(field) != value
                ]
                if audit_changes:
                    await get_audit_service(db).log_entity_updated(
                        entity_type="alert",
                        entity_id=alert_id,
                        before={field: original_values.get(field) for field in update_data},
                        after={field: getattr(db_alert, field, None) for field in update_data},
                        user=updated_by,
                    )

            await emit_event(
                db,
                entity_type="alert",
                entity_id=alert_id,
                event_type=RealtimeEventType.ENTITY_UPDATED,
                performed_by=updated_by or "system",
            )

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating alert {alert_id}: {e}")
            raise

        logger.info("Alert updated")
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            db_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="update",
        )
    
    async def triage_alert(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        triage_request: AlertTriageRequest,
        triaged_by: str
    ) -> Optional[Alert]:
        """Triage an alert and optionally escalate to case."""
        try:
            db_alert = await self._get_alert_for_update(db, alert_id)
            if not db_alert:
                return None
            
            apply_triage_state(
                db_alert,
                triaged_by=triaged_by,
                status=triage_request.status,
                triage_notes=triage_request.triage_notes,
                set_assignee=True,
            )

            await triage_recommendation_service.auto_reject_if_pending(
                db, alert_id, triaged_by
            )
            
            # If escalating to case, create a new case
            if triage_request.escalate_to_case:
                if db_alert.case_id:
                    raise AlertValidationError(
                        "Alert is already escalated to a case"
                    )

                new_case = await create_case_from_alert(
                    db,
                    alert=db_alert,
                    created_by=triaged_by,
                    title=triage_request.case_title,
                    description=triage_request.case_description,
                    assignee=triaged_by,
                )

                # Link alert to case
                mark_alert_escalated(db_alert, case_id=new_case.id)  # type: ignore[arg-type]
                
                logger.info(f"Alert escalated to case {new_case.id}")
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error triaging alert {alert_id}: {e}")
            raise

        logger.info(f"Alert triaged by {triaged_by}")
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            db_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="triage",
        )
    
    async def link_alert_to_case(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        case_id: int,
        linked_by: str
    ) -> Optional[Alert]:
        """Link an existing alert to an existing case."""
        try:
            # Preserve the existing not-found behavior without taking the child
            # lock before its parent. The locked reload below is authoritative.
            if await self._get_alert_model(db, alert_id) is None:
                return None

            db_case = await self._lock_required_case(db, case_id)
            db_alert = await self._get_alert_for_update(db, alert_id)
            if not db_alert:
                return None
            
            # Link alert to case
            apply_triage_state(
                db_alert,
                triaged_by=linked_by,
                set_assignee=True,
            )
            mark_alert_escalated(db_alert, case_id=case_id)
            await triage_recommendation_service.auto_reject_if_pending(
                db, alert_id, linked_by
            )
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error linking alert {alert_id} to case {case_id}: {e}")
            raise

        logger.info(
            "Alert linked to case %s by %s",
            format_entity_id(db_case.id, CASE_PREFIX),
            linked_by,
        )
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            db_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="case link",
        )

    async def bulk_action(
        self,
        db: AsyncSession,
        request: AlertBulkActionRequest,
        performed_by: str,
    ) -> AlertBulkActionResponse:
        """Apply one supported bulk action to selected alerts."""
        try:
            alert_ids = self._deduplicate_alert_ids(request.alert_ids)
            locked_link_case = (
                await self._lock_required_case(db, request.case_id)
                if request.action == "link_case"
                else None
            )
            ordered_alerts = await self._load_alerts_for_bulk_action(db, alert_ids)
            context = await self._prepare_bulk_action(
                db,
                request,
                ordered_alerts,
                alert_ids,
                performed_by,
                locked_link_case=locked_link_case,
            )

            await self._apply_bulk_action_to_alerts(
                db, ordered_alerts, request, context, performed_by
            )
            fallback_response = self._bulk_action_response(ordered_alerts, context)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error applying bulk alert action {request.action}: {e}")
            raise

        return await load_committed_response(
            db,
            lambda: self._build_bulk_action_response(db, alert_ids, context),
            fallback_response,
            logger=logger,
            entity_type="alert batch",
            entity_id=alert_ids,
            operation=request.action,
        )

    @staticmethod
    def _deduplicate_alert_ids(alert_ids: List[int]) -> List[int]:
        return list(dict.fromkeys(alert_ids))

    async def _load_alerts_for_bulk_action(
        self,
        db: AsyncSession,
        alert_ids: List[int],
    ) -> List[Alert]:
        result = await db.execute(
            select(Alert)
            .options(selectinload(Alert.triage_recommendation))  # type: ignore
            .where(col(Alert.id).in_(alert_ids))
            .order_by(Alert.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        alerts = list(result.scalars().all())
        alerts_by_id = {alert.id: alert for alert in alerts}
        missing_ids = [alert_id for alert_id in alert_ids if alert_id not in alerts_by_id]
        if missing_ids:
            missing_list = ", ".join(str(item) for item in missing_ids)
            raise AlertValidationError(f"Alert(s) not found: {missing_list}")
        return [alerts_by_id[alert_id] for alert_id in alert_ids]

    async def _prepare_bulk_action(
        self,
        db: AsyncSession,
        request: AlertBulkActionRequest,
        alerts: List[Alert],
        alert_ids: List[int],
        performed_by: str,
        *,
        locked_link_case: Optional[Case],
    ) -> _BulkActionContext:
        context = _BulkActionContext(status=self._resolve_bulk_update_status(request))

        if request.action == "link_case":
            if locked_link_case is None:
                raise RuntimeError("Bulk case link requires a locked destination case")
            self._ensure_alerts_can_link_to_case(alerts, request.case_id)

        if request.action == "create_case":
            context.created_case = await self._create_case_for_bulk_action(
                db, request, alerts, alert_ids, performed_by
            )

        if self._bulk_action_closes_duplicate(request, context):
            await self._load_bulk_duplicate_targets(db, request, alert_ids, context)

        return context

    @staticmethod
    def _resolve_bulk_update_status(request: AlertBulkActionRequest) -> Optional[AlertStatus]:
        if request.action != "update_status":
            return None
        return request.status or AlertService._status_from_disposition(request.disposition)

    async def _create_case_for_bulk_action(
        self,
        db: AsyncSession,
        request: AlertBulkActionRequest,
        alerts: List[Alert],
        alert_ids: List[int],
        performed_by: str,
    ) -> Case:
        self._ensure_alerts_can_link_to_case(alerts, None)
        case = await create_case_from_alert(
            db,
            alert=alerts[0],
            created_by=performed_by,
            title=request.case_title,
            description=request.case_description
            if request.case_description is not None
            else self._build_bulk_case_description(alerts),
            assignee=performed_by,
        )
        await get_audit_service(db).log_event(
            event_type="case.created",
            entity_type="case",
            entity_id=str(case.id),
            description="Case created from bulk alert selection",
            new_value={
                "title": case.title,
                "alert_ids": alert_ids,
            },
            performed_by=performed_by,
        )
        return case

    async def _get_required_case(
        self,
        db: AsyncSession,
        case_id: Optional[int],
    ) -> Case:
        if case_id is None:
            raise AlertValidationError("case_id is required")
        case = await case_service.get_case(db, case_id)
        if not case:
            raise AlertRelatedEntityNotFoundError(f"Case {case_id} not found")
        return case

    async def _lock_required_case(
        self,
        db: AsyncSession,
        case_id: Optional[int],
    ) -> Case:
        if case_id is None:
            raise AlertValidationError("case_id is required")
        case = await case_service.lock_case_for_update(db, case_id)
        if case is None:
            raise AlertRelatedEntityNotFoundError(f"Case {case_id} not found")
        return case

    async def _get_required_alert(
        self,
        db: AsyncSession,
        alert_id: Optional[int],
    ) -> Alert:
        if alert_id is None:
            raise AlertValidationError("alert_id is required")
        alert = await self._get_alert_model(db, alert_id)
        if not alert:
            raise AlertRelatedEntityNotFoundError(f"Alert {alert_id} not found")
        return alert

    @staticmethod
    def _bulk_action_closes_duplicate(
        request: AlertBulkActionRequest,
        context: _BulkActionContext,
    ) -> bool:
        return request.action == "close_duplicate" or context.status == AlertStatus.CLOSED_DUPLICATE

    async def _load_bulk_duplicate_targets(
        self,
        db: AsyncSession,
        request: AlertBulkActionRequest,
        alert_ids: List[int],
        context: _BulkActionContext,
    ) -> None:
        if request.duplicate_target_case_id is not None:
            await self._get_required_case(db, request.duplicate_target_case_id)

        if request.duplicate_target_alert_id is None:
            return

        if request.duplicate_target_alert_id in alert_ids:
            raise AlertValidationError(
                "Duplicate target alert cannot be one of the selected alerts"
            )
        context.target_alert = await self._get_required_alert(db, request.duplicate_target_alert_id)

    async def _apply_bulk_action_to_alerts(
        self,
        db: AsyncSession,
        alerts: List[Alert],
        request: AlertBulkActionRequest,
        context: _BulkActionContext,
        performed_by: str,
    ) -> None:
        handler = self._bulk_action_handler(request.action)
        should_auto_reject = self._bulk_action_should_auto_reject(request, context)

        for alert in alerts:
            before = self._bulk_audit_snapshot(alert)
            handler(alert, request, context, performed_by)

            if should_auto_reject:
                await triage_recommendation_service.auto_reject_if_pending(
                    db, alert.id, performed_by  # type: ignore[arg-type]
                )
            await self._audit_bulk_alert_update(db, alert, before, performed_by)
            await emit_event(
                db,
                entity_type="alert",
                entity_id=alert.id,  # type: ignore[arg-type]
                event_type=RealtimeEventType.ENTITY_UPDATED,
                performed_by=performed_by,
            )

    def _bulk_action_handler(self, action: str) -> _BulkActionHandler:
        handlers: Dict[str, _BulkActionHandler] = {
            "update_status": self._apply_bulk_status_update,
            "link_case": self._apply_bulk_existing_case_link,
            "create_case": self._apply_bulk_created_case_link,
            "close_duplicate": self._apply_bulk_duplicate_close,
            "add_tags": self._apply_bulk_tags,
            "assign": self._apply_bulk_assign,
        }
        return handlers[action]

    @staticmethod
    def _bulk_action_should_auto_reject(
        request: AlertBulkActionRequest,
        context: _BulkActionContext,
    ) -> bool:
        if request.action in {"link_case", "create_case", "close_duplicate"}:
            return True
        return request.action == "update_status" and is_triage_completion_status(context.status)

    def _apply_bulk_status_update(
        self,
        alert: Alert,
        request: AlertBulkActionRequest,
        context: _BulkActionContext,
        performed_by: str,
    ) -> None:
        if context.status is None:
            raise AlertValidationError(
                "status or disposition is required for update_status"
            )

        if context.status == AlertStatus.CLOSED_DUPLICATE:
            self._link_alert_to_duplicate_target(alert, request, context)

        self._set_alert_status_for_bulk(
            alert,
            context.status,
            performed_by,
            self._bulk_status_note(request, context.status),
        )

    def _apply_bulk_existing_case_link(
        self,
        alert: Alert,
        request: AlertBulkActionRequest,
        _context: _BulkActionContext,
        performed_by: str,
    ) -> None:
        if request.case_id is None:
            raise AlertValidationError("case_id is required for link_case")
        self._link_alert_to_case(
            alert,
            request.case_id,
            performed_by,
            f"Bulk linked alert to case {format_entity_id(request.case_id, CASE_PREFIX)}",
        )

    def _apply_bulk_created_case_link(
        self,
        alert: Alert,
        _request: AlertBulkActionRequest,
        context: _BulkActionContext,
        performed_by: str,
    ) -> None:
        if context.created_case is None or context.created_case.id is None:
            raise AlertValidationError("created case is required for create_case")
        self._link_alert_to_case(
            alert,
            context.created_case.id,
            performed_by,
            f"Bulk linked alert to new case {format_entity_id(context.created_case.id, CASE_PREFIX)}",
        )

    def _apply_bulk_duplicate_close(
        self,
        alert: Alert,
        request: AlertBulkActionRequest,
        context: _BulkActionContext,
        performed_by: str,
    ) -> None:
        self._link_alert_to_duplicate_target(alert, request, context)
        self._set_alert_status_for_bulk(
            alert,
            AlertStatus.CLOSED_DUPLICATE,
            performed_by,
            self._duplicate_note(request),
        )

    def _apply_bulk_tags(
        self,
        alert: Alert,
        request: AlertBulkActionRequest,
        _context: _BulkActionContext,
        _performed_by: str,
    ) -> None:
        next_tags = merge_persisted_tags(alert.tags, request.tags)
        try:
            alert.tags = validate_protected_tag_mutation(alert.tags, next_tags)
        except ProtectedTagMutationError as exc:
            raise AlertValidationError(str(exc)) from exc
        alert.updated_at = datetime.now(timezone.utc)

    def _apply_bulk_assign(
        self,
        alert: Alert,
        request: AlertBulkActionRequest,
        _context: _BulkActionContext,
        performed_by: str,
    ) -> None:
        if not request.assignee:
            raise AlertValidationError("assignee is required for assign")
        alert.assignee = request.assignee
        if alert.status == AlertStatus.NEW:
            alert.status = AlertStatus.IN_PROGRESS
        alert.updated_at = datetime.now(timezone.utc)
        self._add_bulk_note(
            alert,
            performed_by,
            f"Bulk assigned alert to {request.assignee}",
            ["bulk-action", "assignment"],
        )

    @staticmethod
    def _link_alert_to_case(
        alert: Alert,
        case_id: int,
        performed_by: str,
        note: str,
    ) -> None:
        apply_triage_state(alert, triaged_by=performed_by, set_assignee=True)
        mark_alert_escalated(alert, case_id=case_id)
        AlertService._add_bulk_note(
            alert,
            performed_by,
            note,
            ["bulk-action", "case-link"],
        )

    @staticmethod
    def _link_alert_to_duplicate_target(
        alert: Alert,
        request: AlertBulkActionRequest,
        context: _BulkActionContext,
    ) -> None:
        linked_case_id = request.duplicate_target_case_id or (
            context.target_alert.case_id if context.target_alert else None
        )
        if linked_case_id is None:
            return
        alert.case_id = linked_case_id
        alert.linked_at = datetime.now(timezone.utc)

    @staticmethod
    def _bulk_status_note(
        request: AlertBulkActionRequest,
        status: AlertStatus,
    ) -> Optional[str]:
        if status != AlertStatus.CLOSED_DUPLICATE:
            return request.note
        return AlertService._duplicate_note(request)

    @staticmethod
    def _duplicate_note(request: AlertBulkActionRequest) -> str:
        return request.note or AlertService._duplicate_description(
            request.duplicate_target_case_id,
            request.duplicate_target_alert_id,
        )

    async def _build_bulk_action_response(
        self,
        db: AsyncSession,
        alert_ids: List[int],
        context: _BulkActionContext,
    ) -> AlertBulkActionResponse:
        updated_alerts: List[Alert] = []
        for alert_id in alert_ids:
            updated_alert = await self.get_alert(db, alert_id)
            if updated_alert is not None:
                updated_alerts.append(updated_alert)

        if len(updated_alerts) != len(alert_ids):
            raise RuntimeError("One or more committed alerts could not be reloaded")

        return self._bulk_action_response(updated_alerts, context)

    @staticmethod
    def _bulk_action_response(
        updated_alerts: List[Alert],
        context: _BulkActionContext,
    ) -> AlertBulkActionResponse:
        case_id = context.created_case.id if context.created_case is not None else None
        return AlertBulkActionResponse(
            updated_alerts=updated_alerts,  # type: ignore[arg-type]
            updated_count=len(updated_alerts),
            case_id=case_id,
            case_human_id=(
                format_entity_id(case_id, CASE_PREFIX)
                if case_id is not None
                else None
            ),
        )

    @staticmethod
    def _ensure_alerts_can_link_to_case(alerts: List[Alert], case_id: Optional[int]) -> None:
        for alert in alerts:
            if alert.case_id is not None and alert.case_id != case_id:
                raise AlertValidationError(
                    f"Alert {format_entity_id(alert.id, ALERT_PREFIX)} is already linked "
                    f"to case {format_entity_id(alert.case_id, CASE_PREFIX)}"
                )

    @staticmethod
    def _bulk_audit_snapshot(alert: Alert) -> Dict[str, Any]:
        return {
            "status": alert.status,
            "assignee": alert.assignee,
            "triaged_at": alert.triaged_at,
            "triage_notes": alert.triage_notes,
            "case_id": alert.case_id,
            "linked_at": alert.linked_at,
            "tags": list(alert.tags or []),
        }

    async def _audit_bulk_alert_update(
        self,
        db: AsyncSession,
        alert: Alert,
        before: Dict[str, Any],
        performed_by: str,
    ) -> None:
        after = self._bulk_audit_snapshot(alert)
        changed_before = {
            field: value for field, value in before.items() if value != after.get(field)
        }
        changed_after = {
            field: after.get(field) for field in changed_before
        }
        if not changed_before:
            return

        await get_audit_service(db).log_entity_updated(
            entity_type="alert",
            entity_id=alert.id,  # type: ignore[arg-type]
            before=changed_before,
            after=changed_after,
            user=performed_by,
        )

    def _set_alert_status_for_bulk(
        self,
        alert: Alert,
        status: AlertStatus,
        performed_by: str,
        note: Optional[str] = None,
    ) -> None:
        if is_triage_completion_status(status):
            apply_triage_state(
                alert,
                triaged_by=performed_by,
                status=status,
                triage_notes=note,
                set_assignee=True,
            )
        else:
            alert.status = status
        alert.updated_at = datetime.now(timezone.utc)
        description = note or self._status_description(status)
        self._add_bulk_note(alert, performed_by, description, ["bulk-action", "status-change"])

    @staticmethod
    def _status_description(status: AlertStatus) -> str:
        descriptions = {
            AlertStatus.NEW: "Bulk changed alert status to New",
            AlertStatus.IN_PROGRESS: "Bulk changed alert status to In Progress",
            AlertStatus.ESCALATED: "Bulk changed alert status to Escalated",
            AlertStatus.CLOSED_TP: "Bulk closed alert as True Positive",
            AlertStatus.CLOSED_BP: "Bulk closed alert as Benign Positive",
            AlertStatus.CLOSED_FP: "Bulk closed alert as False Positive",
            AlertStatus.CLOSED_UNRESOLVED: "Bulk closed alert as Unresolved",
            AlertStatus.CLOSED_DUPLICATE: "Bulk closed alert as Duplicate",
        }
        return descriptions.get(status, f"Bulk changed alert status to {status.value}")

    @staticmethod
    def _status_from_disposition(disposition: Optional[TriageDisposition]) -> AlertStatus:
        disposition_statuses = {
            TriageDisposition.TRUE_POSITIVE: AlertStatus.CLOSED_TP,
            TriageDisposition.BENIGN: AlertStatus.CLOSED_BP,
            TriageDisposition.FALSE_POSITIVE: AlertStatus.CLOSED_FP,
            TriageDisposition.DUPLICATE: AlertStatus.CLOSED_DUPLICATE,
            TriageDisposition.NEEDS_INVESTIGATION: AlertStatus.IN_PROGRESS,
            TriageDisposition.UNKNOWN: AlertStatus.CLOSED_UNRESOLVED,
        }
        if disposition not in disposition_statuses:
            raise AlertValidationError("Unsupported disposition for status update")
        return disposition_statuses[disposition]

    @staticmethod
    def _add_bulk_note(
        alert: Alert,
        performed_by: str,
        description: str,
        tags: List[str],
    ) -> None:
        now = datetime.now(timezone.utc)
        note_item = timeline_service.build_note_item(
            description=description,
            created_by=performed_by,
            created_at=now.isoformat(),
            timestamp=now.isoformat(),
            tags=tags,
        )
        timeline_service.add_timeline_item(alert, note_item, created_by=performed_by)

    @staticmethod
    def _build_bulk_case_description(alerts: List[Alert]) -> str:
        alert_lines = [
            f"- {format_entity_id(alert.id, ALERT_PREFIX)}: {alert.title}"
            for alert in alerts
            if alert.id is not None
        ]
        return "Created from selected alerts:\n" + "\n".join(alert_lines)

    @staticmethod
    def _duplicate_description(
        target_case_id: Optional[int],
        target_alert_id: Optional[int],
    ) -> str:
        refs: List[str] = []
        if target_case_id is not None:
            refs.append(f"case {format_entity_id(target_case_id, CASE_PREFIX)}")
        if target_alert_id is not None:
            refs.append(f"alert {format_entity_id(target_alert_id, ALERT_PREFIX)}")
        return f"Bulk closed alert as duplicate of {' and '.join(refs)}"

    async def unlink_alert_from_case(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        unlinked_by: str
    ) -> Optional[Alert]:
        """Unlink an alert from its linked case.
        
        This will:
        - Remove the case_id from the alert
        - Clear the linked_at timestamp
        - Change the status from ESCALATED back to IN_PROGRESS
        
        Args:
            db: Database session
            alert_id: ID of the alert to unlink
            unlinked_by: Username of the user performing the unlink
            
        Returns:
            The updated alert, or None if alert not found
            
        Raises:
            ValueError: If alert is not linked to a case
        """
        try:
            db_alert = await self._get_alert_for_update(db, alert_id)
            if not db_alert:
                return None
            
            if not db_alert.case_id:
                raise AlertValidationError("Alert is not linked to a case")
            
            old_case_id = db_alert.case_id
            
            # Unlink alert from case
            db_alert.case_id = None
            db_alert.linked_at = None
            # Change status back to IN_PROGRESS (alert is no longer escalated)
            db_alert.status = AlertStatus.IN_PROGRESS
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error unlinking alert {alert_id} from case: {e}")
            raise

        logger.info(
            "Alert %s unlinked from case %s by %s",
            format_entity_id(db_alert.id, ALERT_PREFIX),
            format_entity_id(old_case_id, CASE_PREFIX),
            unlinked_by,
        )
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            db_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="case unlink",
        )

    async def add_timeline_item(
        self,
        db: AsyncSession,
        alert_id: int,
        timeline_item: AlertTimelineItem,
        added_by: str,
        created_at_override: Optional[datetime] = None,
        preserve_item_id: bool = False,
        idempotent: bool = False,
    ) -> Optional[Alert]:
        """Add a single timeline item to an alert's timeline."""
        try:
            committed_alert = await self._get_alert_model(db, alert_id)
            if committed_alert is None:
                return None
            added_item = await add_timeline_item_and_commit(
                db,
                entity_id=alert_id,
                entity_type="alert",
                timeline_item=timeline_item,
                performed_by=added_by,
                created_at_override=created_at_override,
                preserve_item_id=preserve_item_id,
                idempotent=idempotent,
            )
            if added_item is None:
                return None
        except TimelineValidationError as exc:
            await db.rollback()
            raise AlertValidationError(str(exc)) from exc
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding timeline item to alert {alert_id}: {e}")
            raise

        logger.info(f"Timeline item added to alert by {added_by}")
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            committed_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="timeline item addition",
        )

    async def update_timeline_item(
        self,
        db: AsyncSession,
        alert_id: int,
        item_id: str,
        updated_item: AlertTimelineItem,
        updated_by: str,
        expected_item_fields: dict[str, Any] | None = None,
    ) -> Optional[Alert]:
        """Update a specific timeline item in an alert with permission checks and audit logging."""
        try:
            committed_alert = await self._get_alert_model(db, alert_id)
            if committed_alert is None:
                return None
            updated_dict = await update_timeline_item_and_commit(
                db,
                entity_id=alert_id,
                entity_type="alert",
                item_id=item_id,
                timeline_item=updated_item,
                performed_by=updated_by,
                expected_item_fields=expected_item_fields,
            )

            if updated_dict is None:
                return None
        except TimelineValidationError as exc:
            await db.rollback()
            raise AlertValidationError(str(exc)) from exc
        except TimelineItemConflict:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating timeline item {item_id} in alert {alert_id}: {e}")
            raise

        logger.info(
            f"Timeline item {item_id} (type: {updated_dict.get('type')}) updated in alert {alert_id} by {updated_by}"
        )
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            committed_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="timeline item update",
        )

    async def remove_timeline_item(
        self,
        db: AsyncSession,
        alert_id: int,
        item_id: str,
        removed_by: str
    ) -> Optional[Alert]:
        """Remove a specific timeline item from an alert and clean up associated resources."""
        try:
            committed_alert = await self._get_alert_model(db, alert_id)
            if committed_alert is None:
                return None
            removed_item = await remove_timeline_item_and_commit(
                db,
                entity_id=alert_id,
                entity_type="alert",
                item_id=item_id,
                performed_by=removed_by,
            )
            if removed_item is None:
                return None
        except TimelineValidationError as exc:
            await db.rollback()
            raise AlertValidationError(str(exc)) from exc
        except Exception as e:
            await db.rollback()
            logger.error(f"Error removing timeline item {item_id} from alert {alert_id}: {e}")
            raise

        logger.info(f"Timeline item {item_id} removed from alert by {removed_by}")
        return await load_committed_response(
            db,
            lambda: self.get_alert(db, alert_id),
            committed_alert,
            logger=logger,
            entity_type="alert",
            entity_id=alert_id,
            operation="timeline item removal",
        )

alert_service = AlertService()
