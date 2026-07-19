from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EnrichmentCacheEntry
from app.services.enrichment.cache import EnrichmentCache


class _ScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def scalar_one_or_none(self) -> Any | None:
        return self._values[0] if self._values else None

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[Any]:
        return self._values


class _CacheWriteSession(AsyncSession):
    def __init__(self, query_values: list[Any]) -> None:
        super().__init__()
        self._query_values = query_values
        self.added: list[Any] = []
        self.deleted_objects: list[Any] = []

    async def execute(self, *_args: Any, **_kwargs: Any) -> _ScalarResult:  # type: ignore[override]
        return _ScalarResult(self._query_values)

    def add(self, instance: object, *, _warn: bool = True) -> None:
        self.added.append(instance)

    async def delete(self, instance: object) -> None:
        self.deleted_objects.append(instance)


@pytest.mark.parametrize("expires_at", [None, "", "not-a-date", 123])
def test_is_expired_treats_unusable_timestamps_as_expired(expires_at: object) -> None:
    assert EnrichmentCache()._is_expired({"expires_at": expires_at}) is True


def test_is_expired_normalizes_naive_timestamps() -> None:
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(tzinfo=None)
    assert EnrichmentCache()._is_expired({"expires_at": future.isoformat()}) is False


@pytest.mark.asyncio
async def test_set_updates_hot_cache_only_after_database_commit() -> None:
    cache = EnrichmentCache()
    session = _CacheWriteSession([])
    await session.begin()

    await cache.set(
        session,
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result_payload={"display_name": "Alice"},
        ttl_seconds=300,
    )

    hot_key = cache._key("ldap", "user:alice@example.com")
    assert hot_key not in cache._cache

    await session.commit()

    assert cache._cache[hot_key]["result"] == {"display_name": "Alice"}


@pytest.mark.asyncio
async def test_set_does_not_update_hot_cache_when_database_rolls_back() -> None:
    cache = EnrichmentCache()
    session = _CacheWriteSession([])
    await session.begin()
    hot_key = cache._key("ldap", "user:alice@example.com")
    cache._cache[hot_key] = {
        "result": {"display_name": "Committed Alice"},
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }

    await cache.set(
        session,
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result_payload={"display_name": "Uncommitted Alice"},
        ttl_seconds=300,
    )
    await session.rollback()

    assert cache._cache[hot_key]["result"] == {"display_name": "Committed Alice"}


@pytest.mark.asyncio
async def test_set_then_get_reads_transaction_value_without_publishing_it() -> None:
    cache = EnrichmentCache()
    session = _CacheWriteSession([])
    await session.begin()
    hot_key = cache._key("ldap", "user:alice@example.com")
    cache._cache[hot_key] = {
        "result": {"display_name": "Committed Alice"},
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }

    await cache.set(
        session,
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result_payload={"display_name": "Uncommitted Alice"},
        ttl_seconds=300,
    )

    assert await cache.get(session, "ldap", "user:alice@example.com") == {
        "display_name": "Uncommitted Alice"
    }
    assert cache._cache[hot_key]["result"] == {"display_name": "Committed Alice"}

    await session.rollback()

    assert cache._cache[hot_key]["result"] == {"display_name": "Committed Alice"}


@pytest.mark.asyncio
async def test_clear_evicts_hot_cache_only_after_database_commit() -> None:
    cache = EnrichmentCache()
    entry = EnrichmentCacheEntry(
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result={"display_name": "Alice"},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session = _CacheWriteSession([entry])
    await session.begin()
    hot_key = cache._key(entry.provider_id, entry.cache_key)
    cache._cache[hot_key] = {
        "result": entry.result,
        "expires_at": entry.expires_at.isoformat(),
    }

    await cache.clear(session, provider_id="ldap")

    assert hot_key in cache._cache

    await session.commit()

    assert hot_key not in cache._cache


@pytest.mark.asyncio
async def test_clear_keeps_hot_cache_when_database_rolls_back() -> None:
    cache = EnrichmentCache()
    entry = EnrichmentCacheEntry(
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result={"display_name": "Alice"},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session = _CacheWriteSession([entry])
    await session.begin()
    hot_key = cache._key(entry.provider_id, entry.cache_key)
    cache._cache[hot_key] = {
        "result": entry.result,
        "expires_at": entry.expires_at.isoformat(),
    }

    await cache.clear(session, provider_id="ldap")
    await session.rollback()

    assert hot_key in cache._cache


@pytest.mark.asyncio
async def test_clear_then_get_hides_transactionally_deleted_value() -> None:
    cache = EnrichmentCache()
    entry = EnrichmentCacheEntry(
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result={"display_name": "Alice"},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session = _CacheWriteSession([entry])
    await session.begin()
    hot_key = cache._key(entry.provider_id, entry.cache_key)
    cache._cache[hot_key] = {
        "result": entry.result,
        "expires_at": entry.expires_at.isoformat(),
    }

    await cache.clear(session, provider_id="ldap")

    assert await cache.get(session, entry.provider_id, entry.cache_key) is None
    assert hot_key in cache._cache

    await session.rollback()

    assert hot_key in cache._cache


@pytest.mark.asyncio
async def test_nested_commit_waits_for_root_transaction_commit() -> None:
    cache = EnrichmentCache()
    session = _CacheWriteSession([])
    root_transaction = await session.begin()
    nested_transaction = await session.begin_nested()

    await cache.set(
        session,
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result_payload={"display_name": "Alice"},
        ttl_seconds=300,
    )
    hot_key = cache._key("ldap", "user:alice@example.com")

    await nested_transaction.commit()

    assert hot_key not in cache._cache

    await root_transaction.commit()

    assert cache._cache[hot_key]["result"] == {"display_name": "Alice"}


@pytest.mark.asyncio
async def test_nested_rollback_discards_only_its_hot_cache_update() -> None:
    cache = EnrichmentCache()
    session = _CacheWriteSession([])
    root_transaction = await session.begin()
    nested_transaction = await session.begin_nested()

    await cache.set(
        session,
        provider_id="ldap",
        cache_key="user:alice@example.com",
        result_payload={"display_name": "Alice"},
        ttl_seconds=300,
    )
    hot_key = cache._key("ldap", "user:alice@example.com")

    await nested_transaction.rollback()
    await root_transaction.commit()

    assert hot_key not in cache._cache
