from __future__ import annotations

from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any
from enum import Enum
import hashlib
import json

from app.core.entity_ids import TASK_PREFIX, format_entity_id
from app.core.id_parser import EntityIdParseError, parse_entity_id
from app.models.models import Actor, ActorSnapshot, Alert, Case, Task
from app.models.enums import ActorType


INTERNAL_ACTOR_ENRICHMENT_FIELD_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "google_workspace": {
        "name": ("display_name",),
        "title": ("job_title",),
        "org": ("organization", "department", "org_unit_path"),
        "contact_phone": ("phone",),
        "contact_email": ("primary_email",),
    },
    "entra_id": {
        "name": ("display_name",),
        "title": ("job_title",),
        "org": ("department", "office"),
        "contact_phone": ("mobile_phone", "business_phones"),
        "contact_email": ("email", "upn"),
    },
    "ldap": {
        "name": ("display_name",),
        "title": ("job_title",),
        "org": ("company", "department", "office"),
        "contact_phone": ("phone", "mobile"),
        "contact_email": ("email", "upn"),
    },
}

ACTOR_SNAPSHOT_FIELDS = (
    "actor_type",
    "user_id",
    "name",
    "title",
    "org",
    "contact_phone",
    "contact_email",
)

LINKED_ENTITY_DERIVED_FIELDS = frozenset(
    {
        "title",
        "entity_description",
        "status",
        "priority",
        "assignee",
        "source_timeline_items",
    }
)

TASK_DERIVED_FIELDS = LINKED_ENTITY_DERIVED_FIELDS | {
    "task_human_id",
    "due_date",
    "picerl_stage",
    "source_runbook",
}


class NormalizationValidationError(ValueError):
    """Timeline reference data is missing or invalid for normalization."""


@dataclass(slots=True)
class TimelineReferenceIndex:
    """Strong references used while denormalizing one timeline response."""

    actors: Dict[int, Actor] = field(default_factory=dict)
    actor_snapshots: Dict[tuple[int, str], ActorSnapshot] = field(default_factory=dict)
    alerts: Dict[int, Alert] = field(default_factory=dict)
    cases: Dict[int, Case] = field(default_factory=dict)
    tasks: Dict[int, Task] = field(default_factory=dict)


