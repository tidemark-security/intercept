from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import col, select

from app.models.enums import Priority
from app.models.enums import RealtimeEventType
from app.models.models import (
    Alert,
    Case,
    EnrichmentAlias,
    EnrichmentAliasCreate,
    EnrichmentAliasRead,
    EnrichmentAliasUpdate,
    EnrichmentCacheEntry,
    EnrichmentProviderStatusRead,
    Task,
)
from app.services.enrichment.base import AliasMapping, EnrichmentResult
from app.services.enrichment.cache import enrichment_cache
from app.services.enrichment.registry import enrichment_registry
from app.services.queue_status_service import QueueStatusService
from app.services.realtime_service import emit_event
from app.services.settings_service import SettingsService
from app.services.tag_filter_utils import normalize_persisted_tags
from app.services.task_queue_service import get_task_queue_service

logger = logging.getLogger(__name__)


class EnrichmentError(ValueError):
    """Base class for expected enrichment request failures."""


class EnrichmentValidationError(EnrichmentError):
    """Raised when an enrichment request cannot be performed as submitted."""


class EnrichmentNotFoundError(EnrichmentError):
    """Raised when an enrichment target does not exist."""


PRIORITY_TO_QUEUE_PRIORITY = {
    Priority.INFO: 0,
    Priority.LOW: 10,
    Priority.MEDIUM: 25,
    Priority.HIGH: 50,
    Priority.CRITICAL: 75,
    Priority.EXTREME: 100,
}

ACTIVE_ENRICHMENT_STATUSES = {"pending", "in_progress"}
ENRICHMENT_REQUEST_ID_FIELD = "enrichment_request_id"

_ENTITY_TYPE_TO_TABLE: Dict[str, str] = {
    "case": "cases",
    "alert": "alerts",
    "task": "tasks",
}


def _remove_present(mapping: Dict[str, Any], key: str) -> bool:
    """Remove a key and report structural change, including explicit nulls."""
    if key not in mapping:
        return False
    del mapping[key]
    return True


