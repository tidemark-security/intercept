from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import tasks
from app.services.maxmind_service import MaxMindCacheSyncError, MaxMindUpdateError


@pytest.mark.asyncio
async def test_maxmind_task_propagates_download_failure_for_queue_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()

    @asynccontextmanager
    async def session_factory():
        yield db

    settings = SimpleNamespace(get=AsyncMock(return_value=True))
    download_error = MaxMindUpdateError(
        {"GeoLite2-ASN": "http"},
        {"GeoLite2-ASN": {"status": "error", "error": "http"}},
    )
    download = AsyncMock(side_effect=download_error)
    sync_local_cache = AsyncMock()

    monkeypatch.setattr(tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(tasks, "SettingsService", lambda _db: settings)
    monkeypatch.setattr(tasks.maxmind_service, "download_databases", download)
    monkeypatch.setattr(
        tasks.maxmind_service,
        "sync_local_cache",
        sync_local_cache,
    )

    with pytest.raises(MaxMindUpdateError) as exc_info:
        await tasks.handle_maxmind_update({"reschedule": True})

    assert exc_info.value is download_error
    download.assert_awaited_once_with(db)
    sync_local_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_maxmind_task_propagates_cache_failure_for_queue_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()

    @asynccontextmanager
    async def session_factory():
        yield db

    settings = SimpleNamespace(get=AsyncMock(return_value=True))
    cache_error = MaxMindCacheSyncError({"GeoLite2-City": "missing"})
    download = AsyncMock(return_value={"GeoLite2-City": {"status": "unchanged"}})
    sync_local_cache = AsyncMock(side_effect=cache_error)
    ensure_readers_loaded = AsyncMock()
    enqueue_next_scheduled_update = AsyncMock()

    monkeypatch.setattr(tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(tasks, "SettingsService", lambda _db: settings)
    monkeypatch.setattr(tasks.maxmind_service, "download_databases", download)
    monkeypatch.setattr(
        tasks.maxmind_service,
        "sync_local_cache",
        sync_local_cache,
    )
    monkeypatch.setattr(
        tasks.maxmind_service,
        "ensure_readers_loaded",
        ensure_readers_loaded,
    )
    monkeypatch.setattr(
        tasks.maxmind_service,
        "enqueue_next_scheduled_update",
        enqueue_next_scheduled_update,
    )

    with pytest.raises(MaxMindCacheSyncError) as exc_info:
        await tasks.handle_maxmind_update({"reschedule": True})

    assert exc_info.value is cache_error
    download.assert_awaited_once_with(db)
    sync_local_cache.assert_awaited_once_with(settings=settings)
    ensure_readers_loaded.assert_not_awaited()
    enqueue_next_scheduled_update.assert_not_awaited()
