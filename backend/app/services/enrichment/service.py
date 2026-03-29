from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
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
from app.services.task_queue_service import get_task_queue_service

logger = logging.getLogger(__name__)


PRIORITY_TO_QUEUE_PRIORITY = {
    Priority.INFO: 0,
    Priority.LOW: 10,
    Priority.MEDIUM: 25,
    Priority.HIGH: 50,
    Priority.CRITICAL: 75,
    Priority.EXTREME: 100,
}

ACTIVE_ENRICHMENT_STATUSES = {"pending", "in_progress"}


class EnrichmentService:
    """Coordinates provider lookup, caching, queueing, and alias persistence."""

    def _clear_item_enrichment_state(self, item: Dict[str, Any]) -> bool:
        changed = False
        if item.pop("enrichment_status", None) is not None:
            changed = True
        if item.pop("enrichment_task_id", None) is not None:
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
        if enrichments.pop("system", None) is None:
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

    def _matches_linked_task(self, item: Dict[str, Any], task_id: str | None) -> bool:
        if not task_id:
            return True
        linked_task_id = item.get("enrichment_task_id")
        if linked_task_id is None:
            return True
        return str(linked_task_id) == task_id

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
        if item.pop("enrichment_task_id", None) is not None:
            changed = True
        if error_message:
            enrichments = item.setdefault("enrichments", {})
            if enrichments.get("system", {}).get("error") != error_message:
                enrichments["system"] = {"error": error_message}
                changed = True
        return changed

    async def _get_provider_signatures(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
        *,
        only_enabled: bool,
    ) -> List[Tuple[str, str]]:
        provider_item = await self._get_provider_item(db, item)
        providers = enrichment_registry.get_providers_for_item(provider_item)
        signatures: List[Tuple[str, str]] = []

        for provider in providers:
            if only_enabled:
                settings = SettingsService(db)  # type: ignore[arg-type]
                if not await self._is_provider_enabled(settings, provider):
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
    ) -> str:
        task_queue = get_task_queue_service()
        from app.services.tasks import TASK_ENRICH_ITEM

        return await task_queue.enqueue(
            task_name=TASK_ENRICH_ITEM,
            payload={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "item_id": item_id,
            },
            priority=priority,
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
    ) -> None:
        entity = await self._load_entity(db, entity_type, entity_id)
        if entity is None:
            logger.warning(
                "Failed to mark enrichment enqueue failure for missing %s %s",
                entity_type,
                entity_id,
            )
            return

        from app.services.timeline_service import timeline_service

        item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None:
            logger.warning(
                "Failed to mark enrichment enqueue failure for missing item %s on %s %s",
                item_id,
                entity_type,
                entity_id,
            )
            return

        if not self._matches_linked_task(item, task_id):
            logger.info(
                "Skipping enrichment failure update for superseded task",
                extra={"entity_type": entity_type, "entity_id": entity_id, "item_id": item_id, "task_id": task_id},
            )
            return

        self._set_item_enrichment_failed(item, error_message=error_message)
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

    async def mark_item_enrichment_failed(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        error_message: str,
        task_id: str | None = None,
    ) -> None:
        await self._mark_item_enrichment_failed(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            error_message=error_message,
            task_id=task_id,
        )

    async def prepare_item_enrichment_enqueue(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        item: Dict[str, Any],
    ) -> Optional[int]:
        provider_item = await self._get_provider_item(db, item)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            return None

        self._clear_item_enrichment_error(item)
        item.pop("enrichment_task_id", None)
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
        flag_modified(entity, "timeline_items")
        return self.get_queue_priority_for_entity(entity)

    async def enqueue_prepared_item_enrichment(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        priority: int,
        raise_on_error: bool = True,
    ) -> Optional[str]:
        try:
            enqueued_task_id = await self._enqueue_item_task(
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                priority=priority,
            )
            await self._persist_enrichment_task_link(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                task_id=enqueued_task_id,
            )
            return enqueued_task_id
        except Exception as exc:
            await self._mark_item_enrichment_failed(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                item_id=item_id,
                error_message=str(exc),
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
    ) -> None:
        entity = await self._load_entity(db, entity_type, entity_id)
        if entity is None:
            return

        from app.services.timeline_service import timeline_service

        item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None:
            return

        if not self._link_enrichment_task(item, task_id):
            return

        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            entity.updated_at = datetime.now(timezone.utc)
        await db.commit()

    async def _get_provider_item(self, db: AsyncSession, item: Dict[str, Any]) -> Dict[str, Any]:
        item_type = item.get("type")
        if isinstance(item_type, str) and "actor" in item_type:
            from app.services.normalization_service import normalization_service

            return await normalization_service.denormalize_actor_item(db, dict(item))
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

    async def get_matching_enabled_providers(
        self,
        db: AsyncSession,
        item: Dict[str, Any],
    ) -> List[Any]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        providers = []
        for provider in enrichment_registry.get_providers_for_item(item):
            if await self._is_provider_enabled(settings, provider):
                providers.append(provider)
        return providers

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

    async def maybe_enqueue_item_enrichment(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        entity_type: str,
        entity_id: int,
        item: Dict[str, Any],
    ) -> Optional[str]:
        priority = await self.prepare_item_enrichment_enqueue(
            db,
            entity=entity,
            item=item,
        )
        if priority is None:
            return None

        await db.commit()
        return await self.enqueue_prepared_item_enrichment(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item["id"],
            priority=priority,
            raise_on_error=False,
        )

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
            raise ValueError(f"{entity_type} {entity_id} not found")

        from app.services.timeline_service import timeline_service

        item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None:
            raise ValueError(f"Timeline item {item_id} not found")

        await self.reconcile_entity_enrichment_statuses(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            timeline_items=getattr(entity, "timeline_items", None) or [],
        )
        item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None:
            raise ValueError(f"Timeline item {item_id} not found")
        current_status = str(item.get("enrichment_status") or "").strip().lower()
        if current_status in ACTIVE_ENRICHMENT_STATUSES and item.get("enrichment_task_id"):
            return str(item["enrichment_task_id"])

        priority = await self.prepare_item_enrichment_enqueue(
            db,
            entity=entity,
            item=item,
        )
        if priority is None:
            raise ValueError("No enabled enrichment providers matched this timeline item")

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
        await db.commit()
        await db.refresh(row)
        return EnrichmentAliasRead.model_validate(row)

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
        await db.commit()
        await db.refresh(row)
        return EnrichmentAliasRead.model_validate(row)

    async def delete_alias(self, db: AsyncSession, alias_id: int) -> bool:
        row = await db.get(EnrichmentAlias, alias_id)
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True

    async def get_provider_statuses(self, db: AsyncSession) -> List[EnrichmentProviderStatusRead]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        statuses: List[EnrichmentProviderStatusRead] = []
        for provider in enrichment_registry.list():
            enabled = await self._is_provider_enabled(settings, provider)
            alias_count = (
                await db.execute(
                    select(func.count()).select_from(EnrichmentAlias).where(EnrichmentAlias.provider_id == provider.provider_id)
                )
            ).scalar_one()
            cache_entry_count = (
                await db.execute(
                    select(func.count()).select_from(EnrichmentCacheEntry).where(
                        EnrichmentCacheEntry.provider_id == provider.provider_id
                    )
                )
            ).scalar_one()
            last_alias_update = (
                await db.execute(
                    select(func.max(EnrichmentAlias.updated_at)).where(EnrichmentAlias.provider_id == provider.provider_id)
                )
            ).scalar_one()
            last_cache_update = (
                await db.execute(
                    select(func.max(EnrichmentCacheEntry.updated_at)).where(EnrichmentCacheEntry.provider_id == provider.provider_id)
                )
            ).scalar_one()
            last_activity_at = last_alias_update
            if last_cache_update and (last_activity_at is None or last_cache_update > last_activity_at):
                last_activity_at = last_cache_update
            statuses.append(
                EnrichmentProviderStatusRead(
                    provider_id=provider.provider_id,
                    display_name=provider.display_name,
                    settings_prefix=provider.settings_prefix,
                    enabled=enabled,
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
    ) -> None:
        entity = await self._load_entity(db, entity_type, entity_id)
        if entity is None:
            raise ValueError(f"{entity_type} {entity_id} not found")

        from app.services.timeline_service import timeline_service

        item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None:
            raise ValueError(f"Timeline item {item_id} not found")
        if not self._matches_linked_task(item, task_id):
            logger.info(
                "Skipping enrichment for superseded task",
                extra={"entity_type": entity_type, "entity_id": entity_id, "item_id": item_id, "task_id": task_id},
            )
            return

        settings = SettingsService(db)  # type: ignore[arg-type]
        await self._configure_hot_cache(settings)
        provider_item = await self._get_provider_item(db, item)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            item.pop("enrichment_task_id", None)
            item.pop("enrichment_status", None)
            item.setdefault("enrichments", {})["system"] = {"error": "No enabled providers matched this timeline item"}
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
            return

        if task_id:
            self._link_enrichment_task(item, task_id)
        item["enrichment_status"] = "in_progress"
        flag_modified(entity, "timeline_items")
        await db.flush()

        try:
            for provider in providers:
                cache_key = provider.build_cache_key(provider_item)
                cached_payload = await enrichment_cache.get(db, provider.provider_id, cache_key)
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
                    await enrichment_cache.set(
                        db,
                        provider_id=provider.provider_id,
                        cache_key=cache_key,
                        result_payload=result.to_cache_payload(),
                        ttl_seconds=ttl_seconds,
                    )

                await self._apply_result(db, entity=entity, item=item, item_id=item_id, result=result)

            item["enrichment_status"] = "complete"
            item.pop("enrichment_task_id", None)
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
        except Exception as exc:
            raise

    def _collect_reconcilable_items(
        self,
        items: List[Dict[str, Any]],
        collected: Dict[str, Dict[str, Any]],
    ) -> None:
        for item in items:
            item_id = item.get("id")
            if item_id:
                collected[str(item_id)] = item
            replies = item.get("replies")
            if isinstance(replies, list) and replies:
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
            if item.pop("enrichment_task_id", None) is not None:
                changed = True
        elif job.status in {"exception", "canceled"}:
            changed = self._set_item_enrichment_failed(item) or changed

        return changed

    async def reconcile_entity_enrichment_statuses(
        self,
        db: AsyncSession,
        *,
        entity_type: str,
        entity_id: int,
        timeline_items: List[Dict[str, Any]],
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
        for item_id in active_item_ids:
            item = items_by_id[item_id]
            if self._reconcile_item_with_job(item, jobs_by_item_id.get(item_id)):
                changed_item_ids.append(item_id)

        if not changed_item_ids:
            return []

        await self._persist_reconciled_items(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            items_by_id=items_by_id,
            changed_item_ids=changed_item_ids,
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
    ) -> None:
        entity = await self._load_entity(db, entity_type, entity_id)
        if entity is None:
            return

        from app.services.timeline_service import timeline_service

        updated = False
        for item_id in changed_item_ids:
            stored_item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
            response_item = items_by_id.get(item_id)
            if stored_item is None or response_item is None:
                continue

            for key in ("enrichment_status", "enrichment_task_id"):
                if key in response_item:
                    if stored_item.get(key) != response_item.get(key):
                        stored_item[key] = response_item.get(key)
                        updated = True
                elif key in stored_item:
                    stored_item.pop(key, None)
                    updated = True

            response_enrichments = response_item.get("enrichments")
            if isinstance(response_enrichments, dict) and response_enrichments:
                merged_enrichments = dict(stored_item.get("enrichments") or {})
                merged_enrichments.update(response_enrichments)
                if stored_item.get("enrichments") != merged_enrichments:
                    stored_item["enrichments"] = merged_enrichments
                    updated = True

        if not updated:
            return

        flag_modified(entity, "timeline_items")
        if hasattr(entity, "updated_at"):
            entity.updated_at = datetime.now(timezone.utc)
        for item_id in changed_item_ids:
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
            raise ValueError(f"Unknown provider {provider_id}")
        if not provider.supports_bulk_sync:
            raise ValueError(f"Provider {provider_id} does not support bulk sync")

        settings = SettingsService(db)  # type: ignore[arg-type]
        await self._configure_hot_cache(settings)
        if not await self._is_provider_enabled(settings, provider):
            raise ValueError(f"Provider {provider_id} is disabled")

        results = await provider.bulk_sync(db=db, settings=settings)
        default_ttl = int(await settings.get(f"{provider.settings_prefix}.ttl_seconds", await settings.get("enrichment.cache.default_ttl_seconds", 86400)))
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

    async def _apply_result(
        self,
        db: AsyncSession,
        *,
        entity: Any,
        item: Dict[str, Any],
        item_id: str,
        result: EnrichmentResult,
    ) -> None:
        item.setdefault("enrichments", {})[result.provider_id] = result.enrichment_data
        await self._upsert_alias_mappings(db, result.provider_id, result.aliases)

        if result.timeline_reply:
            from app.services.timeline_service import timeline_service

            reply = dict(result.timeline_reply)
            reply["parent_id"] = item_id
            timeline_service.add_timeline_item(entity, reply, created_by=reply.get("created_by", result.provider_id))

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
        raise ValueError(f"Unsupported entity_type {entity_type}")


enrichment_service = EnrichmentService()