class EnrichmentService:
    """Coordinates provider lookup, caching, queueing, and alias persistence."""

    def _clear_item_enrichment_state(self, item: Dict[str, Any]) -> bool:
        changed = False
        if _remove_present(item, "enrichment_status"):
            changed = True
        if _remove_present(item, "enrichment_task_id"):
            changed = True
        if _remove_present(item, ENRICHMENT_REQUEST_ID_FIELD):
            changed = True

        enrichments = item.get("enrichments")
        if isinstance(enrichments, dict):
            if enrichments:
                changed = True
            item["enrichments"] = {}
        elif "enrichments" in item:
            item["enrichments"] = {}
            changed = True

        return changed

    def _clear_item_enrichment_error(self, item: Dict[str, Any]) -> bool:
        enrichments = item.get("enrichments")
        if not isinstance(enrichments, dict):
            return False
        if not _remove_present(enrichments, "system"):
            return False
        if not enrichments:
            item["enrichments"] = {}
        return True

    def _link_enrichment_task(self, item: Dict[str, Any], task_id: str) -> bool:
        changed = False
        if item.get("enrichment_task_id") != task_id:
            item["enrichment_task_id"] = task_id
            changed = True
        if self._clear_item_enrichment_error(item):
            changed = True
        return changed

    def _normalize_request_id(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    def _matches_enrichment_request(
        self,
        item: Dict[str, Any],
        *,
        task_id: str | None,
        enrichment_request_id: str | None,
    ) -> bool:
        """Match one worker to the active item generation it was created for.

        Jobs created before request IDs were introduced remain eligible only
        while the stored item is also legacy (it has no request ID). Once a
        versioned request exists, an unversioned worker can never mutate it.
        """
        status = str(item.get("enrichment_status") or "").strip().lower()
        if status not in ACTIVE_ENRICHMENT_STATUSES:
            return False

        stored_request_id = self._normalize_request_id(
            item.get(ENRICHMENT_REQUEST_ID_FIELD)
        )
        worker_request_id = self._normalize_request_id(enrichment_request_id)
        if stored_request_id != worker_request_id:
            return False

        linked_task_id = str(item.get("enrichment_task_id") or "").strip()
        worker_task_id = str(task_id or "").strip()
        if not worker_task_id:
            return not linked_task_id
        return not linked_task_id or linked_task_id == worker_task_id

    def _set_item_enrichment_failed(
        self,
        item: Dict[str, Any],
        *,
        error_message: str | None = None,
    ) -> bool:
        changed = False
        if item.get("enrichment_status") != "failed":
            item["enrichment_status"] = "failed"
            changed = True
        if _remove_present(item, "enrichment_task_id"):
            changed = True
        if _remove_present(item, ENRICHMENT_REQUEST_ID_FIELD):
            changed = True
        if error_message:
            enrichments = item.setdefault("enrichments", {})
            system_enrichment = enrichments.get("system")
            existing_error = (
                system_enrichment.get("error")
                if isinstance(system_enrichment, dict)
                else None
            )
            if existing_error != error_message:
                enrichments["system"] = {"error": error_message}
                changed = True
        return changed

    def _get_ignore_enrichment_tag(self, raw_value: Any) -> str:
        normalized = normalize_persisted_tags([str(raw_value)]) if raw_value else []
        return normalized[0] if normalized else ""

    def _item_has_tag(self, item: Dict[str, Any], tag: str) -> bool:
        if not tag:
            return False
        raw_tags = item.get("tags")
        normalized_tag = tag.lower()
        return normalized_tag in {
            item_tag.lower()
            for item_tag in normalize_persisted_tags(raw_tags if isinstance(raw_tags, list) else [])
        }

    async def _should_ignore_item_enrichment(
        self,
        settings: SettingsService,
        item: Dict[str, Any],
    ) -> bool:
        ignore_tag = self._get_ignore_enrichment_tag(
            await settings.get("enrichment.ignore_timeline_tag", "migrated")
        )
        return self._item_has_tag(item, ignore_tag)

    async def _get_provider_signatures(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        only_enabled: bool,
    ) -> List[Tuple[str, str]]:
        provider_item = await self._get_provider_item(db, item)
        providers = enrichment_registry.get_providers_for_item(provider_item)
        enabled_provider_ids: set[str] | None = None
        if only_enabled:
            settings = SettingsService(db)  # type: ignore[arg-type]
            enabled_provider_ids = await self._enabled_provider_ids(settings, providers)
        signatures: List[Tuple[str, str]] = []

        for provider in providers:
            if enabled_provider_ids is not None and provider.provider_id not in enabled_provider_ids:
                continue
            signatures.append((provider.provider_id, provider.build_cache_key(provider_item)))

        return sorted(signatures)

    async def _enqueue_item_task(
        self,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        priority: int,
        enrichment_request_id: str,
    ) -> str:
        task_queue = get_task_queue_service()
        from app.services.tasks import TASK_ENRICH_ITEM

        return await task_queue.enqueue(
            task_name=TASK_ENRICH_ITEM,
            payload={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "item_id": item_id,
                ENRICHMENT_REQUEST_ID_FIELD: enrichment_request_id,
            },
            priority=priority,
            dedupe_key=(
                f"enrich_item:{entity_type.lower()}:{entity_id}:{item_id}:"
                f"{enrichment_request_id}"
            ),
        )

    async def _mark_item_enrichment_failed(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        error_message: str,
        task_id: str | None = None,
        enrichment_request_id: str | None = None,
    ) -> None:
        entity, item = await self._load_timeline_item_for_update(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        if entity is None:
            logger.warning(
                "Failed to mark enrichment enqueue failure for missing %s %s",
                entity_type,
                entity_id,
            )
            await db.rollback()
            return
        if item is None:
            logger.warning(
                "Failed to mark enrichment enqueue failure for missing item %s on %s %s",
                item_id,
                entity_type,
                entity_id,
            )
            await db.rollback()
            return

        if not self._matches_enrichment_request(
            item,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
        ):
            logger.info(
                "Skipping enrichment failure update for superseded task",
                extra={"entity_type": entity_type, "entity_id": entity_id, "item_id": item_id, "task_id": task_id},
            )
            await db.rollback()
            return

        changed = self._set_item_enrichment_failed(item, error_message=error_message)
        await self._commit_timeline_item_update(
            db,
            entity=entity,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            changed=changed,
        )

    async def mark_item_enrichment_failed(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        error_message: str,
        task_id: str | None = None,
        enrichment_request_id: str | None = None,
    ) -> None:
        await self._mark_item_enrichment_failed(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            error_message=error_message,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
        )

    async def prepare_item_enrichment_enqueue(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        item: Dict[str, Any],
    ) -> Optional[int]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        if await self._should_ignore_item_enrichment(settings, item):
            if self._clear_item_enrichment_state(item):
                flag_modified(entity, "timeline_items")
            return None

        provider_item = await self._get_provider_item(db, item)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            return None

        self._clear_item_enrichment_error(item)
        item.pop("enrichment_task_id", None)
        item[ENRICHMENT_REQUEST_ID_FIELD] = str(uuid4())
        item["enrichment_status"] = "pending"
        flag_modified(entity, "timeline_items")
        return self.get_queue_priority_for_entity(entity)

    async def prepare_updated_item_enrichment(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        previous_item: Dict[str, Any],
        updated_item: Dict[str, Any],
    ) -> Optional[int]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        if await self._should_ignore_item_enrichment(settings, updated_item):
            if self._clear_item_enrichment_state(updated_item):
                flag_modified(entity, "timeline_items")
            return None

        previous_signatures = await self._get_provider_signatures(
            db,
            previous_item,
            only_enabled=False,
        )
        updated_signatures = await self._get_provider_signatures(
            db,
            updated_item,
            only_enabled=False,
        )

        if previous_signatures == updated_signatures:
            return None

        changed = self._clear_item_enrichment_state(updated_item)
        enabled_updated_signatures = await self._get_provider_signatures(
            db,
            updated_item,
            only_enabled=True,
        )
        if not enabled_updated_signatures:
            if changed:
                flag_modified(entity, "timeline_items")
            return None

        updated_item["enrichment_status"] = "pending"
        updated_item[ENRICHMENT_REQUEST_ID_FIELD] = str(uuid4())
        flag_modified(entity, "timeline_items")
        return self.get_queue_priority_for_entity(entity)

    async def _get_enrichment_request_for_enqueue(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        expected_request_id: str | None = None,
    ) -> str | None:
        """Read the active request under lock before publishing its queue job.

        The legacy fallback assigns a request ID to an unlinked pending item so
        even work prepared immediately before an upgrade gets versioned before
        it reaches the queue.
        """
        entity, item = await self._load_timeline_item_for_update(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        if entity is None or item is None:
            await db.rollback()
            return None

        status = str(item.get("enrichment_status") or "").strip().lower()
        if status not in ACTIVE_ENRICHMENT_STATUSES:
            await db.rollback()
            return None

        request_id = self._normalize_request_id(
            item.get(ENRICHMENT_REQUEST_ID_FIELD)
        )
        normalized_expected = self._normalize_request_id(expected_request_id)
        if normalized_expected is not None and request_id != normalized_expected:
            await db.rollback()
            return None

        if request_id is not None:
            await db.rollback()
            return request_id

        if str(item.get("enrichment_task_id") or "").strip():
            # A linked unversioned item already belongs to a legacy queue job.
            await db.rollback()
            return None

        request_id = str(uuid4())
        item[ENRICHMENT_REQUEST_ID_FIELD] = request_id
        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            entity.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return request_id

    async def enqueue_prepared_item_enrichment(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        priority: int,
        raise_on_error: bool = True,
        enrichment_request_id: str | None = None,
    ) -> Optional[str]:
        enqueued_task_id: str | None = None
        active_request_id: str | None = None
        try:
            active_request_id = await self._get_enrichment_request_for_enqueue(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                expected_request_id=enrichment_request_id,
            )
            if active_request_id is None:
                logger.info(
                    "Skipping enrichment enqueue for a superseded request",
                    extra={
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "item_id": item_id,
                        ENRICHMENT_REQUEST_ID_FIELD: enrichment_request_id,
                    },
                )
                return None
            enqueued_task_id = await self._enqueue_item_task(
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                priority=priority,
                enrichment_request_id=active_request_id,
            )
            await self._persist_enrichment_task_link(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                task_id=enqueued_task_id,
                enrichment_request_id=active_request_id,
            )
            return enqueued_task_id
        except Exception as exc:
            try:
                await db.rollback()
                if active_request_id is not None:
                    await self._mark_item_enrichment_failed(
                        db,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        item_id=item_id,
                        error_message="Enrichment task could not be queued",
                        task_id=enqueued_task_id,
                        enrichment_request_id=active_request_id,
                    )
            except Exception:
                logger.exception(
                    "Failed to persist enrichment enqueue failure",
                    extra={
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "item_id": item_id,
                        "task_id": enqueued_task_id,
                    },
                )
            logger.warning("Failed to enqueue enrichment task: %s", exc)
            if raise_on_error:
                raise
            return None

    async def _persist_enrichment_task_link(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        task_id: str,
        enrichment_request_id: str,
    ) -> bool:
        """Atomically set enrichment_task_id on a timeline item without a full
        read-modify-write of the JSONB column.  This prevents the stale-snapshot
        race where this commit overwrites enrichment data the worker has already
        written.

        Falls back to a locked ORM write for legacy array rows and nested reply items.
        """
        table = _ENTITY_TYPE_TO_TABLE.get(entity_type.lower())
        if table is None:
            return False

        # NOTE: table name comes from _ENTITY_TYPE_TO_TABLE (hardcoded),
        # never from user input.
        sql = text(f"""
            UPDATE {table}
            SET timeline_items = jsonb_set(
                timeline_items #- ARRAY[:item_id, 'enrichments', 'system'],
                ARRAY[:item_id, 'enrichment_task_id'],
                to_jsonb(:task_id ::text)
            ),
            updated_at = :now
            WHERE id = :entity_id
            AND jsonb_typeof(timeline_items) = 'object'
            AND timeline_items ? :item_id
            AND timeline_items -> :item_id ->> 'enrichment_status'
                IN ('pending', 'in_progress')
            AND timeline_items -> :item_id ->> 'enrichment_request_id'
                = :enrichment_request_id
            AND (
                timeline_items -> :item_id ->> 'enrichment_task_id' IS NULL
                OR timeline_items -> :item_id ->> 'enrichment_task_id' = :task_id
            )
        """)

        result = await db.execute(sql, {
            "item_id": item_id,
            "task_id": task_id,
            "enrichment_request_id": enrichment_request_id,
            "entity_id": entity_id,
            "now": datetime.now(timezone.utc),
        })
        if result.rowcount:  # type: ignore[union-attr]
            await db.commit()
            # The raw SQL bypassed the ORM, so any entity already in the
            # identity-map still holds stale timeline_items.  Expire
            # everything so the next attribute access re-fetches from DB.
            db.expire_all()
            return True
        else:
            return await self._persist_enrichment_task_link_locked(
                db, entity_type=entity_type, entity_id=entity_id,
                item_id=item_id, task_id=task_id,
                enrichment_request_id=enrichment_request_id,
            )

    async def _persist_enrichment_task_link_locked(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        task_id: str,
        enrichment_request_id: str,
    ) -> bool:
        """Fallback for nested reply items where the atomic jsonb_set missed.
        Uses SELECT FOR UPDATE to serialise the write."""
        logger.debug(
            "Atomic task-link update missed (item may be nested); "
            "falling back to locked read-modify-write",
            extra={"entity_type": entity_type, "entity_id": entity_id, "item_id": item_id},
        )
        entity = await self._load_entity_for_update(db, entity_type, entity_id)
        if entity is None:
            await db.rollback()
            return False

        from app.services.timeline_service import timeline_service

        item = timeline_service.find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None or not self._matches_enrichment_request(
            item,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
        ):
            await db.rollback()
            return False
        if not self._link_enrichment_task(item, task_id):
            await db.rollback()
            return True

        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            entity.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return True

    async def _get_provider_item(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        item_type = item.get("type")
        if isinstance(item_type, str) and "actor" in item_type:
            from app.services.normalization_service import normalization_service

            return await normalization_service.denormalize_item(db, dict(item))
        return item

    async def _configure_hot_cache(self, settings: SettingsService) -> None:
        default_ttl = int(await settings.get("enrichment.cache.default_ttl_seconds", 86400))
        maxsize = int(await settings.get("enrichment.cache.hot_cache_max_size", 1024))
        enrichment_cache.configure(maxsize=maxsize, ttl_seconds=default_ttl)

    def _normalize_alias_value(self, value: str) -> str:
        return value.strip().lower()

    async def _is_provider_enabled(self, settings: SettingsService, provider: Any) -> bool:
        enabled = await settings.get(f"{provider.settings_prefix}.enabled", False)
        return bool(enabled)

    async def _enabled_provider_ids(
        self,
        settings: SettingsService,
        providers: List[Any],
    ) -> set[str]:
        values = await settings.get_many(
            {
                f"{provider.settings_prefix}.enabled": False
                for provider in providers
            }
        )
        return {
            provider.provider_id
            for provider in providers
            if bool(values[f"{provider.settings_prefix}.enabled"])
        }

    async def get_matching_enabled_providers(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
    ) -> List[Any]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        providers = enrichment_registry.get_providers_for_item(item)
        enabled_provider_ids = await self._enabled_provider_ids(settings, providers)
        return [
            provider
            for provider in providers
            if provider.provider_id in enabled_provider_ids
        ]

    def get_queue_priority_for_entity(self, entity: Any) -> int:
        priority = getattr(entity, "priority", None)
        if isinstance(priority, Priority):
            return PRIORITY_TO_QUEUE_PRIORITY.get(priority, 0)
        if isinstance(priority, str):
            try:
                return PRIORITY_TO_QUEUE_PRIORITY.get(Priority(priority), 0)
            except ValueError:
                return 0
        return 0

    async def enqueue_item_enrichment(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
    ) -> str:
        entity = await self._load_entity(db, entity_type, entity_id)
        if entity is None:
            raise EnrichmentNotFoundError(f"{entity_type} {entity_id} not found")

        await self.reconcile_entity_enrichment_statuses(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            timeline_items=getattr(entity, "timeline_items", None) or [],
        )

        # Manual enqueue is itself a state transition. Refresh under a row lock
        # so a stale identity-map snapshot cannot replace a newer request.
        entity, item = await self._load_timeline_item_for_update(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        if entity is None:
            await db.rollback()
            raise EnrichmentNotFoundError(f"{entity_type} {entity_id} not found")
        if item is None:
            await db.rollback()
            raise EnrichmentNotFoundError(f"Timeline item {item_id} not found")
        settings = SettingsService(db)  # type: ignore[arg-type]
        if await self._should_ignore_item_enrichment(settings, item):
            if self._clear_item_enrichment_state(item):
                flag_modified(entity, "timeline_items")
                if hasattr(entity, "updated_at"):
                    entity.updated_at = datetime.now(timezone.utc)
                await db.commit()
            else:
                await db.rollback()
            raise EnrichmentValidationError(
                "Timeline item is tagged to skip enrichment"
            )

        current_status = str(item.get("enrichment_status") or "").strip().lower()
        if current_status in ACTIVE_ENRICHMENT_STATUSES and item.get("enrichment_task_id"):
            task_id = str(item["enrichment_task_id"])
            await db.rollback()
            return task_id

        priority = await self.prepare_item_enrichment_enqueue(
            db,
            entity=entity,
            item=item,
        )
        if priority is None:
            await db.rollback()
            raise EnrichmentValidationError(
                "No enabled enrichment providers matched this timeline item"
            )

        await db.commit()
        enqueued_task_id = await self.enqueue_prepared_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            priority=priority,
        )
        if enqueued_task_id is None:
            raise RuntimeError(f"Failed to enqueue enrichment for {entity_type} {entity_id} item {item_id}")
        return enqueued_task_id

    async def search_aliases(
        self,
        db: AsyncSession,
        *,
        query: str,
        entity_type: str,
        provider_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[EnrichmentAliasRead]:
        normalized_query = self._normalize_alias_value(query)
        statement = select(EnrichmentAlias).where(
            EnrichmentAlias.entity_type == entity_type,
            col(EnrichmentAlias.alias_value).ilike(f"%{normalized_query}%"),
        )
        if provider_id:
            statement = statement.where(EnrichmentAlias.provider_id == provider_id)
        statement = statement.order_by(col(EnrichmentAlias.alias_value).asc()).limit(limit)
        rows = (await db.execute(statement)).scalars().all()
        return [EnrichmentAliasRead.model_validate(row) for row in rows]

    async def upsert_alias(
        self,
        db: AsyncSession,
        alias: EnrichmentAliasCreate,
    ) -> EnrichmentAliasRead:
        row = await self._upsert_alias_row(db, alias)
        response = EnrichmentAliasRead.model_validate(row)
        await db.commit()
        return response

    async def _upsert_alias_row(
        self,
        db: AsyncSession,
        alias: EnrichmentAliasCreate,
    ) -> EnrichmentAlias:
        existing = (
            await db.execute(
                select(EnrichmentAlias).where(
                    EnrichmentAlias.provider_id == alias.provider_id,
                    EnrichmentAlias.alias_type == alias.alias_type,
                    EnrichmentAlias.alias_value == self._normalize_alias_value(alias.alias_value),
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        normalized_alias_value = self._normalize_alias_value(alias.alias_value)
        payload = alias.model_dump()
        payload["alias_value"] = normalized_alias_value

        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = now
            db.add(existing)
            return existing

        row = EnrichmentAlias(**payload)
        db.add(row)
        await db.flush()
        return row

    async def update_alias(
        self,
        db: AsyncSession,
        alias_id: int,
        alias_update: EnrichmentAliasUpdate,
    ) -> Optional[EnrichmentAliasRead]:
        row = await db.get(EnrichmentAlias, alias_id)
        if row is None:
            return None

        update_data = alias_update.model_dump(exclude_unset=True)
        if "alias_value" in update_data and update_data["alias_value"] is not None:
            update_data["alias_value"] = self._normalize_alias_value(update_data["alias_value"])
        for key, value in update_data.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        response = EnrichmentAliasRead.model_validate(row)
        await db.commit()
        return response

    async def delete_alias(self, db: AsyncSession, alias_id: int) -> bool:
        row = await db.get(EnrichmentAlias, alias_id)
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True

    async def get_provider_statuses(self, db: AsyncSession) -> List[EnrichmentProviderStatusRead]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        providers = enrichment_registry.list()
        enabled_provider_ids = await self._enabled_provider_ids(settings, providers)

        alias_rows = (
            await db.execute(
                select(
                    EnrichmentAlias.provider_id,
                    func.count().label("entry_count"),
                    func.max(EnrichmentAlias.updated_at).label("last_updated_at"),
                ).group_by(EnrichmentAlias.provider_id)
            )
        ).all()
        alias_stats = {
            row.provider_id: (int(row.entry_count or 0), row.last_updated_at)
            for row in alias_rows
        }
        cache_rows = (
            await db.execute(
                select(
                    EnrichmentCacheEntry.provider_id,
                    func.count().label("entry_count"),
                    func.max(EnrichmentCacheEntry.updated_at).label("last_updated_at"),
                ).group_by(EnrichmentCacheEntry.provider_id)
            )
        ).all()
        cache_stats = {
            row.provider_id: (int(row.entry_count or 0), row.last_updated_at)
            for row in cache_rows
        }

        statuses: List[EnrichmentProviderStatusRead] = []
        for provider in providers:
            alias_count, last_alias_update = alias_stats.get(provider.provider_id, (0, None))
            cache_entry_count, last_cache_update = cache_stats.get(provider.provider_id, (0, None))
            last_activity_at = last_alias_update
            if last_cache_update and (last_activity_at is None or last_cache_update > last_activity_at):
                last_activity_at = last_cache_update
            statuses.append(
                EnrichmentProviderStatusRead(
                    provider_id=provider.provider_id,
                    display_name=provider.display_name,
                    settings_prefix=provider.settings_prefix,
                    enabled=provider.provider_id in enabled_provider_ids,
                    supports_bulk_sync=provider.supports_bulk_sync,
                    item_types=list(provider.supported_item_types),
                    cache_entry_count=int(cache_entry_count or 0),
                    alias_count=int(alias_count or 0),
                    last_activity_at=last_activity_at,
                )
            )
        return statuses

    async def clear_cache(self, db: AsyncSession, provider_id: str | None = None) -> int:
        cleared = await enrichment_cache.clear(db, provider_id)
        await db.commit()
        return cleared

    async def run_item_enrichment(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        task_id: str | None = None,
        enrichment_request_id: str | None = None,
    ) -> None:
        entity, item = await self._load_timeline_item_for_update(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        if entity is None:
            await db.rollback()
            raise EnrichmentNotFoundError(f"{entity_type} {entity_id} not found")
        if item is None:
            await db.rollback()
            raise EnrichmentNotFoundError(f"Timeline item {item_id} not found")
        if not self._matches_enrichment_request(
            item,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
        ):
            logger.info(
                "Skipping enrichment for superseded task",
                extra={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "item_id": item_id,
                    "task_id": task_id,
                    ENRICHMENT_REQUEST_ID_FIELD: enrichment_request_id,
                },
            )
            await db.rollback()
            return

        settings = SettingsService(db)  # type: ignore[arg-type]
        if await self._should_ignore_item_enrichment(settings, item):
            await self._commit_timeline_item_update(
                db,
                entity=entity,
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                changed=self._clear_item_enrichment_state(item),
            )
            return

        changed = bool(task_id and self._link_enrichment_task(item, task_id))
        provider_input = deepcopy(item)
        await self._commit_timeline_item_update(
            db,
            entity=entity,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            changed=changed,
        )

        await self._configure_hot_cache(settings)
        provider_item = await self._get_provider_item(db, provider_input)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            await self._persist_no_provider_result(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                task_id=task_id,
                enrichment_request_id=enrichment_request_id,
            )
            return

        results: List[EnrichmentResult] = []
        for provider in providers:
            cache_key = provider.build_cache_key(provider_item)
            provider_cacheable = bool(getattr(provider, "cacheable", True))
            cached_payload = (
                await enrichment_cache.get(db, provider.provider_id, cache_key)
                if provider_cacheable
                else None
            )
            if cached_payload is not None:
                result = EnrichmentResult.from_cache_payload(cached_payload)
            else:
                result = await provider.enrich(
                    db=db,
                    settings=settings,
                    item=provider_item,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
                ttl_seconds = result.ttl_seconds or int(
                    await settings.get(f"{provider.settings_prefix}.ttl_seconds", await settings.get("enrichment.cache.default_ttl_seconds", 86400))
                )
                if provider_cacheable:
                    await enrichment_cache.set(
                        db=db,
                        provider_id=provider.provider_id,
                        cache_key=cache_key,
                        result_payload=result.to_cache_payload(),
                        ttl_seconds=ttl_seconds,
                    )

            await self._upsert_alias_mappings(db, result.provider_id, result.aliases)
            results.append(result)

        await self._persist_enrichment_results(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
            results=results,
        )

    async def _persist_no_provider_result(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        task_id: str | None,
        enrichment_request_id: str | None,
    ) -> None:
        entity, item = await self._load_timeline_item_for_update(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        if entity is None or item is None or not self._matches_enrichment_request(
            item,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
        ):
            await db.commit()
            return

        item.pop("enrichment_task_id", None)
        item.pop("enrichment_status", None)
        item.pop(ENRICHMENT_REQUEST_ID_FIELD, None)
        item.setdefault("enrichments", {})["system"] = {
            "error": "No enabled providers matched this timeline item"
        }
        await self._commit_timeline_item_update(
            db,
            entity=entity,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            changed=True,
        )

    async def _persist_enrichment_results(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        task_id: str | None,
        enrichment_request_id: str | None,
        results: List[EnrichmentResult],
    ) -> None:
        entity, item = await self._load_timeline_item_for_update(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
        )
        if entity is None or item is None or not self._matches_enrichment_request(
            item,
            task_id=task_id,
            enrichment_request_id=enrichment_request_id,
        ):
            logger.info(
                "Skipping stale enrichment result",
                extra={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "item_id": item_id,
                    "task_id": task_id,
                },
            )
            await db.commit()
            return

        if task_id:
            self._link_enrichment_task(item, task_id)

        from app.services.timeline_service import timeline_service

        for result in results:
            self._apply_result_to_item(item, result)
            if result.timeline_reply:
                reply = dict(result.timeline_reply)
                reply["parent_id"] = item_id
                timeline_service.add_timeline_item(
                    entity,
                    reply,
                    created_by=reply.get("created_by", result.provider_id),
                )

        item["enrichment_status"] = "complete"
        item.pop("enrichment_task_id", None)
        item.pop(ENRICHMENT_REQUEST_ID_FIELD, None)
        await self._commit_timeline_item_update(
            db,
            entity=entity,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            changed=True,
        )

    async def _commit_timeline_item_update(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        entity_type: str,
        entity_id: int,
        item_id: str,
        changed: bool,
    ) -> None:
        if changed:
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now(timezone.utc)
            await emit_event(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=RealtimeEventType.TIMELINE_ITEM_UPDATED,
                performed_by="system",
                item_id=item_id,
            )
        await db.commit()

    def _collect_reconcilable_items(
        self,
        items: Any,
        collected: Dict[str, Dict[str, Any]],
    ) -> None:
        from app.services.timeline_service import timeline_service

        for item in timeline_service.iter_items(items):
            item_id = item.get("id")
            if item_id:
                collected[str(item_id)] = item
            replies = item.get("replies")
            if replies:
                self._collect_reconcilable_items(replies, collected)

    def _reconcile_item_with_job(
        self,
        item: Dict[str, Any],
        job: Any | None,
    ) -> bool:
        status = str(item.get("enrichment_status") or "").strip().lower()
        if status not in ACTIVE_ENRICHMENT_STATUSES:
            return False

        if job is None:
            if status == "pending" and not str(item.get("enrichment_task_id") or "").strip():
                return False
            return self._set_item_enrichment_failed(item)

        if not self._job_matches_enrichment_request(item, job):
            return False

        changed = False
        job_id = str(job.id)
        if item.get("enrichment_task_id") != job_id:
            item["enrichment_task_id"] = job_id
            changed = True

        if job.status == "picked" and item.get("enrichment_status") != "in_progress":
            item["enrichment_status"] = "in_progress"
            changed = True
        elif job.status == "queued" and item.get("enrichment_status") != "pending":
            item["enrichment_status"] = "pending"
            changed = True
        elif job.status == "successful":
            if item.get("enrichment_status") != "complete":
                item["enrichment_status"] = "complete"
                changed = True
            if _remove_present(item, "enrichment_task_id"):
                changed = True
            if _remove_present(item, ENRICHMENT_REQUEST_ID_FIELD):
                changed = True
        elif job.status in {"exception", "canceled"}:
            changed = self._set_item_enrichment_failed(item) or changed

        return changed

    def _job_matches_enrichment_request(
        self,
        item: Dict[str, Any],
        job: Any,
    ) -> bool:
        """Validate a queue-status row before reconciling item state.

        Historical pgqueuer rows do not retain payloads, so an exact persisted
        task link is the only safe proof for those rows. Active, unlinked rows
        must carry the same request ID as the item.
        """
        job_id = str(getattr(job, "id", "") or "").strip()
        linked_task_id = str(item.get("enrichment_task_id") or "").strip()
        if linked_task_id and linked_task_id != job_id:
            return False

        payload = getattr(job, "payload", None)
        payload_request_id = (
            self._normalize_request_id(payload.get(ENRICHMENT_REQUEST_ID_FIELD))
            if isinstance(payload, dict)
            else None
        )
        item_request_id = self._normalize_request_id(
            item.get(ENRICHMENT_REQUEST_ID_FIELD)
        )
        if payload_request_id is not None:
            return payload_request_id == item_request_id
        if item_request_id is not None:
            return bool(linked_task_id and linked_task_id == job_id)
        return True

    def _enrichment_state_guard(
        self,
        item: Dict[str, Any],
    ) -> tuple[str, str | None, str | None]:
        return (
            str(item.get("enrichment_status") or "").strip().lower(),
            self._normalize_request_id(item.get(ENRICHMENT_REQUEST_ID_FIELD)),
            str(item.get("enrichment_task_id") or "").strip() or None,
        )

    async def reconcile_entity_enrichment_statuses(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        timeline_items: Any,
    ) -> List[str]:
        items_by_id: Dict[str, Dict[str, Any]] = {}
        self._collect_reconcilable_items(timeline_items, items_by_id)

        active_item_ids = [
            item_id
            for item_id, item in items_by_id.items()
            if str(item.get("enrichment_status") or "").strip().lower() in ACTIVE_ENRICHMENT_STATUSES
        ]
        if not active_item_ids:
            return []

        linked_task_ids_by_item_id = {
            item_id: str(item.get("enrichment_task_id"))
            for item_id, item in items_by_id.items()
            if item_id in active_item_ids and str(item.get("enrichment_task_id") or "").strip()
        }

        jobs_by_item_id = await QueueStatusService(db).get_enrichment_jobs_for_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            item_ids=active_item_ids,
            linked_task_ids_by_item_id=linked_task_ids_by_item_id,
        )

        changed_item_ids: List[str] = []
        state_guards_by_item_id: Dict[
            str,
            tuple[str, str | None, str | None],
        ] = {}
        for item_id in active_item_ids:
            item = items_by_id[item_id]
            state_guard = self._enrichment_state_guard(item)
            if self._reconcile_item_with_job(item, jobs_by_item_id.get(item_id)):
                changed_item_ids.append(item_id)
                state_guards_by_item_id[item_id] = state_guard

        if not changed_item_ids:
            return []

        await self._persist_reconciled_items(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            items_by_id=items_by_id,
            changed_item_ids=changed_item_ids,
            state_guards_by_item_id=state_guards_by_item_id,
        )
        return changed_item_ids

    async def _persist_reconciled_items(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        items_by_id: Dict[str, Dict[str, Any]],
        changed_item_ids: List[str],
        state_guards_by_item_id: Dict[
            str,
            tuple[str, str | None, str | None],
        ],
    ) -> None:
        entity = await self._load_entity_for_update(db, entity_type, entity_id)
        if entity is None:
            await db.rollback()
            return

        from app.services.timeline_service import timeline_service

        updated = False
        updated_item_ids: List[str] = []
        for item_id in changed_item_ids:
            stored_item = timeline_service.find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
            response_item = items_by_id.get(item_id)
            if stored_item is None or response_item is None:
                continue
            if self._enrichment_state_guard(stored_item) != state_guards_by_item_id.get(item_id):
                # The caller's response object is the stale snapshot that was
                # reconciled. Refresh it in place as well as skipping the write.
                response_item.clear()
                response_item.update(deepcopy(stored_item))
                continue

            item_updated = False
            for key in (
                "enrichment_status",
                "enrichment_task_id",
                ENRICHMENT_REQUEST_ID_FIELD,
            ):
                if key in response_item:
                    if stored_item.get(key) != response_item.get(key):
                        stored_item[key] = response_item.get(key)
                        updated = True
                        item_updated = True
                elif key in stored_item:
                    stored_item.pop(key, None)
                    updated = True
                    item_updated = True

            response_enrichments = response_item.get("enrichments")
            if isinstance(response_enrichments, dict) and response_enrichments:
                merged_enrichments = dict(stored_item.get("enrichments") or {})
                merged_enrichments.update(response_enrichments)
                if stored_item.get("enrichments") != merged_enrichments:
                    stored_item["enrichments"] = merged_enrichments
                    updated = True
                    item_updated = True
            if item_updated:
                updated_item_ids.append(item_id)

        if not updated:
            await db.rollback()
            return

        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            entity.updated_at = datetime.now(timezone.utc)
        for item_id in updated_item_ids:
            await emit_event(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=RealtimeEventType.TIMELINE_ITEM_UPDATED,
                performed_by="system",
                item_id=item_id,
            )
        await db.commit()

    async def run_directory_sync(self, db: AsyncSession, provider_id: str) -> None:
        provider = enrichment_registry.get(provider_id)
        if provider is None:
            raise EnrichmentValidationError(f"Unknown provider {provider_id}")
        if not provider.supports_bulk_sync:
            raise EnrichmentValidationError(
                f"Provider {provider_id} does not support bulk sync"
            )

        settings = SettingsService(db)  # type: ignore[arg-type]
        await self._configure_hot_cache(settings)
        if not await self._is_provider_enabled(settings, provider):
            raise EnrichmentValidationError(f"Provider {provider_id} is disabled")

        results = await provider.bulk_sync(db=db, settings=settings)
        cache_default_ttl = await settings.get(
            "enrichment.cache.default_ttl_seconds",
            86400,
        )
        default_ttl = int(
            await settings.get(
                f"{provider.settings_prefix}.ttl_seconds",
                cache_default_ttl,
            )
        )
        for result in results:
            await enrichment_cache.set(
                db,
                provider_id=provider.provider_id,
                cache_key=result.cache_key,
                result_payload=result.to_cache_payload(),
                ttl_seconds=result.ttl_seconds or default_ttl,
            )
            await self._upsert_alias_mappings(db, provider.provider_id, result.aliases)
        await db.commit()

    def _apply_result_to_item(
        self,
        item: Dict[str, Any],
        result: EnrichmentResult,
    ) -> None:
        item.setdefault("enrichments", {})[result.provider_id] = result.enrichment_data
        if (
            result.provider_id == "servicenow"
            and item.get("type") == "internal_actor"
            and "error" not in result.enrichment_data
        ):
            for item_key, enrichment_key in (
                ("is_vip", "is_vip"),
                ("is_privileged", "is_privileged"),
            ):
                value = result.enrichment_data.get(enrichment_key)
                if isinstance(value, bool):
                    item[item_key] = value
        self._apply_system_enrichment_fields(item, result)

    def _apply_system_enrichment_fields(self, item: Dict[str, Any], result: EnrichmentResult) -> None:
        if item.get("type") != "system" or result.enrichment_data.get("status") != "matched":
            return

        for key in ("is_privileged", "is_critical"):
            value = result.enrichment_data.get(key)
            if isinstance(value, bool):
                item[key] = value

        field_map = {
            "cmdb_id": "record_id",
            "hostname": "name",
            "ip_address": "ip_address",
        }
        for item_key, enrichment_key in field_map.items():
            if item.get(item_key):
                continue
            value = result.enrichment_data.get(enrichment_key)
            if isinstance(value, str) and value.strip():
                item[item_key] = value.strip()

    async def _upsert_alias_mappings(
        self,
        db: AsyncSession,
        provider_id: str,
        aliases: List[AliasMapping],
    ) -> None:
        for alias in aliases:
            await self._upsert_alias_row(
                db,
                EnrichmentAliasCreate(
                    provider_id=provider_id,
                    entity_type=alias.entity_type,
                    canonical_value=alias.canonical_value,
                    canonical_display=alias.canonical_display,
                    alias_type=alias.alias_type,
                    alias_value=alias.alias_value,
                    attributes=alias.attributes,
                ),
            )

    async def _load_entity(self, db: AsyncSession, entity_type: str, entity_id: int) -> Optional[Any]:
        normalized_type = entity_type.lower()
        if normalized_type == "case":
            return await db.get(Case, entity_id)
        if normalized_type == "alert":
            return await db.get(Alert, entity_id)
        if normalized_type == "task":
            return await db.get(Task, entity_id)
        raise EnrichmentValidationError(f"Unsupported entity_type {entity_type}")

    async def _load_entity_for_update(self, db: AsyncSession, entity_type: str, entity_id: int) -> Optional[Any]:
        normalized_type = entity_type.lower()
        if normalized_type == "case":
            stmt = select(Case).where(Case.id == entity_id).with_for_update()  # type: ignore[arg-type]
        elif normalized_type == "alert":
            stmt = select(Alert).where(Alert.id == entity_id).with_for_update()  # type: ignore[arg-type]
        elif normalized_type == "task":
            stmt = select(Task).where(Task.id == entity_id).with_for_update()  # type: ignore[arg-type]
        else:
            raise EnrichmentValidationError(
                f"Unsupported entity_type {entity_type}"
            )
        return (
            await db.execute(stmt.execution_options(populate_existing=True))
        ).scalar_one_or_none()

    async def _load_timeline_item_for_update(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
    ) -> tuple[Any | None, Dict[str, Any] | None]:
        entity = await self._load_entity_for_update(db, entity_type, entity_id)
        if entity is None:
            return None, None

        from app.services.timeline_service import timeline_service

        item = timeline_service.find_item_by_id(
            getattr(entity, "timeline_items", None) or [],
            item_id,
        )
        return entity, item


enrichment_service = EnrichmentService()
