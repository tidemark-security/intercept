from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime, timezone
import hashlib

from app.models.models import Actor, ActorSnapshot, Task
from app.models.enums import ActorType


class NormalizationService:
    """Encapsulates normalization and denormalization for timeline items
    involving Actors, Alerts, and Cases.
    """

    async def normalize_actor_item(
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
            return await self._normalize_case(db, item)
        if t == "task":
            return await self._normalize_task(db, item)
        if t == "ttp":
            return self._normalize_ttp(item)
        return item

    async def denormalize_actor_item(
        self,
        db: AsyncSession,
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Populate denormalized fields on an actor timeline item for API responses."""
        t = item.get("type")
        # Handle all actor types: internal_actor, external_actor, threat_actor
        if t and ("actor" in t):
            return await self._denormalize_actor(db, item)
        if t == "alert":
            return await self._denormalize_alert(db, item)
        if t == "case":
            return await self._denormalize_case(db, item)
        if t == "task":
            return await self._denormalize_task(db, item)
        if t == "ttp":
            return self._denormalize_ttp(item)
        return item

    async def _normalize_task(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)

        task_id = normalized.get("task_id")
        if isinstance(task_id, str) and task_id.isdigit():
            normalized["task_id"] = int(task_id)

        if task_id is None:
            human_id = normalized.get("task_human_id")
            if isinstance(human_id, str) and human_id.startswith("TSK-"):
                try:
                    normalized["task_id"] = int(human_id[4:])
                except ValueError:
                    pass

        # Strip denormalized fields to keep canonical data in the Task table
        for field in ("task_human_id", "title", "description", "status", "priority", "assignee", "due_date"):
            normalized.pop(field, None)

        return normalized

    async def _denormalize_task(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        denorm = dict(item)
        task_id = denorm.get("task_id")

        if isinstance(task_id, str) and task_id.isdigit():
            task_id = int(task_id)
            denorm["task_id"] = task_id

        if not isinstance(task_id, int):
            return denorm

        task = await db.get(Task, task_id)
        if not task:
            return denorm

        denorm["task_id"] = task.id
        denorm["task_human_id"] = f"TSK-{task.id:07d}"
        denorm["title"] = task.title
        denorm["description"] = task.description or task.title
        denorm["status"] = task.status.value if isinstance(task.status, Enum) else task.status
        denorm["priority"] = task.priority.value if isinstance(task.priority, Enum) else task.priority
        denorm["assignee"] = task.assignee

        if task.due_date:
            denorm["due_date"] = task.due_date.isoformat()
        else:
            denorm.pop("due_date", None)

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
        from app.services.mitre_service import mitre_service
        
        denorm = dict(item)
        mitre_id = denorm.get("mitre_id")
        
        if not mitre_id:
            return denorm
        
        # Look up the ATT&CK object (cached for performance)
        attack_obj = mitre_service.get_attack_object_cached(mitre_id)
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
        # Map timeline item 'type' field to actor_type enum
        # e.g., 'internal_actor' -> ActorType.INTERNAL
        item_type = item.get("type")
        if item_type == "internal_actor":
            item["actor_type"] = ActorType.INTERNAL
        elif item_type == "external_actor":
            item["actor_type"] = ActorType.EXTERNAL
        elif item_type == "threat_actor":
            item["actor_type"] = ActorType.EXTERNAL_THREAT
        
        # Accept either actor_id or denormalized identity
        actor_id = item.get("actor_id")
        if actor_id is None:
            actor_id = await self._get_or_create_actor(db, item)

        # Build snapshot payload from known fields
        snapshot_payload = {
            k: item.get(k)
            for k in (
                "actor_type",
                "user_id",
                "name",
                "title",
                "org",
                "contact_phone",
                "contact_email",
            )
            if item.get(k) is not None
        }

        snapshot_hash = await self._get_or_create_snapshot(db, actor_id, snapshot_payload)

        # Compose normalized item
        normalized = dict(item)
        normalized["actor_id"] = actor_id
        normalized["snapshot_hash"] = snapshot_hash

        # Remove denormalized fields from storage to avoid bloat
        for k in ("user_id", "name", "title", "org", "contact_phone", "contact_email"):
            normalized.pop(k, None)

        return normalized

    async def _denormalize_actor(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = item.get("actor_id")
        snapshot_hash = item.get("snapshot_hash")
        if actor_id is None:
            return item
        actor = await db.get(Actor, actor_id)
        if actor is None:
            return item
        denorm = dict(item)
        denorm.setdefault("actor_type", actor.actor_type)
        payload: Optional[Dict[str, Any]] = None
        if snapshot_hash:
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
        return denorm

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
            result = await db.execute(select(Alert).where(Alert.alert_id == alert_id_val))
            alert = result.scalar_one_or_none()
            if alert:
                normalized["alert_id"] = alert.id
            else:
                # If not found, drop it to avoid dangling reference
                normalized.pop("alert_id", None)

        # Strip denormalized fields
        for k in ("title", "priority", "assignee"):
            normalized.pop(k, None)
        return normalized

    async def _denormalize_alert(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        from app.models.models import Alert
        denorm = dict(item)
        pk = denorm.get("alert_id")
        alert = await db.get(Alert, pk) if isinstance(pk, int) else None
        if alert:
            # Populate live denormalized fields (source of truth is Alert entity)
            denorm["title"] = alert.title
            denorm["priority"] = alert.priority
            denorm["assignee"] = alert.assignee
            denorm["status"] = alert.status.value if isinstance(alert.status, Enum) else alert.status
        return denorm

    # --- Case helpers ---
    async def _normalize_case(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        # Case item requires case_id already (per contract)
        normalized = dict(item)
        # Strip denormalized fields
        for k in ("title", "priority", "assignee"):
            normalized.pop(k, None)
        return normalized

    async def _denormalize_case(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        from app.models.models import Case
        denorm = dict(item)
        case = await db.get(Case, denorm.get("case_id")) if denorm.get("case_id") is not None else None
        if case:
            # Populate live denormalized fields (source of truth is Case entity)
            denorm["title"] = case.title
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

        query = None
        if actor_type == ActorType.INTERNAL:
            if not user_id:
                raise ValueError("user_id is required for internal actor")
            query = select(Actor).where(Actor.actor_type == ActorType.INTERNAL, Actor.user_id == user_id)
        else:
            # Treat missing actor_type as external by default if name exists
            query = select(Actor).where(Actor.actor_type == ActorType.EXTERNAL, Actor.name == name, Actor.org == org)

        result = await db.execute(query)
        actor = result.scalar_one_or_none()
        if actor:
            return actor.id  # type: ignore[return-value]

        actor = Actor(
            actor_type=actor_type or ActorType.EXTERNAL,
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

    async def _get_or_create_snapshot(self, db: AsyncSession, actor_id: int, payload: Dict[str, Any]) -> str:
        """Ensure a snapshot exists for the given payload; return its content hash."""
        # Stable JSON string for hashing
        import json
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
