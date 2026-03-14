from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from cachetools import TTLCache
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EnrichmentCacheEntry


class EnrichmentCache:
    """Two-tier enrichment cache: process-local hot cache backed by Postgres."""

    def __init__(self) -> None:
        self._maxsize = 1024
        self._ttl = 86400
        self._cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=self._maxsize, ttl=self._ttl)

    def configure(self, *, maxsize: int, ttl_seconds: int) -> None:
        maxsize = max(1, maxsize)
        ttl_seconds = max(60, ttl_seconds)
        if maxsize == self._maxsize and ttl_seconds == self._ttl:
            return
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def _key(self, provider_id: str, cache_key: str) -> str:
        return f"{provider_id}:{cache_key}"

    def _is_expired(self, payload: Dict[str, Any]) -> bool:
        expires_at = payload.get("expires_at")
        if not expires_at:
            return True
        try:
            return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    async def get(self, db: AsyncSession, provider_id: str, cache_key: str) -> Optional[Dict[str, Any]]:
        hot_key = self._key(provider_id, cache_key)
        hot_value = self._cache.get(hot_key)
        if hot_value is not None:
            if self._is_expired(hot_value):
                self._cache.pop(hot_key, None)
            else:
                return hot_value.get("result")

        result = await db.execute(
            select(EnrichmentCacheEntry).where(
                EnrichmentCacheEntry.provider_id == provider_id,
                EnrichmentCacheEntry.cache_key == cache_key,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry or entry.expires_at <= datetime.now(timezone.utc):
            return None

        self._cache[hot_key] = {
            "result": entry.result,
            "expires_at": entry.expires_at.isoformat(),
        }
        return entry.result

    async def set(
        self,
        db: AsyncSession,
        *,
        provider_id: str,
        cache_key: str,
        result_payload: Dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, ttl_seconds))
        query = select(EnrichmentCacheEntry).where(
            EnrichmentCacheEntry.provider_id == provider_id,
            EnrichmentCacheEntry.cache_key == cache_key,
        )
        existing = (await db.execute(query)).scalar_one_or_none()

        if existing:
            existing.result = result_payload
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(timezone.utc)
            db.add(existing)
        else:
            db.add(
                EnrichmentCacheEntry(
                    provider_id=provider_id,
                    cache_key=cache_key,
                    result=result_payload,
                    expires_at=expires_at,
                )
            )

        self._cache[self._key(provider_id, cache_key)] = {
            "result": result_payload,
            "expires_at": expires_at.isoformat(),
        }

    async def clear(self, db: AsyncSession, provider_id: str | None = None) -> int:
        query = select(EnrichmentCacheEntry)
        if provider_id:
            query = query.where(EnrichmentCacheEntry.provider_id == provider_id)
        rows = (await db.execute(query)).scalars().all()
        for row in rows:
            await db.delete(row)
        if provider_id:
            prefix = f"{provider_id}:"
            for key in list(self._cache.keys()):
                if key.startswith(prefix):
                    self._cache.pop(key, None)
        else:
            self._cache.clear()
        return len(rows)


enrichment_cache = EnrichmentCache()