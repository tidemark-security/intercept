"""Settings-backed delayed-job scheduling for collector streams."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from pgqueuer.errors import DuplicateJobError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.collectors.registry import collector_registry
from app.services.settings_service import SettingsService
from app.services.task_queue_service import get_task_queue_service

logger = logging.getLogger(__name__)

COLLECTOR_SCHEDULE_DEDUPE_PREFIX = "collector_schedule:"
COLLECTOR_RECONCILE_DEDUPE_KEY = "collector_reconcile"
_COLLECTOR_SETTING_RE = re.compile(
    r"^collectors\.(?P<provider_id>[a-z0-9_]+)\."
    r"(enabled|schedule_enabled|schedule_time_utc)$"
)
_UTC_TIME_RE = re.compile(r"^(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)$")


def collector_schedule_dedupe_key(provider_id: str, stream_key: str) -> str:
    return f"{COLLECTOR_SCHEDULE_DEDUPE_PREFIX}{provider_id}:{stream_key}"


def get_collector_provider_id_from_setting_key(key: str) -> str | None:
    match = _COLLECTOR_SETTING_RE.fullmatch(key)
    if match is None:
        return None
    provider_id = match.group("provider_id")
    return provider_id if collector_registry.get(provider_id) is not None else None


def next_collector_run_at(value: str, *, now: datetime | None = None) -> datetime:
    match = _UTC_TIME_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError("Collector schedule time must use HH:MM 24-hour UTC format")
    reference = now or datetime.now(timezone.utc)
    reference = reference.replace(tzinfo=reference.tzinfo or timezone.utc).astimezone(timezone.utc)
    scheduled = reference.replace(
        hour=int(match.group("hour")),
        minute=int(match.group("minute")),
        second=0,
        microsecond=0,
    )
    return scheduled + timedelta(days=1) if scheduled <= reference else scheduled


async def _delete_queued_job(db: AsyncSession, entrypoint: str, dedupe_key: str) -> int:
    result = await db.execute(
        text(
            "DELETE FROM pgqueuer WHERE entrypoint = :entrypoint "
            "AND dedupe_key = :dedupe_key AND status = 'queued'"
        ),
        {"entrypoint": entrypoint, "dedupe_key": dedupe_key},
    )
    return int(result.rowcount or 0)


async def sync_collector_schedule_for_stream(
    db: AsyncSession,
    provider_id: str,
    stream_key: str,
    *,
    settings: SettingsService | None = None,
) -> bool:
    from app.services.tasks import TASK_COLLECTOR_POLL

    provider = collector_registry.require(provider_id)
    setting_service = settings or SettingsService(db)  # type: ignore[arg-type]
    dedupe_key = collector_schedule_dedupe_key(provider_id, stream_key)
    removed = await _delete_queued_job(db, TASK_COLLECTOR_POLL, dedupe_key)
    enabled = bool(await setting_service.get(f"{provider.settings_prefix}.enabled", False))
    schedule_enabled = bool(
        await setting_service.get(f"{provider.settings_prefix}.schedule_enabled", False)
    )
    schedule_time = str(
        await setting_service.get(f"{provider.settings_prefix}.schedule_time_utc", "") or ""
    ).strip()
    if not enabled or not schedule_enabled or not schedule_time:
        await db.commit()
        logger.info(
            "Collector schedule disabled",
            extra={"provider_id": provider_id, "stream_key": stream_key, "removed_jobs": removed},
        )
        return False

    next_run = next_collector_run_at(schedule_time)
    await db.commit()
    try:
        await get_task_queue_service().enqueue(
            task_name=TASK_COLLECTOR_POLL,
            payload={
                "provider_id": provider_id,
                "stream_key": stream_key,
                "scheduled": True,
                "reschedule": True,
            },
            priority=10,
            schedule_at=next_run,
            dedupe_key=dedupe_key,
        )
    except DuplicateJobError:
        return True
    logger.info(
        "Scheduled collector poll",
        extra={
            "provider_id": provider_id,
            "stream_key": stream_key,
            "next_run": next_run.isoformat(),
        },
    )
    return True


async def sync_collector_schedules(db: AsyncSession) -> None:
    service = get_task_queue_service()
    settings = SettingsService(db)  # type: ignore[arg-type]
    async with service.schedule_refresh_lock:
        for provider in collector_registry.list():
            for stream_key in provider.stream_keys:
                try:
                    await sync_collector_schedule_for_stream(
                        db,
                        provider.provider_id,
                        stream_key,
                        settings=settings,
                    )
                except ValueError:
                    logger.exception(
                        "Skipping invalid collector schedule",
                        extra={"provider_id": provider.provider_id, "stream_key": stream_key},
                    )


async def schedule_collector_reconciliation(db: AsyncSession) -> None:
    from app.services.tasks import TASK_COLLECTOR_RECONCILE

    settings = SettingsService(db)  # type: ignore[arg-type]
    interval = max(int(await settings.get("collectors.reconcile_interval_seconds", 300)), 60)
    await _delete_queued_job(db, TASK_COLLECTOR_RECONCILE, COLLECTOR_RECONCILE_DEDUPE_KEY)
    await db.commit()
    try:
        await get_task_queue_service().enqueue(
            task_name=TASK_COLLECTOR_RECONCILE,
            payload={"reschedule": True},
            priority=0,
            schedule_at=datetime.now(timezone.utc) + timedelta(seconds=interval),
            dedupe_key=COLLECTOR_RECONCILE_DEDUPE_KEY,
        )
    except DuplicateJobError:
        return

