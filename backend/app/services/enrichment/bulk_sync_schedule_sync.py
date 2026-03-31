"""Helpers for bulk sync scheduling via delayed queue jobs."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from pgqueuer.errors import DuplicateJobError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.enrichment.registry import enrichment_registry
from app.services.settings_service import SettingsService
from app.services.task_queue_service import get_task_queue_service

logger = logging.getLogger(__name__)

TASK_DIRECTORY_SYNC = "directory_sync"
SUPPORTED_BULK_SYNC_PROVIDER_IDS = ("entra_id", "google_workspace", "ldap")
BULK_SYNC_SCHEDULE_ENTRYPOINT_PREFIX = "bulk_sync_schedule__"
BULK_SYNC_SCHEDULE_DEDUPE_KEY_PREFIX = "bulk_sync_schedule:"
_BULK_SYNC_KEY_RE = re.compile(
    r"^enrichment\.(?P<provider_id>[a-z0-9_]+)\.(enabled|bulk_sync_enabled|bulk_sync_time_utc)$"
)
_BULK_SYNC_TIME_RE = re.compile(r"^(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)$")


def bulk_sync_schedule_enabled_key(provider_id: str) -> str:
    return f"enrichment.{provider_id}.bulk_sync_enabled"


def bulk_sync_schedule_time_key(provider_id: str) -> str:
    return f"enrichment.{provider_id}.bulk_sync_time_utc"


def bulk_sync_schedule_dedupe_key(provider_id: str) -> str:
    return f"{BULK_SYNC_SCHEDULE_DEDUPE_KEY_PREFIX}{provider_id}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_bulk_sync_provider_id_from_setting_key(key: str) -> str | None:
    match = _BULK_SYNC_KEY_RE.match(key)
    if match is None:
        return None

    provider_id = match.group("provider_id")
    if provider_id not in SUPPORTED_BULK_SYNC_PROVIDER_IDS:
        return None

    return provider_id


def cron_expression_for_utc_time(value: str) -> str:
    normalized = value.strip()
    match = _BULK_SYNC_TIME_RE.fullmatch(normalized)
    if match is None:
        raise ValueError("Bulk sync time must use HH:MM 24-hour UTC format")

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    return f"{minute} {hour} * * *"


def next_bulk_sync_run_at(value: str, *, now: datetime | None = None) -> datetime:
    normalized = value.strip()
    match = _BULK_SYNC_TIME_RE.fullmatch(normalized)
    if match is None:
        raise ValueError("Bulk sync time must use HH:MM 24-hour UTC format")

    reference = now or _utcnow()
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    else:
        reference = reference.astimezone(timezone.utc)

    scheduled_for = reference.replace(
        hour=int(match.group("hour")),
        minute=int(match.group("minute")),
        second=0,
        microsecond=0,
    )
    if scheduled_for <= reference:
        scheduled_for += timedelta(days=1)

    return scheduled_for


async def _delete_legacy_bulk_sync_schedules(db: AsyncSession) -> int:
    result = await db.execute(
        text(
            "DELETE FROM pgqueuer_schedules WHERE entrypoint LIKE :entrypoint_prefix"
        ),
        {"entrypoint_prefix": f"{BULK_SYNC_SCHEDULE_ENTRYPOINT_PREFIX}%"},
    )
    return int(result.rowcount or 0)


async def _delete_queued_bulk_sync_job(db: AsyncSession, provider_id: str) -> int:
    result = await db.execute(
        text(
            "DELETE FROM pgqueuer "
            "WHERE entrypoint = :entrypoint "
            "AND dedupe_key = :dedupe_key "
            "AND status = 'queued'"
        ),
        {
            "entrypoint": TASK_DIRECTORY_SYNC,
            "dedupe_key": bulk_sync_schedule_dedupe_key(provider_id),
        },
    )
    return int(result.rowcount or 0)


async def sync_bulk_sync_schedule_for_provider(
    db: AsyncSession,
    provider_id: str,
    *,
    settings: SettingsService | None = None,
) -> bool:
    service = get_task_queue_service()
    settings_service = settings or SettingsService(db)  # type: ignore[arg-type]

    removed_jobs = await _delete_queued_bulk_sync_job(db, provider_id)

    enabled = bool(await settings_service.get(f"enrichment.{provider_id}.enabled", False))
    schedule_enabled = bool(await settings_service.get(bulk_sync_schedule_enabled_key(provider_id), False))
    schedule_time = str(await settings_service.get(bulk_sync_schedule_time_key(provider_id), "") or "").strip()

    if not enabled or not schedule_enabled or not schedule_time:
        await db.commit()
        logger.info(
            "Bulk sync schedule disabled for provider",
            extra={"provider_id": provider_id, "removed_jobs": removed_jobs},
        )
        return False

    next_run = next_bulk_sync_run_at(schedule_time)
    await db.commit()

    try:
        await service.enqueue(
            task_name=TASK_DIRECTORY_SYNC,
            payload={"provider_id": provider_id, "reschedule": True, "scheduled": True},
            priority=10,
            schedule_at=next_run,
            dedupe_key=bulk_sync_schedule_dedupe_key(provider_id),
        )
    except DuplicateJobError:
        logger.info(
            "Bulk sync job already scheduled for provider",
            extra={"provider_id": provider_id, "next_run": next_run.isoformat()},
        )
        return True

    logger.info(
        "Scheduled next bulk sync job for provider",
        extra={"provider_id": provider_id, "next_run": next_run.isoformat()},
    )
    return True


async def sync_bulk_sync_schedules(db: AsyncSession) -> None:
    """Sync bulk sync jobs into the queue from current app settings."""
    service = get_task_queue_service()
    if service.queries is None:
        raise RuntimeError("Task queue service is missing queue queries")

    settings = SettingsService(db)  # type: ignore[arg-type]

    async with service.schedule_refresh_lock:
        scheduled_provider_ids: list[str] = []
        deleted_legacy_schedules = await _delete_legacy_bulk_sync_schedules(db)

        for provider in enrichment_registry.list():
            if not provider.supports_bulk_sync:
                continue

            provider_id = provider.provider_id
            try:
                if await sync_bulk_sync_schedule_for_provider(db, provider_id, settings=settings):
                    scheduled_provider_ids.append(provider_id)
            except ValueError:
                schedule_time = str(await settings.get(bulk_sync_schedule_time_key(provider_id), "") or "").strip()
                logger.warning(
                    "Skipping bulk sync schedule with invalid UTC time",
                    extra={"provider_id": provider_id, "schedule_time": schedule_time},
                )
                await db.commit()

        logger.info(
            "Bulk sync schedule sync complete",
            extra={
                "scheduled_provider_ids": scheduled_provider_ids,
                "schedule_count": len(scheduled_provider_ids),
                "deleted_legacy_schedules": deleted_legacy_schedules,
            },
        )