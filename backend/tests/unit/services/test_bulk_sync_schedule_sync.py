from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.enrichment.bulk_sync_schedule_sync import (
    bulk_sync_schedule_dedupe_key,
    cron_expression_for_utc_time,
    get_bulk_sync_provider_id_from_setting_key,
    next_bulk_sync_run_at,
    sync_bulk_sync_schedule_for_provider,
    sync_bulk_sync_schedules,
)


class _AsyncLock:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00:00", "0 0 * * *"),
        ("02:15", "15 2 * * *"),
        ("23:59", "59 23 * * *"),
    ],
)
def test_cron_expression_for_utc_time(value: str, expected: str) -> None:
    assert cron_expression_for_utc_time(value) == expected


@pytest.mark.parametrize("value", ["", "2:15", "24:00", "12:60", "nope"])
def test_cron_expression_for_utc_time_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        cron_expression_for_utc_time(value)


def test_next_bulk_sync_run_at_same_day() -> None:
    now = datetime(2026, 3, 31, 10, 30, tzinfo=timezone.utc)
    assert next_bulk_sync_run_at("11:15", now=now) == datetime(2026, 3, 31, 11, 15, tzinfo=timezone.utc)


def test_next_bulk_sync_run_at_rolls_to_next_day() -> None:
    now = datetime(2026, 3, 31, 11, 15, tzinfo=timezone.utc)
    assert next_bulk_sync_run_at("11:15", now=now) == datetime(2026, 4, 1, 11, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("enrichment.ldap.enabled", "ldap"),
        ("enrichment.ldap.bulk_sync_enabled", "ldap"),
        ("enrichment.ldap.bulk_sync_time_utc", "ldap"),
        ("enrichment.entra_id.bulk_sync_time_utc", "entra_id"),
        ("enrichment.maxmind.enabled", None),
        ("other.setting", None),
    ],
)
def test_get_bulk_sync_provider_id_from_setting_key(key: str, expected: str | None) -> None:
    assert get_bulk_sync_provider_id_from_setting_key(key) == expected


@pytest.mark.asyncio
async def test_sync_bulk_sync_schedule_for_provider_enqueues_active_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = SimpleNamespace(
        schedule_refresh_lock=_AsyncLock(),
        enqueue=AsyncMock(return_value="job-123"),
    )
    fake_db = AsyncMock()
    fake_db.execute.return_value.rowcount = 1

    async def fake_get(self, key: str, default=None):
        values = {
            "enrichment.ldap.enabled": True,
            "enrichment.ldap.bulk_sync_enabled": True,
            "enrichment.ldap.bulk_sync_time_utc": "02:15",
        }
        return values.get(key, default)

    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.get_task_queue_service",
        lambda: fake_service,
    )
    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync._utcnow",
        lambda: datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.SettingsService.get",
        fake_get,
    )

    scheduled = await sync_bulk_sync_schedule_for_provider(fake_db, "ldap")

    assert scheduled is True
    fake_db.execute.assert_awaited_once()
    fake_db.commit.assert_awaited_once()
    fake_service.enqueue.assert_awaited_once_with(
        task_name="directory_sync",
        payload={"provider_id": "ldap", "reschedule": True, "scheduled": True},
        priority=10,
        schedule_at=datetime(2026, 3, 31, 2, 15, tzinfo=timezone.utc),
        dedupe_key=bulk_sync_schedule_dedupe_key("ldap"),
    )


@pytest.mark.asyncio
async def test_sync_bulk_sync_schedule_for_provider_disables_job(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_service = SimpleNamespace(
        schedule_refresh_lock=_AsyncLock(),
        enqueue=AsyncMock(),
    )
    fake_db = AsyncMock()
    fake_db.execute.return_value.rowcount = 1

    async def fake_get(self, key: str, default=None):
        values = {
            "enrichment.ldap.enabled": False,
            "enrichment.ldap.bulk_sync_enabled": True,
            "enrichment.ldap.bulk_sync_time_utc": "02:15",
        }
        return values.get(key, default)

    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.get_task_queue_service",
        lambda: fake_service,
    )
    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.SettingsService.get",
        fake_get,
    )

    scheduled = await sync_bulk_sync_schedule_for_provider(fake_db, "ldap")

    assert scheduled is False
    fake_db.execute.assert_awaited_once()
    fake_db.commit.assert_awaited_once()
    fake_service.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_bulk_sync_schedules_reconciles_all_bulk_sync_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = SimpleNamespace(
        queries=SimpleNamespace(),
        schedule_refresh_lock=_AsyncLock(),
    )
    fake_db = AsyncMock()
    fake_db.execute.return_value.rowcount = 1

    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.get_task_queue_service",
        lambda: fake_service,
    )
    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.enrichment_registry.list",
        lambda: [
            SimpleNamespace(provider_id="ldap", supports_bulk_sync=True),
            SimpleNamespace(provider_id="maxmind", supports_bulk_sync=False),
            SimpleNamespace(provider_id="entra_id", supports_bulk_sync=True),
        ],
    )

    synced_provider_ids: list[str] = []

    async def fake_sync_provider(db, provider_id: str, *, settings=None):
        synced_provider_ids.append(provider_id)
        return provider_id == "ldap"

    monkeypatch.setattr(
        "app.services.enrichment.bulk_sync_schedule_sync.sync_bulk_sync_schedule_for_provider",
        fake_sync_provider,
    )

    await sync_bulk_sync_schedules(fake_db)

    assert synced_provider_ids == ["ldap", "entra_id"]
    fake_db.execute.assert_awaited_once()