class NormalizationService:
    """Normalize first-class entity references embedded in timeline items."""

    @staticmethod
    def _strip_linked_entity_fields(
        item: Dict[str, Any],
        derived_fields: frozenset[str] = LINKED_ENTITY_DERIVED_FIELDS,
    ) -> Dict[str, Any]:
        """Keep canonical identity and analyst-authored link metadata only."""
        return {
            field: value
            for field, value in item.items()
            if field not in derived_fields
        }

    async def normalize_item(
        self,
        db: AsyncSession,
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Given an inbound timeline item dict (possibly with denormalized fields),
        ensure actor exists, create/find snapshot, and return a normalized item
        referencing actor_id and snapshot_hash while stripping denormalized fields.
        """
        t = item.get("type")
        # Handle all actor types: internal_actor, external_actor, threat_actor
        if t and ("actor" in t):
            return await self._normalize_actor(db, item)
        if t == "alert":
            return await self._normalize_alert(db, item)
        if t == "case":
            return self._normalize_case(item)
        if t == "task":
            return self._normalize_task(item)
        if t == "ttp":
            return self._normalize_ttp(item)
        return item

    async def denormalize_item(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        """Populate denormalized fields on an actor timeline item for API responses."""
        t = item.get("type")
        # Handle all actor types: internal_actor, external_actor, threat_actor
        if t and ("actor" in t):
            return await self._denormalize_actor(db, item, references=references)
        if t == "alert":
            return await self._denormalize_alert(db, item, references=references)
        if t == "case":
            return await self._denormalize_case(db, item, references=references)
        if t == "task":
            return await self._denormalize_task(db, item, references=references)
        if t == "ttp":
            return self._denormalize_ttp(item)
        return item

    def resolve_task_id(self, item: Dict[str, Any]) -> Optional[int]:
        """Resolve a task reference from either its numeric or human-readable field."""
        for field in ("task_id", "task_human_id"):
            raw_id = item.get(field)
            if isinstance(raw_id, bool) or raw_id is None:
                continue
            if isinstance(raw_id, int):
                if raw_id > 0:
                    return raw_id
                continue
            if isinstance(raw_id, str):
                try:
                    numeric_id, _ = parse_entity_id(raw_id, "task")
                except EntityIdParseError:
                    continue
                if numeric_id > 0:
                    return numeric_id
        return None

    def _normalize_task(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        task_id = self.resolve_task_id(normalized)
        if task_id is not None:
            normalized["task_id"] = task_id

        return self._strip_linked_entity_fields(normalized, TASK_DERIVED_FIELDS)

    async def _denormalize_task(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        denorm = dict(item)
        task_id = self.resolve_task_id(denorm)
        if task_id is None:
            return denorm

        task = references.tasks.get(task_id) if references is not None else await db.get(Task, task_id)
        if not task:
            return denorm

        denorm["task_id"] = task.id
        denorm["task_human_id"] = format_entity_id(task.id, TASK_PREFIX)
        denorm["title"] = task.title
        denorm["entity_description"] = task.description
        denorm["status"] = task.status.value if isinstance(task.status, Enum) else task.status
        denorm["priority"] = task.priority.value if isinstance(task.priority, Enum) else task.priority
        denorm["assignee"] = task.assignee
        denorm["due_date"] = task.due_date.isoformat() if task.due_date else None
        denorm["picerl_stage"] = (
            task.picerl_stage.value
            if isinstance(task.picerl_stage, Enum)
            else task.picerl_stage
        )
        denorm["source_runbook"] = task.source_runbook
        denorm["created_at"] = (
            task.created_at.isoformat() if task.created_at else denorm.get("created_at")
        )
        denorm["created_by"] = task.created_by or denorm.get("created_by")

        return denorm

    # --- TTP (MITRE ATT&CK) helpers ---
    def _normalize_ttp(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a TTP timeline item by stripping denormalized ATT&CK fields.
        
        Only the mitre_id is stored; the rest is populated dynamically from
        the MITRE ATT&CK STIX bundle on read.
        """
        normalized = dict(item)
        
        # Ensure mitre_id is present and properly formatted
        mitre_id = normalized.get("mitre_id")
        if mitre_id and isinstance(mitre_id, str):
            normalized["mitre_id"] = mitre_id.upper().strip()
        
        # Strip denormalized fields - these come from the ATT&CK database
        for field in ("title", "technique", "tactic", "url", "tactics", "is_subtechnique", 
                      "parent_technique", "object_type", "aliases", "software_type"):
            normalized.pop(field, None)
        
        return normalized
    
    def _denormalize_ttp(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Populate TTP timeline item fields from the MITRE ATT&CK database.
        
        Uses mitre_id to fetch live data from the STIX bundle. The ATT&CK
        database is the source of truth for technique names, tactics, URLs, etc.
        """
        from app.services.mitre_service import MitreDataUnavailableError, mitre_service
        
        denorm = dict(item)
        mitre_id = denorm.get("mitre_id")
        
        if not mitre_id:
            return denorm
        
        # Look up the ATT&CK object (cached for performance)
        try:
            attack_obj = mitre_service.get_attack_object_cached(mitre_id)
        except MitreDataUnavailableError:
            # Timeline reads remain usable when the optional ATT&CK bundle is absent.
            return denorm
        if not attack_obj:
            # ATT&CK ID not found - leave item as-is (may have stale snapshot data)
            return denorm
        
        # Populate from ATT&CK database (source of truth)
        denorm["title"] = attack_obj.get("name")
        denorm["url"] = attack_obj.get("url")
        denorm["object_type"] = attack_obj.get("object_type")
        denorm["mitre_description"] = attack_obj.get("description")
        
        # For techniques, add tactic information
        if attack_obj.get("object_type") == "technique":
            tactics = attack_obj.get("tactics", [])
            denorm["tactics"] = tactics
            # Keep tactic as first tactic for backward compatibility
            denorm["tactic"] = tactics[0] if tactics else None
            denorm["technique"] = attack_obj.get("name")
            denorm["is_subtechnique"] = attack_obj.get("is_subtechnique", False)
            denorm["parent_technique"] = attack_obj.get("parent_technique")
        
        # For groups/software, add aliases
        if attack_obj.get("aliases"):
            denorm["aliases"] = attack_obj.get("aliases")
        
        # For software, add type
        if attack_obj.get("software_type"):
            denorm["software_type"] = attack_obj.get("software_type")
        
        return denorm

    # --- Actor helpers ---
    async def _normalize_actor(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(item)
        # Map timeline item 'type' field to actor_type enum
        # e.g., 'internal_actor' -> ActorType.INTERNAL
        item_type = item.get("type")
        if item_type == "internal_actor":
            item["actor_type"] = ActorType.INTERNAL
        elif item_type == "external_actor":
            item["actor_type"] = ActorType.EXTERNAL
        elif item_type == "threat_actor":
            item["actor_type"] = ActorType.EXTERNAL_THREAT

        self._coalesce_inbound_actor_aliases(item)
        
        # Accept either actor_id or denormalized identity
        actor_id = item.get("actor_id")
        if actor_id is None:
            actor_id = await self._get_or_create_actor(db, item)
            actor = None
        else:
            actor = await db.get(Actor, actor_id)
            if actor is None:
                raise NormalizationValidationError(f"Actor {actor_id} not found")

        # Build snapshot payload from known fields
        snapshot_payload = {
            k: item.get(k)
            for k in ACTOR_SNAPSHOT_FIELDS
            if item.get(k) is not None
        }
        if actor is not None:
            canonical_payload = self._actor_snapshot_payload(actor)
            for key, value in canonical_payload.items():
                snapshot_payload.setdefault(key, value)

        snapshot_hash = await self._get_or_create_snapshot(db, actor_id, snapshot_payload)

        # Compose normalized item
        normalized = dict(item)
        normalized["actor_id"] = actor_id
        normalized["snapshot_hash"] = snapshot_hash

        # Remove denormalized fields from storage to avoid bloat
        for k in (
            "user_id",
            "name",
            "display_name",
            "displayName",
            "full_name",
            "fullName",
            "username",
            "userPrincipalName",
            "upn",
            "title",
            "org",
            "contact_phone",
            "contact_email",
        ):
            normalized.pop(k, None)

        return normalized

    def _coalesce_inbound_actor_aliases(self, item: Dict[str, Any]) -> None:
        """Accept common external identity field names before snapshotting."""
        if item.get("name") in (None, ""):
            for alias in ("display_name", "displayName", "full_name", "fullName"):
                value = item.get(alias)
                if isinstance(value, str) and value.strip():
                    item["name"] = value.strip()
                    break

        if item.get("user_id") in (None, ""):
            for alias in ("username", "userPrincipalName", "upn"):
                value = item.get(alias)
                if isinstance(value, str) and value.strip():
                    item["user_id"] = value.strip()
                    break

    async def _denormalize_actor(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        actor_id = item.get("actor_id")
        snapshot_hash = item.get("snapshot_hash")
        if actor_id is None:
            return item
        actor = references.actors.get(actor_id) if references is not None else await db.get(Actor, actor_id)
        if actor is None:
            return item
        denorm = dict(item)
        denorm.setdefault("actor_type", actor.actor_type)
        payload: Optional[Dict[str, Any]] = None
        if snapshot_hash:
            if references is not None:
                snapshot = references.actor_snapshots.get((actor_id, snapshot_hash))
                payload = snapshot.snapshot if snapshot is not None else None
            else:
                payload = await self._get_snapshot_payload(db, actor_id, snapshot_hash)
        if payload is None:
            payload = {
                "actor_type": actor.actor_type,
                "user_id": actor.user_id,
                "name": actor.name,
                "title": actor.title,
                "org": actor.org,
                "contact_phone": actor.contact_phone,
                "contact_email": actor.contact_email,
            }
        for k, v in payload.items():
            if v is not None:
                denorm[k] = v
        self._coalesce_internal_actor_enrichments(denorm)
        return denorm

    def _coalesce_internal_actor_enrichments(self, item: Dict[str, Any]) -> None:
        if item.get("type") != "internal_actor":
            return

        enrichments = item.get("enrichments")
        if not isinstance(enrichments, dict):
            return

        for provider_id, field_map in INTERNAL_ACTOR_ENRICHMENT_FIELD_MAP.items():
            payload = enrichments.get(provider_id)
            if not isinstance(payload, dict):
                continue
            for target_field, source_fields in field_map.items():
                current_value = item.get(target_field)
                if isinstance(current_value, str) and current_value.strip():
                    continue
                if current_value not in (None, ""):
                    continue

                enriched_value = self._get_first_enrichment_value(payload, source_fields)
                if enriched_value:
                    item[target_field] = enriched_value

    def _get_first_enrichment_value(
        self,
        payload: Dict[str, Any],
        source_fields: tuple[str, ...],
    ) -> str | None:
        for source_field in source_fields:
            enriched_value = payload.get(source_field)
            if isinstance(enriched_value, str):
                enriched_value = enriched_value.strip()
                if enriched_value:
                    return enriched_value
            elif isinstance(enriched_value, list):
                for entry in enriched_value:
                    if isinstance(entry, str) and entry.strip():
                        return entry.strip()
        return None

    # --- Alert helpers ---
    async def _normalize_alert(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an alert timeline item so it references alerts.id in alert_id.
        Backward compatibility: if a string business ID is provided, look up the alert by
        Alert.alert_id and store its integer PK in alert_id.
        """
        from app.models.models import Alert
        normalized = dict(item)
        alert_id_val = normalized.get("alert_id")

        # If alert_id is a string (legacy business id), resolve to PK
        if isinstance(alert_id_val, str) and alert_id_val:
            try:
                numeric_id, _ = parse_entity_id(alert_id_val, "alert")
            except EntityIdParseError:
                numeric_id = None

            alert = await db.get(Alert, numeric_id) if isinstance(numeric_id, int) else None
            if alert:
                normalized["alert_id"] = alert.id
            else:
                # If not found, drop it to avoid dangling reference
                normalized.pop("alert_id", None)

        return self._strip_linked_entity_fields(normalized)

    async def _denormalize_alert(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        denorm = dict(item)
        pk = denorm.get("alert_id")
        if isinstance(pk, int):
            alert = references.alerts.get(pk) if references is not None else await db.get(Alert, pk)
        else:
            alert = None
        if alert:
            # Populate live denormalized fields (source of truth is Alert entity)
            denorm["title"] = alert.title
            denorm["entity_description"] = alert.description
            denorm["priority"] = alert.priority
            denorm["assignee"] = alert.assignee
            denorm["status"] = alert.status.value if isinstance(alert.status, Enum) else alert.status
        return denorm

    # --- Case helpers ---
    def _normalize_case(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Case item requires case_id already (per contract)
        return self._strip_linked_entity_fields(item)

    async def _denormalize_case(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        references: TimelineReferenceIndex | None = None,
    ) -> Dict[str, Any]:
        denorm = dict(item)
        case_id = denorm.get("case_id")
        if isinstance(case_id, int):
            case = references.cases.get(case_id) if references is not None else await db.get(Case, case_id)
        else:
            case = None
        if case:
            # Populate live denormalized fields (source of truth is Case entity)
            denorm["title"] = case.title
            denorm["entity_description"] = case.description
            denorm["priority"] = case.priority
            denorm["assignee"] = case.assignee
            denorm["status"] = case.status.value if isinstance(case.status, Enum) else case.status
        return denorm

    async def _get_or_create_actor(self, db: AsyncSession, item: Dict[str, Any]) -> int:
        """Find or create an Actor using stable identity (user_id for internal; name+org for external)."""
        actor_type = item.get("actor_type")
        user_id = item.get("user_id")
        name = item.get("name")
        org = item.get("org")

        resolved_actor_type = actor_type or ActorType.EXTERNAL
        if resolved_actor_type == ActorType.INTERNAL:
            if not user_id:
                raise NormalizationValidationError(
                    "user_id is required for internal actor"
                )
            query = select(Actor).where(Actor.actor_type == ActorType.INTERNAL, Actor.user_id == user_id)
        else:
            query = select(Actor).where(
                Actor.actor_type == resolved_actor_type,
                Actor.name == name,
                Actor.org == org,
            )

        result = await db.execute(query)
        actor = result.scalar_one_or_none()
        if actor:
            return actor.id  # type: ignore[return-value]

        actor = Actor(
            actor_type=resolved_actor_type,
            user_id=user_id,
            name=name,
            title=item.get("title"),
            org=org,
            contact_phone=item.get("contact_phone"),
            contact_email=item.get("contact_email"),
        )
        db.add(actor)
        await db.flush()
        return actor.id  # type: ignore[return-value]

    @staticmethod
    def _actor_snapshot_payload(actor: Actor) -> Dict[str, Any]:
        return {
            field_name: getattr(actor, field_name)
            for field_name in ACTOR_SNAPSHOT_FIELDS
            if getattr(actor, field_name) is not None
        }

    async def _get_or_create_snapshot(self, db: AsyncSession, actor_id: int, payload: Dict[str, Any]) -> str:
        """Ensure a snapshot exists for the given payload; return its content hash."""
        # Stable JSON string for hashing
        json_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(json_bytes).hexdigest()

        query = select(ActorSnapshot).where(
            ActorSnapshot.actor_id == actor_id, ActorSnapshot.snapshot_hash == digest
        )
        result = await db.execute(query)
        snap = result.scalar_one_or_none()
        if snap:
            return digest

        snap = ActorSnapshot(
            actor_id=actor_id,
            snapshot_hash=digest,
            snapshot=payload,
        )
        db.add(snap)
        await db.flush()
        return digest

    async def _get_snapshot_payload(self, db: AsyncSession, actor_id: int, snapshot_hash: str) -> Optional[Dict[str, Any]]:
        query = select(ActorSnapshot).where(
            ActorSnapshot.actor_id == actor_id, ActorSnapshot.snapshot_hash == snapshot_hash
        )
        result = await db.execute(query)
        snap = result.scalar_one_or_none()
        return snap.snapshot if snap else None


normalization_service = NormalizationService()
