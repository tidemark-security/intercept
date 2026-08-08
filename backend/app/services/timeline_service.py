from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, TYPE_CHECKING, TypeVar
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timezone
import uuid
import logging

import json
from sqlalchemy import select
from sqlmodel import col

from app.core.entity_ids import ALERT_PREFIX, CASE_PREFIX, TASK_PREFIX, format_entity_id
from app.models.models import Actor, ActorSnapshot, Alert, AuditLog, Case, Task
from app.services.date_filter_utils import parse_optional_utc_datetime
from app.services.normalization_service import (
    NormalizationValidationError,
    TimelineReferenceIndex,
    normalization_service,
)

if TYPE_CHECKING:
    from app.models.models import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)

_EnumT = TypeVar("_EnumT", bound=Enum)


class TimelineValidationError(ValueError):
    """A timeline mutation violates a client-facing domain rule."""


def _coerce_enum(value: Any, enum_type: type[_EnumT]) -> _EnumT | None:
    """Return a known enum member, or None for malformed legacy timeline data."""
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return None

# Fields that should be preserved in the timeline JSON for task items
TASK_REFERENCE_FIELDS: Set[str] = {
    "id", "type", "task_id", "description", "created_at", "created_by",
    "parent_id", "replies", "flagged", "highlighted", "tags", "timestamp",
}


@dataclass(frozen=True, slots=True)
class TimelineRemovalCleanup:
    """External cleanup to perform only after the database deletion commits."""

    storage_key: Optional[str] = None


@dataclass(frozen=True, slots=True)
class DeferredAutonomousTaskEnqueue:
    """Autonomous task enqueue that is safe to run only after commit."""

    task_id: int
    assignee: str


@dataclass(frozen=True, slots=True)
class TimelineItemUpdateResult:
    """A timeline update plus any side effect deferred until after commit."""

    item: Dict[str, Any]
    autonomous_task_enqueue: Optional[DeferredAutonomousTaskEnqueue] = None


