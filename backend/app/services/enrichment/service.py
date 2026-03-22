from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from app.models.enums import Priority
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


class EnrichmentService:
    """Coordinates provider lookup, caching, queueing, and alias persistence."""

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
        settings = SettingsService(db)
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
        provider_item = await self._get_provider_item(db, item)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            return None

        item["enrichment_status"] = "pending"
        flag_modified(entity, "timeline_items")

        try:
            task_queue = get_task_queue_service()
            from app.services.tasks import TASK_ENRICH_ITEM

            return await task_queue.enqueue(
                task_name=TASK_ENRICH_ITEM,
                payload={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "item_id": item["id"],
                },
                priority=self.get_queue_priority_for_entity(entity),
            )
        except Exception as exc:
            item["enrichment_status"] = "failed"
            item.setdefault("enrichments", {})["system"] = {"error": str(exc)}
            flag_modified(entity, "timeline_items")
            logger.warning("Failed to enqueue enrichment task: %s", exc)
            return None

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

        provider_item = await self._get_provider_item(db, item)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            raise ValueError("No enabled enrichment providers matched this timeline item")

        item["enrichment_status"] = "pending"
        flag_modified(entity, "timeline_items")

        task_queue = get_task_queue_service()
        from app.services.tasks import TASK_ENRICH_ITEM

        return await task_queue.enqueue(
            task_name=TASK_ENRICH_ITEM,
            payload={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "item_id": item_id,
            },
            priority=self.get_queue_priority_for_entity(entity),
        )

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
            EnrichmentAlias.alias_value.ilike(f"%{normalized_query}%"),
        )
        if provider_id:
            statement = statement.where(EnrichmentAlias.provider_id == provider_id)
        statement = statement.order_by(EnrichmentAlias.alias_value.asc()).limit(limit)
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
        settings = SettingsService(db)
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
    ) -> None:
        entity = await self._load_entity(db, entity_type, entity_id)
        if entity is None:
            raise ValueError(f"{entity_type} {entity_id} not found")

        from app.services.timeline_service import timeline_service

        item = timeline_service._find_item_by_id(getattr(entity, "timeline_items", None) or [], item_id)
        if item is None:
            raise ValueError(f"Timeline item {item_id} not found")

        settings = SettingsService(db)
        await self._configure_hot_cache(settings)
        provider_item = await self._get_provider_item(db, item)
        providers = await self.get_matching_enabled_providers(db, provider_item)
        if not providers:
            item["enrichment_status"] = "failed"
            item.setdefault("enrichments", {})["system"] = {"error": "No enabled providers matched this timeline item"}
            flag_modified(entity, "timeline_items")
            await db.commit()
            return

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
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            item["enrichment_status"] = "failed"
            item.setdefault("enrichments", {})["system"] = {"error": str(exc)}
            flag_modified(entity, "timeline_items")
            if hasattr(entity, "updated_at"):
                entity.updated_at = datetime.now(timezone.utc)
            await db.commit()
            raise

    async def run_directory_sync(self, db: AsyncSession, provider_id: str) -> None:
        provider = enrichment_registry.get(provider_id)
        if provider is None:
            raise ValueError(f"Unknown provider {provider_id}")
        if not provider.supports_bulk_sync:
            raise ValueError(f"Provider {provider_id} does not support bulk sync")

        settings = SettingsService(db)
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