from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, String
from sqlalchemy.orm import selectinload, defer
from sqlmodel import col
from typing import List, Optional, Set, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4
import logging
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate
from fastapi import HTTPException

from app.models.models import (
    Alert, Case, UserAccount, Task, Actor,
    AlertCreate, AlertUpdate, AlertTriageRequest,
    AlertRead, AlertTimelineItem, TriageRecommendation
)
from app.models.enums import AlertStatus, Priority, RecommendationStatus, TriageDisposition
from app.services.case_service import case_service
from app.services.alert_triage_apply_service import (
    apply_triage_state,
    create_case_from_alert,
    is_triage_completion_status,
    mark_alert_escalated,
)
from app.services.timeline_service import timeline_service
from app.services.audit_service import get_audit_service
from app.services import triage_recommendation_service

logger = logging.getLogger(__name__)


class AlertService:
    
    async def create_alert(
        self, 
        db: AsyncSession, 
        alert_data: AlertCreate
    ) -> Alert:
        """Create a new alert.
        
        If AI triage is enabled (langflow.alert_triage_flow_id is set) and
        auto-enqueue is enabled (triage.auto_enqueue is True or unset),
        automatically enqueues the alert for AI triage.
        """
        try:
            db_alert = Alert(
                title=alert_data.title,
                description=alert_data.description,
                priority=alert_data.priority,
                source=alert_data.source,
            )
            
            db.add(db_alert)
            await db.commit()
            await db.refresh(db_alert)
            
            logger.info(f"Alert created")
            
            # Auto-enqueue for AI triage if enabled
            await self._auto_enqueue_triage(db, db_alert.id)  # type: ignore[arg-type]
            
            return db_alert
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating alert: {e}")
            raise
    
    async def _auto_enqueue_triage(self, db: AsyncSession, alert_id: int):
        """Auto-enqueue alert for AI triage if enabled.
        
        Checks both langflow.alert_triage_flow_id and triage.auto_enqueue settings.
        Fails silently if triage is not enabled or task queue is unavailable.
        """
        from app.services.settings_service import SettingsService
        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_TRIAGE_ALERT
        from datetime import datetime, timezone
        
        try:
            settings = SettingsService(db)  # type: ignore[arg-type]
            
            # Check if triage flow is configured
            flow_id = await settings.get_typed_value("langflow.alert_triage_flow_id")
            if not flow_id:
                logger.debug(f"AI triage not enabled - skipping auto-enqueue for alert {alert_id}")
                return
            
            # Check if auto-enqueue is enabled (defaults to False)
            auto_enqueue = await settings.get_typed_value("triage.auto_enqueue")
            if auto_enqueue is not True:
                logger.debug(f"Auto-enqueue disabled - skipping for alert {alert_id}")
                return
            
            # Create QUEUED placeholder
            recommendation = TriageRecommendation(
                alert_id=alert_id,
                disposition=TriageDisposition.UNKNOWN,
                confidence=0.0,
                reasoning_bullets=[],
                recommended_actions=[],
                created_by="system",
                created_at=datetime.now(timezone.utc),
                status=RecommendationStatus.QUEUED,
            )
            db.add(recommendation)
            await db.commit()
            await db.refresh(recommendation)
            
            # Enqueue triage task
            try:
                task_queue = get_task_queue_service()
                await task_queue.enqueue(
                    task_name=TASK_TRIAGE_ALERT,
                    payload={"alert_id": alert_id}
                )
                logger.info(f"Auto-enqueued AI triage for alert {alert_id}")
            except RuntimeError as e:
                # Task queue not available - mark as failed
                recommendation.status = RecommendationStatus.FAILED
                recommendation.error_message = f"Task queue not available: {str(e)}"
                db.add(recommendation)
                await db.commit()
                logger.warning(f"Failed to auto-enqueue triage for alert {alert_id}: {e}")
                
        except Exception as e:
            # Don't fail alert creation if triage enqueue fails
            logger.warning(f"Auto-enqueue triage failed for alert {alert_id}: {e}")
    
    async def _get_alert_model(self, db: AsyncSession, alert_id: int) -> Optional[Alert]:
        """Get the tracked alert model with related entities loaded."""
        try:
            query = (
                select(Alert)
                .options(
                    selectinload(Alert.case),  # type: ignore
                    selectinload(Alert.triage_recommendation)  # type: ignore
                )
                .where(Alert.id == alert_id)  # type: ignore
            )
            result = await db.execute(query)
            db_alert = result.scalar_one_or_none()
            if not db_alert:
                return None
            
            # Eager load all entities referenced in timeline items to avoid N+1 queries
            if db_alert.timeline_items:
                await self._preload_timeline_entities(db, db_alert.timeline_items)

            return db_alert
        except Exception as e:
            logger.error(f"Error fetching alert {alert_id}: {e}")
            raise

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

        db_alert = await timeline_service.denormalize_entity_timeline(
            db,
            db_alert,
            human_prefix="ALT",
            include_linked_timelines=include_linked_timelines,
        )
        return await timeline_service.coalesce_timeline_audit(
            db,
            entity_type="alert",
            entity_id=alert_id,
            entity=db_alert,
        )
    
    async def get_alert_by_human_id(self, db: AsyncSession, human_id: str) -> Optional[Alert]:
        """Get alert by human_id."""
        try:
            if not human_id.startswith("ALT-"):
                return None
            alert_id = int(human_id[4:])
            return await self.get_alert(db, alert_id)
        except (ValueError, IndexError):
            return None
    
    async def get_alerts(
        self, 
        db: AsyncSession, 
        status: Optional[List[AlertStatus]] = None,
        assignee: Optional[List[str]] = None,
        case_id: Optional[int] = None,
        priority: Optional[List[Priority]] = None,
        source: Optional[str] = None,
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
        try:
            # Build base query
            # Defer timeline_items - not needed for list view and can cause validation 
            # errors if malformed data exists. Detail view fetches them separately.
            query = select(Alert).options(
                selectinload(Alert.case),  # type: ignore
                selectinload(Alert.triage_recommendation),  # type: ignore
                defer(Alert.timeline_items)  # type: ignore[arg-type]
            )
            
            # Apply filters
            filters = []
            if status:
                # Handle multiple statuses with IN clause
                filters.append(Alert.status.in_(status))  # type: ignore
            if assignee:
                # Handle multiple assignees with IN clause
                # Special handling for "__unassigned__" token to filter for NULL assignees
                unassigned_requested = "__unassigned__" in assignee
                regular_assignees = [a for a in assignee if a != "__unassigned__"]
                
                if unassigned_requested and regular_assignees:
                    # Both unassigned and specific assignees requested
                    filters.append(
                        or_(
                            Alert.assignee.is_(None),  # type: ignore
                            Alert.assignee.in_(regular_assignees)  # type: ignore
                        )
                    )
                elif unassigned_requested:
                    # Only unassigned requested
                    filters.append(Alert.assignee.is_(None))  # type: ignore
                elif regular_assignees:
                    # Only specific assignees requested
                    filters.append(Alert.assignee.in_(regular_assignees))  # type: ignore
            if case_id:
                filters.append(Alert.case_id == case_id)
            if priority:
                # Handle multiple priorities with IN clause
                filters.append(Alert.priority.in_(priority))  # type: ignore
            if source:
                filters.append(Alert.source.ilike(f"%{source}%"))  # type: ignore
            if has_case is not None:
                if has_case:
                    filters.append(Alert.case_id.is_not(None))  # type: ignore
                else:
                    filters.append(Alert.case_id.is_(None))  # type: ignore
            
            # Date range filtering (expects UTC ISO8601 strings)
            if start_date:
                try:
                    # Parse ISO8601 with or without 'Z' suffix
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    filters.append(Alert.created_at >= start_dt)  # type: ignore
                except ValueError:
                    logger.warning(f"Invalid start_date format: {start_date}")
            
            if end_date:
                try:
                    # Parse ISO8601 with or without 'Z' suffix
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    filters.append(Alert.created_at <= end_dt)  # type: ignore
                except ValueError:
                    logger.warning(f"Invalid end_date format: {end_date}")
            
            # Search filtering (match against ID, title, or description)
            if search:
                search_pattern = f"%{search}%"
                filters.append(
                    or_(
                        cast(Alert.id, String).ilike(search_pattern),  # type: ignore
                        Alert.title.ilike(search_pattern),  # type: ignore
                        Alert.description.ilike(search_pattern)  # type: ignore
                    )
                )
            
            if filters:
                query = query.where(*filters)
            
            # Apply sorting
            sort_column = getattr(Alert, sort_by, Alert.created_at)
            if sort_order.lower() == "asc":
                query = query.order_by(sort_column.asc())  # type: ignore
            else:
                query = query.order_by(sort_column.desc())  # type: ignore
            
            # Use fastapi-pagination for pagination with SQLAlchemy
            return await paginate(db, query)
            
        except Exception as e:
            logger.error(f"Error fetching alerts: {e}")
            raise
    
    async def update_alert(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        alert_update: AlertUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[Alert]:
        """Update an alert."""
        try:
            db_alert = await self._get_alert_model(db, alert_id)
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
                    if field == 'status' and value != old_status:
                        status_changed = True
                        new_status = value
                    setattr(db_alert, field, value)
            
            # Update the updated_at timestamp
            db_alert.updated_at = datetime.now(timezone.utc)
            
            # Add timeline item for status changes
            if status_changed and updated_by:
                # Map status values (not enum attributes) to descriptions
                status_descriptions = {
                    "new": "Alert status changed to New",
                    "in_progress": "Alert status changed to In Progress",
                    "escalated": "Alert status changed to Escalated",
                    "closed_true_positive": "Alert closed as True Positive",
                    "closed_benign_positive": "Alert closed as True Positive Benign",
                    "closed_false_positive": "Alert closed as False Positive",
                    "closed_unresolved": "Alert closed as Unresolved",
                    "closed_duplicate": "Alert closed as Duplicate",
                }
                
                description = status_descriptions.get(
                    db_alert.status,
                    f"Alert status changed to {db_alert.status}"
                )
                
                # Create a note timeline item for the status change
                now = datetime.now(timezone.utc)
                status_change_item = {
                    "id": str(uuid4()),
                    "type": "note",
                    "description": description,
                    "created_at": now.isoformat(),
                    "timestamp": now.isoformat(),
                    "created_by": updated_by,
                    "tags": ["status-change"],
                    "flagged": False,
                    "highlighted": False,
                    "replies": []
                }
                
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

            await db.commit()
            await db.refresh(db_alert)
            
            logger.info(f"Alert updated")
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating alert {alert_id}: {e}")
            raise
    
    async def triage_alert(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        triage_request: AlertTriageRequest,
        triaged_by: str
    ) -> Optional[Alert]:
        """Triage an alert and optionally escalate to case."""
        try:
            db_alert = await self._get_alert_model(db, alert_id)
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
                    raise HTTPException(status_code=400, detail="Alert is already escalated to a case")

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
            await db.refresh(db_alert)
            
            logger.info(f"Alert triaged by {triaged_by}")
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error triaging alert {alert_id}: {e}")
            raise
    
    async def link_alert_to_case(
        self, 
        db: AsyncSession, 
        alert_id: int, 
        case_id: int,
        linked_by: str
    ) -> Optional[Alert]:
        """Link an existing alert to an existing case."""
        try:
            db_alert = await self._get_alert_model(db, alert_id)
            if not db_alert:
                return None
            
            # Verify case exists
            db_case = await case_service.get_case(db, case_id)
            if not db_case:
                raise ValueError(f"Case {case_id} not found")
            
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
            await db.refresh(db_alert)
            
            logger.info(f"Alert linked to case CAS-{db_case.id:07d} by {linked_by}")
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error linking alert {alert_id} to case {case_id}: {e}")
            raise

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
            db_alert = await self._get_alert_model(db, alert_id)
            if not db_alert:
                return None
            
            if not db_alert.case_id:
                raise ValueError("Alert is not linked to a case")
            
            old_case_id = db_alert.case_id
            
            # Unlink alert from case
            db_alert.case_id = None
            db_alert.linked_at = None
            # Change status back to IN_PROGRESS (alert is no longer escalated)
            db_alert.status = AlertStatus.IN_PROGRESS
            
            await db.commit()
            await db.refresh(db_alert)
            
            logger.info(f"Alert ALT-{db_alert.id:07d} unlinked from case CAS-{old_case_id:07d} by {unlinked_by}")
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error unlinking alert {alert_id} from case: {e}")
            raise

    async def add_timeline_item(
        self,
        db: AsyncSession,
        alert_id: int,
        timeline_item: AlertTimelineItem,
        added_by: str
    ) -> Optional[Alert]:
        """Add a single timeline item to an alert's timeline."""
        try:
            db_alert = await self._get_alert_model(db, alert_id)
            if not db_alert:
                return None
            
            # Use mode='json' to ensure datetime fields are serialized to ISO strings
            item_dict = timeline_item.model_dump(mode='json')
            
            # Add via timeline service with resource sync
            # entity_type="alert" will raise error if trying to add task items
            item_dict = await timeline_service.add_timeline_item_with_sync(
                db, db_alert, item_dict, added_by,
                entity_id=alert_id, entity_type="alert"
            )
            
            await db.commit()
            await db.refresh(db_alert)
            
            await get_audit_service(db).log_timeline_item_added(
                entity_type="alert",
                entity_id=alert_id,
                item_id=item_dict.get("id", ""),
                item_type=item_dict.get("type", "unknown"),
                user=added_by,
                new_value=item_dict,
            )
            logger.info(f"Timeline item added to alert by {added_by}")
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except ValueError as e:
            # Raised when trying to add unsupported item types (e.g., tasks on alerts)
            await db.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding timeline item to alert {alert_id}: {e}")
            raise

    async def update_timeline_item(
        self,
        db: AsyncSession,
        alert_id: int,
        item_id: str,
        updated_item: AlertTimelineItem,
        updated_by: str
    ) -> Optional[Alert]:
        """Update a specific timeline item in an alert with permission checks and audit logging."""
        try:
            db_alert = await self._get_alert_model(db, alert_id)
            if not db_alert:
                return None
            
            # Find the existing item to validate permissions and preserve metadata
            existing_item = timeline_service._find_item_by_id(db_alert.timeline_items or [], item_id)
            if not existing_item:
                raise ValueError(f"Timeline item {item_id} not found")
            
            # Permission check: users can edit own items, admins can edit any
            if existing_item.get('created_by') != updated_by:
                # Check if user is admin
                result = await db.execute(
                    select(UserAccount).where(UserAccount.username == updated_by)  # type: ignore
                )
                user = result.scalars().first()
                if not user or user.role.value != 'ADMIN':
                    raise HTTPException(
                        status_code=403,
                        detail=f"You can only edit items you created. This item was created by {existing_item.get('created_by')}"
                    )
            
            # Use mode='json' to ensure datetime fields are serialized to ISO strings
            item_dict = updated_item.model_dump(mode='json')
            
            # Update via timeline service with resource sync
            result = await timeline_service.update_timeline_item_with_sync(
                db, db_alert, item_id, item_dict, updated_by
            )
            
            if result is None:
                raise ValueError(f"Timeline item {item_id} not found")
            
            # Re-fetch the updated item for audit logging
            updated_dict = timeline_service._find_item_by_id(db_alert.timeline_items or [], item_id) or item_dict
            
            # Audit log the edit with field-level changes
            await get_audit_service(db).log_timeline_edit(
                entity_type="alert",
                entity_id=alert_id,
                item_id=item_id,
                item_type=updated_dict.get('type', 'unknown'),
                before=existing_item,
                after=updated_dict,
                user=updated_by,
            )
            
            await db.commit()
            await db.refresh(db_alert)
            
            logger.info(
                f"Timeline item {item_id} (type: {updated_dict.get('type')}) updated in alert {alert_id} by {updated_by}"
            )
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating timeline item {item_id} in alert {alert_id}: {e}")
            raise

    async def remove_timeline_item(
        self,
        db: AsyncSession,
        alert_id: int,
        item_id: str,
        removed_by: str
    ) -> Optional[Alert]:
        """Remove a specific timeline item from an alert and clean up associated resources."""
        try:
            db_alert = await self._get_alert_model(db, alert_id)
            if not db_alert:
                return None
            
            # Find the item for error messaging
            item_to_remove = timeline_service._find_item_by_id(db_alert.timeline_items or [], item_id)
            if not item_to_remove:
                raise ValueError(f"Timeline item {item_id} not found")
            
            # Remove timeline item with resource cleanup (handles attachments, etc.)
            if not await timeline_service.remove_timeline_item_with_cleanup(
                db, db_alert, item_id, removed_by
            ):
                raise ValueError(f"Timeline item {item_id} not found")
            
            await db.commit()
            await db.refresh(db_alert)
            
            await get_audit_service(db).log_timeline_item_deleted(
                entity_type="alert",
                entity_id=alert_id,
                item_id=item_id,
                item_type=item_to_remove.get("type", "unknown"),
                user=removed_by,
                old_value=item_to_remove,
            )
            logger.info(f"Timeline item {item_id} removed from alert by {removed_by}")
            db_alert = await timeline_service.denormalize_entity_timeline(db, db_alert, human_prefix="ALT")
            return await timeline_service.coalesce_timeline_audit(
                db,
                entity_type="alert",
                entity_id=alert_id,
                entity=db_alert,
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error removing timeline item {item_id} from alert {alert_id}: {e}")
            raise
    
    async def _preload_timeline_entities(
        self,
        db: AsyncSession,
        timeline_items: List[Dict[str, Any]]
    ) -> None:
        """Preload all entities referenced in timeline items to avoid N+1 queries.
        
        This eagerly loads actors, tasks, and cases that are referenced
        in the timeline items into SQLAlchemy's session cache.
        """
        actor_ids: Set[int] = set()
        task_ids: Set[int] = set()
        case_ids: Set[int] = set()
        
        def extract_ids_recursive(items: List[Dict[str, Any]]) -> None:
            """Recursively extract entity IDs from items and their replies."""
            for item in items:
                item_type = item.get("type")
                
                # Extract entity IDs based on item type
                if item_type in ("internal_actor", "external_actor", "threat_actor"):
                    if item.get("actor_id"):
                        actor_ids.add(item["actor_id"])
                elif item_type == "task":
                    if item.get("task_id") and isinstance(item["task_id"], int):
                        task_ids.add(item["task_id"])
                elif item_type == "case":
                    if item.get("case_id") and isinstance(item["case_id"], int):
                        case_ids.add(item["case_id"])
                
                # Recursively process replies
                if item.get("replies"):
                    extract_ids_recursive(item["replies"])
        
        # Extract all IDs from the timeline
        extract_ids_recursive(timeline_items)
        
        # Bulk load all actors
        if actor_ids:
            actor_query = select(Actor).where(col(Actor.id).in_(actor_ids))
            await db.execute(actor_query)
            logger.debug(f"Preloaded {len(actor_ids)} actors for alert timeline")
        
        # Bulk load all tasks
        if task_ids:
            task_query = select(Task).where(col(Task.id).in_(task_ids))
            await db.execute(task_query)
            logger.debug(f"Preloaded {len(task_ids)} tasks for alert timeline")
        
        # Bulk load all cases
        if case_ids:
            case_query = select(Case).where(col(Case.id).in_(case_ids))
            await db.execute(case_query)
            logger.debug(f"Preloaded {len(case_ids)} cases for alert timeline")


alert_service = AlertService()