class TimelineService:
    """
    Shared helpers for timeline item normalization, denormalization,
    and mutation (add/update/remove) across alerts and cases.
    """

    def iter_items(self, items: Any) -> Iterable[Dict[str, Any]]:
        """Iterate valid item mappings across legacy list and mapping storage."""
        if isinstance(items, dict):
            return (item for item in items.values() if isinstance(item, dict))
        if isinstance(items, list):
            return (item for item in items if isinstance(item, dict))
        return ()

    def _collect_reference_ids(
        self,
        timeline_items: List[Dict[str, Any]] | Dict[str, Dict[str, Any]],
        referenced_ids: Dict[str, Set[int]],
        actor_snapshot_keys: Set[tuple[int, str]],
    ) -> None:
        for item in self.iter_items(timeline_items):
            item_type = item.get("type")
            if item_type in {"internal_actor", "external_actor", "threat_actor"}:
                actor_id = item.get("actor_id")
                if isinstance(actor_id, int):
                    referenced_ids["actor"].add(actor_id)
                    snapshot_hash = item.get("snapshot_hash")
                    if isinstance(snapshot_hash, str) and snapshot_hash:
                        actor_snapshot_keys.add((actor_id, snapshot_hash))
            elif item_type in {"alert", "case", "task"}:
                entity_id = item.get(f"{item_type}_id")
                if isinstance(entity_id, int):
                    referenced_ids[item_type].add(entity_id)

            replies = item.get("replies")
            if replies:
                self._collect_reference_ids(replies, referenced_ids, actor_snapshot_keys)

    async def _load_reference_entities(
        self,
        db: AsyncSession,
        referenced_ids: Dict[str, Set[int]],
        references: TimelineReferenceIndex,
    ) -> None:
        model_and_index = {
            "actor": (Actor, references.actors),
            "alert": (Alert, references.alerts),
            "case": (Case, references.cases),
            "task": (Task, references.tasks),
        }
        for entity_type, entity_ids in referenced_ids.items():
            model, index = model_and_index[entity_type]
            missing_ids = entity_ids.difference(index)
            if not missing_ids:
                continue

            result = await db.execute(select(model).where(col(model.id).in_(missing_ids)))
            entities = result.scalars().all()
            index.update(
                {
                    entity.id: entity
                    for entity in entities
                    if isinstance(entity.id, int)
                }
            )
            logger.debug("Loaded %d referenced %ss", len(entities), entity_type)

    async def load_referenced_entities(
        self,
        db: AsyncSession,
        timeline_items: List[Dict[str, Any]] | Dict[str, Dict[str, Any]],
        *,
        include_linked_timelines: bool = False,
        references: TimelineReferenceIndex | None = None,
    ) -> TimelineReferenceIndex:
        """Build a strong, request-local index for all timeline references."""
        root_ids: Dict[str, Set[int]] = {
            "actor": set(),
            "alert": set(),
            "case": set(),
            "task": set(),
        }
        actor_snapshot_keys: Set[tuple[int, str]] = set()
        self._collect_reference_ids(timeline_items, root_ids, actor_snapshot_keys)

        references = references or TimelineReferenceIndex()
        await self._load_reference_entities(db, root_ids, references)

        if include_linked_timelines:
            nested_ids: Dict[str, Set[int]] = {
                "actor": set(),
                "alert": set(),
                "case": set(),
                "task": set(),
            }
            for entity_type, index in (
                ("alert", references.alerts),
                ("case", references.cases),
                ("task", references.tasks),
            ):
                for entity_id in root_ids[entity_type]:
                    entity = index.get(entity_id)
                    source_timeline = getattr(entity, "timeline_items", None)
                    if source_timeline:
                        self._collect_reference_ids(
                            source_timeline,
                            nested_ids,
                            actor_snapshot_keys,
                        )
            await self._load_reference_entities(db, nested_ids, references)

        if actor_snapshot_keys:
            actor_ids = {actor_id for actor_id, _ in actor_snapshot_keys}
            snapshot_hashes = {snapshot_hash for _, snapshot_hash in actor_snapshot_keys}
            result = await db.execute(
                select(ActorSnapshot).where(
                    col(ActorSnapshot.actor_id).in_(actor_ids),
                    col(ActorSnapshot.snapshot_hash).in_(snapshot_hashes),
                )
            )
            references.actor_snapshots.update(
                {
                    (snapshot.actor_id, snapshot.snapshot_hash): snapshot
                    for snapshot in result.scalars().all()
                    if (snapshot.actor_id, snapshot.snapshot_hash) in actor_snapshot_keys
                }
            )

        return references

    def _seed_entity_references(self, entity: Any, human_prefix: str) -> TimelineReferenceIndex:
        """Reuse relationships already loaded by the owning entity query."""
        references = TimelineReferenceIndex()
        entity_id = getattr(entity, "id", None)
        if not isinstance(entity_id, int):
            return references

        if human_prefix == CASE_PREFIX:
            references.cases[entity_id] = entity
            references.alerts.update(
                {alert.id: alert for alert in getattr(entity, "alerts", ()) if isinstance(alert.id, int)}
            )
            references.tasks.update(
                {task.id: task for task in getattr(entity, "tasks", ()) if isinstance(task.id, int)}
            )
        elif human_prefix == ALERT_PREFIX:
            references.alerts[entity_id] = entity
            linked_case = getattr(entity, "case", None)
            linked_case_id = getattr(linked_case, "id", None)
            if isinstance(linked_case_id, int):
                references.cases[linked_case_id] = linked_case
        elif human_prefix == TASK_PREFIX:
            references.tasks[entity_id] = entity

        return references

    def _ensure_item_id(self, item: Dict[str, Any]) -> None:
        if not item.get("id"):
            item["id"] = self.generate_item_id()

    def _assign_new_item_ids(self, item: Dict[str, Any]) -> None:
        item["id"] = self.generate_item_id()
        replies = item.get("replies")
        for reply in self.iter_items(replies):
            self._assign_new_item_ids(reply)

    def _coerce_item_for_storage(self, item: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_item_id(item)
        replies = item.get("replies")
        item["replies"] = self._coerce_storage_items(replies)
        return item

    def _coerce_storage_items(self, items: Any) -> Dict[str, Dict[str, Any]]:
        mapping: Dict[str, Dict[str, Any]] = {}

        if isinstance(items, dict):
            candidates = list(items.values())
        elif isinstance(items, list):
            candidates = items
        else:
            return mapping

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            self._coerce_item_for_storage(candidate)
            mapping[str(candidate["id"])] = candidate

        return mapping

    def _ensure_storage_items(self, entity: Any) -> Dict[str, Dict[str, Any]]:
        items = self._coerce_storage_items(getattr(entity, "timeline_items", None))
        entity.timeline_items = items
        return items

    def response_items(self, items: Any) -> List[Dict[str, Any]]:
        """Return copied, recursively sorted items for API responses."""
        response_items: List[Dict[str, Any]] = []
        for item in self.iter_items(items):
            item_copy = dict(item)
            item_copy["replies"] = self.response_items(item.get("replies"))
            response_items.append(item_copy)
        response_items.sort(key=self._timeline_sort_key)
        return response_items

    def _response_mapping(self, items: Any) -> Dict[str, Dict[str, Any]]:
        response_items: Dict[str, Dict[str, Any]] = {}
        for item in self.iter_items(items):
            item_copy = dict(item)
            item_copy["replies"] = self._response_mapping(item.get("replies"))
            response_items[str(item_copy["id"])] = item_copy
        return response_items

    def generate_item_id(self) -> str:
        """Generate a unique identifier for a timeline item."""
        return uuid.uuid4().hex

    def build_note_item(
        self,
        *,
        description: str,
        created_by: str,
        timestamp: datetime | str,
        tags: Iterable[str] = (),
        created_at: datetime | str | None = None,
        flagged: bool = False,
        highlighted: bool = False,
    ) -> Dict[str, Any]:
        """Build a note for insertion through :meth:`add_timeline_item`."""
        item: Dict[str, Any] = {
            "type": "note",
            "description": description,
            "timestamp": timestamp,
            "created_by": created_by,
            "tags": list(tags),
            "flagged": flagged,
            "highlighted": highlighted,
            "replies": [],
        }
        if created_at is not None:
            item["created_at"] = created_at
        return item

    def _validate_reply_depth(self, item: Dict[str, Any], current_depth: int = 0, max_depth: int = 5) -> None:
        """
        Validate that replies don't exceed max depth (default: 5 levels).
        Raises ValueError if validation fails.
        
        Args:
            item: Timeline item to validate
            current_depth: Current nesting level (0 = top-level)
            max_depth: Maximum allowed nesting depth
        """
        if current_depth >= max_depth:
            raise TimelineValidationError(
                f"Replies cannot be nested more than {max_depth} levels deep"
            )
        
        # Check each reply recursively
        if item.get("replies"):
            for reply in self.iter_items(item["replies"]):
                self._validate_reply_depth(reply, current_depth + 1, max_depth)

    async def normalize_item(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a timeline item and any first-class entity reference it contains."""
        # Validate reply depth before normalizing (max 5 levels)
        self._validate_reply_depth(item)
        
        try:
            normalized = await normalization_service.normalize_item(db, item)
        except NormalizationValidationError as exc:
            raise TimelineValidationError(str(exc)) from exc
        
        # Recursively normalize replies if present (up to max depth)
        if "replies" in normalized and normalized["replies"]:
            normalized_replies = []
            for reply in self.iter_items(normalized["replies"]):
                # Recursively normalize each reply (which may have its own replies)
                normalized_replies.append(await self.normalize_item(db, reply))
            normalized["replies"] = normalized_replies
        
        return normalized

    async def denormalize_entity_timeline(
        self, 
        db: AsyncSession, 
        entity: Any, 
        human_prefix: str,
        include_linked_timelines: bool = False,
        detach: bool = True,
    ) -> Any:
        """
        Set human-readable id on the entity and denormalize all timeline items.
        human_prefix examples: "ALT" for alerts, "CAS" for cases.
        
        Also injects synthetic timeline items for linked entities:
        - For Cases: injects alert items for each linked alert (based on alert.case_id FK)
        - For Alerts: injects case item if linked to a case (based on alert.case_id FK)
        
        Args:
            db: Database session
            entity: The case/alert entity
            human_prefix: Prefix for human ID (e.g., "ALT", "CAS")
            include_linked_timelines: If True, alert and task items will include
                source_timeline_items from the linked entity
        """
        items = self._response_mapping(getattr(entity, "timeline_items", None))
        
        # Filter out any previously injected items (in case entity was cached/reused)
        items = {
            item_id: item
            for item_id, item in items.items()
            if not item.get("_injected")
        }
        
        references = self._seed_entity_references(entity, human_prefix)

        # Inject synthetic timeline items for linked entities
        items = await self._inject_linked_entity_items(
            db,
            entity,
            human_prefix,
            items,
            references=references,
        )
        references = await self.load_referenced_entities(
            db,
            items,
            include_linked_timelines=include_linked_timelines,
            references=references,
        )

        denormed: Dict[str, Dict[str, Any]] = {}
        for item_id, item in items.items():
            denormed[item_id] = await self._denormalize_item_recursive(
                db,
                item,
                include_linked_timelines=include_linked_timelines,
                references=references,
            )

        if detach:
            state = sa_inspect(entity)
            if state.session is not None:
                state.session.expunge(entity)

        entity.timeline_items = denormed
        return entity

    async def coalesce_timeline_audit(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int | str,
        entity: Any,
    ) -> Any:
        """Annotate denormalized timeline items with audit metadata and tombstones."""
        timeline_items = self._response_mapping(getattr(entity, "timeline_items", None))

        result = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == str(entity_id),
                col(AuditLog.item_id).is_not(None),
                col(AuditLog.event_type).in_(("timeline.item.updated", "timeline.item.deleted")),
            )
            .order_by(col(AuditLog.performed_at).asc())
        )
        audit_rows = result.scalars().all()
        if not audit_rows:
            return entity

        edited_item_ids = {
            row.item_id
            for row in audit_rows
            if row.event_type == "timeline.item.updated" and row.item_id
        }
        deleted_items = [row for row in audit_rows if row.event_type == "timeline.item.deleted" and row.item_id]

        self._annotate_items_with_audit(timeline_items, edited_item_ids)
        self._inject_deleted_tombstones(timeline_items, deleted_items)
        setattr(entity, "timeline_items", timeline_items)
        return entity

    async def prepare_entity_detail_timeline(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        entity_type: str,
        entity_id: int,
        human_prefix: str,
        include_linked_timelines: bool = False,
    ) -> Any:
        entity = await self.denormalize_entity_timeline(
            db,
            entity,
            human_prefix=human_prefix,
            include_linked_timelines=include_linked_timelines,
        )
        entity = await self.coalesce_timeline_audit(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            entity=entity,
        )

        from app.services.enrichment.service import enrichment_service

        await enrichment_service.reconcile_entity_enrichment_statuses(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            timeline_items=getattr(entity, "timeline_items", None) or {},
        )
        return entity

    def _annotate_items_with_audit(self, items: Dict[str, Dict[str, Any]], edited_item_ids: Set[str]) -> None:
        for item in items.values():
            if item.get("id") in edited_item_ids:
                item["audit"] = {"edited": True}
            replies = item.get("replies")
            if replies and isinstance(replies, dict):
                self._annotate_items_with_audit(replies, edited_item_ids)

    def _inject_deleted_tombstones(self, items: Dict[str, Dict[str, Any]], deleted_rows: List[AuditLog]) -> None:
        for row in deleted_rows:
            if not row.item_id:
                continue
            snapshot = self._load_audit_snapshot(row.old_value)
            tombstone = {
                "id": row.item_id,
                "type": "_deleted",
                "deleted_at": row.performed_at.isoformat(),
                "deleted_by": row.performed_by or "system",
                "original_type": snapshot.get("type", "unknown"),
                "original_timestamp": snapshot.get("timestamp"),
                "original_created_at": snapshot.get("created_at"),
                "original_created_by": snapshot.get("created_by"),
                "parent_id": snapshot.get("parent_id"),
                "replies": {},
            }
            parent_id = snapshot.get("parent_id")
            if parent_id and self._add_reply_to_parent(items, parent_id, tombstone):
                continue
            if not self._contains_item(items, row.item_id):
                items[str(row.item_id)] = tombstone

    def _contains_item(self, items: Dict[str, Dict[str, Any]], item_id: str) -> bool:
        for item in items.values():
            if item.get("id") == item_id:
                return True
            replies = item.get("replies")
            if replies and isinstance(replies, dict) and self._contains_item(replies, item_id):
                return True
        return False

    def _load_audit_snapshot(self, value: Optional[str]) -> Dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _timeline_sort_key(self, item: Dict[str, Any]) -> str:
        return str(
            item.get("original_timestamp")
            or item.get("timestamp")
            or item.get("original_created_at")
            or item.get("created_at")
            or item.get("deleted_at")
            or ""
        )

    async def _get_case_reference(
        self,
        db: AsyncSession,
        case_id: int,
        references: TimelineReferenceIndex,
    ) -> Case | None:
        case = references.cases.get(case_id)
        if case is not None:
            return case

        from app.services.case_service import case_service

        case = await case_service.get_case_minimal(db, case_id)
        if case is not None:
            references.cases[case_id] = case
        return case

    @staticmethod
    def _linked_item_fields(
        *,
        item_id: str,
        item_type: str,
        linked_at: Any,
        created_by: str,
        tag: str,
        entity_tags: Any,
    ) -> Dict[str, Any]:
        """Build fields shared by synthetic linked-entity timeline items."""
        timestamp = linked_at.isoformat()
        return {
            "id": item_id,
            "type": item_type,
            "created_at": timestamp,
            "timestamp": timestamp,
            "created_by": created_by,
            "tags": [tag],
            "entity_tags": entity_tags if isinstance(entity_tags, list) else [],
            "flagged": False,
            "highlighted": False,
            "replies": {},
            "_injected": True,
        }

    def _build_linked_alert_item(self, alert: Any) -> Dict[str, Any]:
        return {
            **self._linked_item_fields(
                item_id=f"linked-alert-{alert.id}",
                item_type="alert",
                linked_at=alert.linked_at,
                created_by=alert.assignee or "system",
                tag="linked-alert",
                entity_tags=alert.tags,
            ),
            "alert_id": alert.id,
            "title": alert.title,
            "priority": alert.priority,
            "assignee": alert.assignee,
            "entity_description": alert.description,
        }

    def _build_linked_task_item(self, task: Any) -> Dict[str, Any]:
        return {
            **self._linked_item_fields(
                item_id=f"linked-task-{task.id}",
                item_type="task",
                linked_at=task.linked_at,
                created_by=task.created_by or "system",
                tag="linked-task",
                entity_tags=task.tags,
            ),
            "task_id": task.id,
            "title": task.title,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "priority": task.priority,
            "assignee": task.assignee,
            "entity_description": task.description,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "picerl_stage": task.picerl_stage.value if task.picerl_stage else None,
            "source_runbook": task.source_runbook,
        }

    def _build_linked_case_item(
        self,
        case: Case,
        *,
        case_id: int,
        linked_at: Any,
        created_by: str,
    ) -> Dict[str, Any]:
        return {
            **self._linked_item_fields(
                item_id=f"linked-case-{case_id}",
                item_type="case",
                linked_at=linked_at,
                created_by=created_by,
                tag="linked",
                entity_tags=case.tags,
            ),
            "case_id": case_id,
            "title": case.title,
            "priority": case.priority,
            "assignee": case.assignee,
            "entity_description": case.description,
            "description": f"Linked to Case {format_entity_id(case_id, CASE_PREFIX)}",
        }
    
    async def _inject_linked_entity_items(
        self,
        db: AsyncSession,
        entity: Any,
        human_prefix: str,
        items: Dict[str, Dict[str, Any]],
        *,
        references: TimelineReferenceIndex,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Inject synthetic timeline items for linked entities based on FK relationships.
        
        - For Cases (CAS): inject alert items for each linked alert
        - For Alerts (ALT): inject case item if linked to a case
        """
        if human_prefix == CASE_PREFIX:
            for alert in getattr(entity, "alerts", None) or []:
                if alert.linked_at:
                    alert_item = self._build_linked_alert_item(alert)
                    items[str(alert_item["id"])] = alert_item

            for task in getattr(entity, "tasks", None) or []:
                if task.linked_at:
                    task_item = self._build_linked_task_item(task)
                    items[str(task_item["id"])] = task_item

        elif human_prefix in {ALERT_PREFIX, TASK_PREFIX}:
            case_id = getattr(entity, "case_id", None)
            linked_at = getattr(entity, "linked_at", None)
            if case_id and linked_at:
                case = await self._get_case_reference(db, case_id, references)
                if case:
                    created_by = (
                        entity.assignee
                        if human_prefix == ALERT_PREFIX
                        else getattr(entity, "created_by", None)
                    ) or "system"
                    case_item = self._build_linked_case_item(
                        case,
                        case_id=case_id,
                        linked_at=linked_at,
                        created_by=created_by,
                    )
                    items[str(case_item["id"])] = case_item

        return items
    
    async def _denormalize_item_recursive(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any],
        include_linked_timelines: bool = False,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        """Recursively denormalize a timeline item and its replies.
        
        Args:
            db: Database session
            item: Timeline item dict to denormalize
            include_linked_timelines: If True, alert and task items will include
                source_timeline_items from the linked entity
        """
        denormalized = await normalization_service.denormalize_item(
            db,
            item,
            references=references,
        )

        if denormalized.get("type") == "task" and include_linked_timelines:
            denormalized = await self._embed_task_timeline_items(
                db,
                denormalized,
                references=references,
            )
        
        # For alert items, optionally embed timeline items from the linked alert
        if denormalized.get("type") == "alert" and include_linked_timelines:
            denormalized = await self._embed_alert_timeline_items(
                db,
                denormalized,
                references=references,
            )
        
        # For case items, optionally embed timeline items from the linked case
        if denormalized.get("type") == "case" and include_linked_timelines:
            denormalized = await self._embed_case_timeline_items(
                db,
                denormalized,
                references=references,
            )
        
        # Recursively denormalize replies if present
        if "replies" in denormalized and denormalized["replies"]:
            denormalized_replies: Dict[str, Dict[str, Any]] = {}
            for reply in self.iter_items(denormalized["replies"]):
                denormalized_reply = await self._denormalize_item_recursive(
                    db,
                    reply,
                    include_linked_timelines=include_linked_timelines,
                    references=references,
                )
                denormalized_replies[str(denormalized_reply["id"])] = denormalized_reply
            denormalized["replies"] = denormalized_replies
        
        return denormalized

    async def _embed_task_timeline_items(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        """Embed a linked task's timeline after canonical task denormalization."""
        task_id = normalization_service.resolve_task_id(item)
        if task_id is None:
            return item

        task = references.tasks.get(task_id) if references is not None else await db.get(Task, task_id)
        if not task:
            return item

        if task.timeline_items:
            source_items: Dict[str, Dict[str, Any]] = {}
            for task_item in self.iter_items(task.timeline_items):
                denormalized = await self._denormalize_item_recursive(
                    db,
                    task_item,
                    include_linked_timelines=False,
                    references=references,
                )
                source_items[str(denormalized["id"])] = denormalized
            item["source_timeline_items"] = source_items

        return item

    async def _embed_alert_timeline_items(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        """
        Embed timeline items from the linked alert into the alert timeline item.
        
        This is called when include_linked_timelines=True to populate
        the source_timeline_items field on AlertItem.
        
        Args:
            db: Database session
            item: Alert timeline item dict
            
        Returns:
            Item with source_timeline_items populated
        """
        alert_id = item.get("alert_id")
        if not alert_id:
            return item
        
        alert = (
            references.alerts.get(alert_id)
            if references is not None
            else await db.get(Alert, alert_id)
        )
        if not alert:
            logger.warning(f"Alert {alert_id} not found for timeline embedding")
            return item

        item["title"] = alert.title
        item["entity_description"] = alert.description
        item["status"] = alert.status.value if alert.status else None
        item["priority"] = alert.priority.value if alert.priority else None
        item["assignee"] = alert.assignee

        # Embed the alert's timeline items
        if alert.timeline_items:
            source_items: Dict[str, Dict[str, Any]] = {}
            for alert_item in self.iter_items(alert.timeline_items):
                denormalized = await self._denormalize_item_recursive(
                    db,
                    alert_item,
                    include_linked_timelines=False,
                    references=references,
                )
                source_items[str(denormalized["id"])] = denormalized
            item["source_timeline_items"] = source_items
        
        return item

    async def _embed_case_timeline_items(
        self, 
        db: AsyncSession, 
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        """
        Embed timeline items from the linked case into the case timeline item.
        
        This is called when include_linked_timelines=True to populate
        the source_timeline_items field on CaseItem.
        
        Args:
            db: Database session
            item: Case timeline item dict
            
        Returns:
            Item with source_timeline_items populated
        """
        case_id = item.get("case_id")
        if not case_id:
            return item
        
        case = (
            references.cases.get(case_id)
            if references is not None
            else await db.get(Case, case_id)
        )
        if not case:
            logger.warning(f"Case {case_id} not found for timeline embedding")
            return item

        item["title"] = case.title
        item["entity_description"] = case.description
        item["status"] = case.status.value if case.status else None
        item["priority"] = case.priority.value if case.priority else None
        item["assignee"] = case.assignee
        item["created_by"] = case.created_by or item.get("created_by")

        # Embed the case's timeline items
        if case.timeline_items:
            source_items: Dict[str, Dict[str, Any]] = {}
            for case_item in self.iter_items(case.timeline_items):
                denormalized = await self._denormalize_item_recursive(
                    db,
                    case_item,
                    include_linked_timelines=False,
                    references=references,
                )
                source_items[str(denormalized["id"])] = denormalized
            item["source_timeline_items"] = source_items
        
        return item

    def _strip_task_snapshot_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove snapshot fields from a task item before persistence.
        Only keeps reference fields (task_id, type, id, etc.).
        """
        if item.get("type") != "task":
            return item
        
        # Keep only reference fields, strip everything else
        return {k: v for k, v in item.items() if k in TASK_REFERENCE_FIELDS}

    async def _create_task_for_timeline_item(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        case_id: int,
        created_by: str,
    ) -> int:
        """
        Create a Task entity for a new task timeline item.
        
        Returns the task_id of the created task.
        """
        from app.services.task_service import task_service
        from app.models.models import TaskCreate
        from app.models.enums import PICERLStage, Priority, TaskStatus
        
        # Extract task data from the timeline item
        # Prioritize title field, only fall back to description if title is None or empty
        title = item.get("title")
        if not title or not title.strip():
            title = item.get("description")
        if not title or not title.strip():
            title = "Case Task"
        
        # Ensure title doesn't exceed max length
        if len(title) > 200:
            title = title[:200]
        
        # Parse priority
        priority = _coerce_enum(item.get("priority"), Priority) or Priority.MEDIUM
        
        # Parse status
        status = _coerce_enum(item.get("status"), TaskStatus) or TaskStatus.TODO
        
        # Parse due_date
        due_date = parse_optional_utc_datetime(item.get("due_date"))

        picerl_stage = _coerce_enum(item.get("picerl_stage"), PICERLStage)
        
        task_create = TaskCreate(
            title=title,
            description=item.get("description"),
            priority=priority,
            status=status,
            assignee=item.get("assignee"),
            due_date=due_date,
            picerl_stage=picerl_stage,
            case_id=case_id,
            tags=item.get("tags") or [],
        )
        
        task = await task_service.create_task_in_transaction(db, task_create, created_by)
        if task.id is None:
            raise RuntimeError("Task creation did not return an ID")
        return task.id

    async def _update_task_for_timeline_item(
        self,
        db: AsyncSession,
        task_id: int,
        item: Dict[str, Any],
        updated_by: str,
    ) -> tuple[bool, Optional[DeferredAutonomousTaskEnqueue]]:
        """
        Update a Task entity from timeline item data.
        
        Returns whether the update succeeded and any post-commit enqueue.
        """
        from app.services.task_service import task_service
        from app.models.models import TaskUpdate
        from app.models.enums import Priority, TaskStatus
        
        # Build update payload from provided fields
        update_data: Dict[str, Any] = {}
        
        if "title" in item and item["title"]:
            title = item["title"]
            if len(title) > 200:
                title = title[:200]
            update_data["title"] = title
        
        if "description" in item:
            update_data["description"] = item["description"]
        
        if "priority" in item and item["priority"]:
            if priority := _coerce_enum(item["priority"], Priority):
                update_data["priority"] = priority
        
        if "status" in item and item["status"]:
            if status := _coerce_enum(item["status"], TaskStatus):
                update_data["status"] = status
        
        if "assignee" in item:
            update_data["assignee"] = item["assignee"]
        
        if "due_date" in item:
            due_date_val = item["due_date"]
            if due_date_val is None:
                update_data["due_date"] = None
            elif parsed_due_date := parse_optional_utc_datetime(due_date_val):
                update_data["due_date"] = parsed_due_date
        
        if not update_data:
            return True, None  # Nothing to update
        
        task_update = TaskUpdate(**update_data)
        outcome = await task_service.update_task_in_transaction(
            db,
            task_id,
            task_update,
            updated_by,
        )
        if outcome is None:
            return False, None

        task, autonomous_assignee = outcome
        deferred_enqueue = None
        if task.id is not None and autonomous_assignee is not None:
            deferred_enqueue = DeferredAutonomousTaskEnqueue(
                task_id=task.id,
                assignee=autonomous_assignee,
            )
        return True, deferred_enqueue

    # ===== High-level Timeline Operations with Resource Sync =====

    async def add_timeline_item_with_sync(
        self,
        db: AsyncSession,
        entity: Any,
        item: Dict[str, Any],
        created_by: str,
        entity_id: Optional[int] = None,
        entity_type: str = "case",
        preserve_item_id: bool = False,
    ) -> tuple[Dict[str, Any], Optional[int]]:
        """
        Add a timeline item with external resource synchronization.
        
        For task items:
        - Creates the backing Task record
        - Stores only the reference (task_id) in timeline JSON
        
        For other items:
        - Adds normally via add_timeline_item
        
        Args:
            db: Database session
            entity: The case/alert entity to add the item to
            item: The timeline item data
            created_by: Username performing the action
            entity_id: The case_id for task creation (required for tasks)
            entity_type: "case" or "alert" - alerts reject task items
        
        Returns:
            The normalized item dict (with task_id for tasks) and optional
            enrichment queue priority for deferred enqueue after commit.
        
        Raises:
            ValueError: If trying to add a task to an alert
        """
        item_type = item.get("type")
        
        # Alerts do not support task timeline items
        if item_type == "task" and entity_type == "alert":
            raise TimelineValidationError("Task timeline items are not supported on alerts")
        
        # Normalize the item first
        normalized = await self.normalize_item(db, item)
        
        # Handle task creation
        if item_type == "task":
            if not entity_id:
                raise TimelineValidationError(
                    "entity_id (case_id) is required for task timeline items"
                )
            
            # Create the Task entity using the ORIGINAL item (before normalization stripped fields)
            # This sets linked_at which triggers dynamic injection
            task_id = await self._create_task_for_timeline_item(db, item, entity_id, created_by)
            
            # Don't add to timeline JSON - tasks are dynamically injected based on FK relationship
            # Return the reference for the caller
            normalized = self._strip_task_snapshot_fields(normalized)
            normalized["task_id"] = task_id
            return normalized, None
        
        # Add to timeline (for non-task items)
        self.add_timeline_item(
            entity,
            normalized,
            created_by=created_by,
            preserve_item_id=preserve_item_id,
        )

        enrichment_priority: Optional[int] = None
        if entity_id is not None:
            from app.services.enrichment.service import enrichment_service

            enrichment_priority = await enrichment_service.prepare_item_enrichment_enqueue(
                db,
                entity=entity,
                item=normalized,
            )
        
        return normalized, enrichment_priority

    async def update_timeline_item_with_sync(
        self,
        db: AsyncSession,
        entity: Any,
        item_id: str,
        item: Dict[str, Any],
        updated_by: str,
    ) -> Optional[TimelineItemUpdateResult]:
        """
        Update a timeline item with external resource synchronization.
        
        For task items:
        - Routes the update to the Task entity
        - Timeline JSON remains unchanged (just holds reference)
        
        For other items:
        - Updates normally via update_timeline_item
        
        Returns:
            The updated item dict, or None if not found
        """
        # Find the existing item
        existing = self.find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if not existing:
            return None
        
        item_type = existing.get("type")
        
        # Handle task updates
        if item_type == "task":
            task_id = normalization_service.resolve_task_id(existing)
            if task_id:
                # Route task-specific updates (title, status, etc.) to Task entity
                success, autonomous_task_enqueue = await self._update_task_for_timeline_item(
                    db,
                    task_id,
                    item,
                    updated_by,
                )
                if not success:
                    logger.warning(f"Task {task_id} not found, may have been deleted")
            else:
                autonomous_task_enqueue = None
            
            # For tasks, update timeline-specific reference fields in the JSON
            # while leaving task entity fields on the Task row itself.
            timeline_specific_update: Dict[str, Any] = {}
            
            # Include any timeline-specific reference fields that were provided
            for field in ("flagged", "highlighted", "tags", "timestamp"):
                if field in item:
                    timeline_specific_update[field] = item[field]
            
            if timeline_specific_update:
                self.update_timeline_item(entity, item_id, timeline_specific_update)
            
            # Return the existing item (caller should re-read with denormalization)
            return TimelineItemUpdateResult(
                item=existing,
                autonomous_task_enqueue=autonomous_task_enqueue,
            )
        
        # For non-task items, update normally
        normalized = await self.normalize_item(db, item)
        if not self.update_timeline_item(entity, item_id, normalized):
            return None
        
        return TimelineItemUpdateResult(item=normalized)

    async def remove_timeline_item_with_cleanup(
        self,
        db: AsyncSession,
        entity: Any,
        item_id: str,
        removed_by: str,
    ) -> Optional[TimelineRemovalCleanup]:
        """
        Remove a timeline item and prepare any external cleanup.
        
        Handles:
        - Attachments: Defers storage deletion until after the database commit
        - Tasks: Deletes the Task record in the caller's transaction
        
        Returns:
            Deferred cleanup if the item was removed, otherwise ``None``.
        """
        items = getattr(entity, "timeline_items", None)
        if not items:
            return None
        
        # Find the item first
        item_to_remove = self.find_item_by_id(items, item_id)
        if not item_to_remove:
            return None

        item_type = item_to_remove.get("type")
        storage_key: Optional[str] = None
        if item_type == "attachment":
            candidate = item_to_remove.get("storage_key")
            if isinstance(candidate, str) and candidate:
                storage_key = candidate
        
        elif item_type == "task":
            task_id = normalization_service.resolve_task_id(item_to_remove)
            if task_id:
                from app.services.task_service import task_service

                if not await task_service.delete_task_in_transaction(db, task_id, removed_by):
                    raise TimelineValidationError(f"Task {task_id} not found")
        
        # Remove from timeline
        if not self.remove_timeline_item(entity, item_id):
            return None
        return TimelineRemovalCleanup(storage_key=storage_key)

    def find_item_by_id(self, items: Any, item_id: str) -> Optional[Dict[str, Any]]:
        """Recursively find a timeline item by ID, supporting nested replies."""
        if not items:
            return None
        if isinstance(items, dict) and item_id in items:
            item = items[item_id]
            return item if isinstance(item, dict) else None
        for item in self.iter_items(items):
            if item.get("id") == item_id:
                return item
            # Check replies recursively
            found = self.find_item_by_id(item.get("replies") or {}, item_id)
            if found:
                return found
        return None

    def _add_item_metadata(self, item: Dict[str, Any], created_by: str) -> None:
        if not item.get("created_at"):
            item["created_at"] = datetime.now(timezone.utc).isoformat()
        item["created_by"] = created_by
    
    @classmethod
    def _serialize_datetime_value(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                key: cls._serialize_datetime_value(child)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [cls._serialize_datetime_value(child) for child in value]
        return value

    def _serialize_datetime_fields(self, item: Dict[str, Any]) -> None:
        """Convert datetime objects at every JSON nesting depth to ISO strings."""
        for key, value in item.items():
            item[key] = self._serialize_datetime_value(value)

    def add_timeline_item(
        self,
        entity: Any,
        item: Dict[str, Any],
        created_by: str,
        *,
        preserve_item_id: bool = False,
    ) -> None:
        """
        Mutate entity to append a normalized item with metadata; does not commit.
        
        If item has a parent_id, this will add it as a reply to the parent item.
        Otherwise, it will add it as a top-level timeline item.
        """
        timeline_items = self._ensure_storage_items(entity)
        server_prepared_attachment = item.get("type") == "attachment" and bool(item.get("storage_key"))
        if server_prepared_attachment or preserve_item_id:
            self._ensure_item_id(item)
        else:
            self._assign_new_item_ids(item)
        self._add_item_metadata(item, created_by)
        # Ensure all datetime fields are serialized to ISO strings before storing in JSON column
        self._serialize_datetime_fields(item)
        self._coerce_item_for_storage(item)
        
        # Check if this is a reply (has parent_id)
        parent_id = item.get("parent_id")
        if parent_id:
            # Find parent and add as reply
            if self._add_reply_to_parent(timeline_items, parent_id, item):
                flag_modified(entity, "timeline_items")
                if hasattr(entity, "updated_at"):
                    setattr(entity, "updated_at", datetime.now(timezone.utc))
                return
            # Parent not found: preserve the established graceful fallback and
            # store the item at the top level.
        
        # Add as top-level item
        if str(item["id"]) in timeline_items:
            raise TimelineValidationError("Timeline item ID collision")
        timeline_items[str(item["id"])] = item
        # Mark the JSON column as modified so SQLAlchemy knows to update it
        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            setattr(entity, "updated_at", datetime.now(timezone.utc))
    
    def _add_reply_to_parent(self, items: Any, parent_id: str, reply: Dict[str, Any]) -> bool:
        """
        Recursively search for parent item and add reply to it.
        Returns True if parent found and reply added, False otherwise.
        """
        for item in self.iter_items(items):
            if item.get("id") == parent_id:
                # Found parent - add reply
                existing_replies = item.get("replies")
                if isinstance(existing_replies, dict):
                    existing_replies[str(reply["id"])] = reply
                elif isinstance(existing_replies, list):
                    existing_replies.append(reply)
                elif isinstance(items, dict):
                    item["replies"] = {str(reply["id"]): reply}
                else:
                    item["replies"] = [reply]
                return True
            
            # Check nested replies
            if item.get("replies"):
                if self._add_reply_to_parent(item["replies"], parent_id, reply):
                    return True
        
        return False

    def update_timeline_item(
        self,
        entity: Any,
        item_id: str,
        updated: Dict[str, Any],
    ) -> bool:
        """
        Update a timeline item by id; preserves created_* fields; returns True if found and updated.
        Supports nested replies at any depth.
        """
        items = self._ensure_storage_items(entity)
        if not items:
            return False
        
        # Try to update recursively
        if self._update_item_recursive(items, item_id, updated):
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                setattr(entity, "updated_at", datetime.now(timezone.utc))
            return True
        
        return False
    
    def _build_updated_item(self, item: Dict[str, Any], item_id: str, updated: Dict[str, Any]) -> Dict[str, Any]:
        created_at = item.get("created_at") or item.get("timestamp") or datetime.now(timezone.utc).isoformat()
        created_by = item.get("created_by")
        existing_replies = item.get("replies")

        new_item = {**item, **updated}
        new_item["id"] = item_id
        new_item["created_at"] = created_at
        new_item["created_by"] = created_by
        if existing_replies is not None:
            new_item["replies"] = existing_replies
        self._serialize_datetime_fields(new_item)
        self._coerce_item_for_storage(new_item)
        return new_item

    def _update_item_recursive(
        self,
        items: Any,
        item_id: str,
        updated: Dict[str, Any],
    ) -> bool:
        """Recursively search and update a timeline item by ID."""
        if isinstance(items, dict):
            if item_id in items:
                items[item_id] = self._build_updated_item(items[item_id], item_id, updated)
                return True

            for item in self.iter_items(items):
                replies = item.get("replies")
                if replies and self._update_item_recursive(replies, item_id, updated):
                    return True

            return False

        if isinstance(items, list):
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue

                if item.get("id") == item_id:
                    items[idx] = self._build_updated_item(item, item_id, updated)
                    return True

                replies = item.get("replies")
                if replies and self._update_item_recursive(replies, item_id, updated):
                    return True

        return False

    def remove_timeline_item(self, entity: Any, item_id: str) -> bool:
        """
        Remove a timeline item by id; returns True if item removed.
        Supports removing nested replies at any depth.
        """
        items = self._ensure_storage_items(entity)
        if not items:
            return False
        
        if self._remove_item_recursive(items, item_id):
            # Mark the JSON column as modified so SQLAlchemy knows to update it
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                setattr(entity, "updated_at", datetime.now(timezone.utc))
            return True
        
        return False
    
    def _remove_item_recursive(self, items: Any, item_id: str) -> bool:
        """Recursively search and remove a timeline item by ID."""
        if isinstance(items, dict):
            if item_id in items:
                del items[item_id]
                return True
        elif isinstance(items, list):
            for index, item in enumerate(items):
                if isinstance(item, dict) and item.get("id") == item_id:
                    del items[index]
                    return True
        else:
            return False

        for item in self.iter_items(items):
            replies = item.get("replies")
            if replies and self._remove_item_recursive(replies, item_id):
                return True

        return False


timeline_service = TimelineService()
