"""Durable collection, processing, validation, and reconciliation workflows."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import SETTINGS_REGISTRY
from app.models.models import (
    CollectorCheckpoint,
    CollectorEvent,
    CollectorEventRevision,
    CollectorFinding,
    CollectorRun,
)
from app.services.collectors.alert_ingestion import alert_ingestion_service
from app.services.collectors.base import CollectorProvider
from app.services.collectors.models import (
    CollectionPage,
    CollectorConnectionTestResponse,
    CollectorContext,
    CollectorErrorCode,
    CollectorEventStatus,
    CollectorFindingStatus,
    CollectorProviderStatus,
    CollectorRunStatus,
    CollectorRunTrigger,
    EvaluationOutcome,
    ExternalEvent,
    NormalizedEvent,
    NormalizedFinding,
    ValidationResult,
)
from app.services.collectors.registry import collector_registry
from app.services.collectors.metrics import record_provider_request
from app.services.collectors.security import (
    CollectorSecurityError,
    canonical_hash,
    redacted_error,
    validate_allowed_url,
    validate_external_event,
)
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

EMPTY_COUNTS = {
    "discovered": 0,
    "new": 0,
    "unchanged": 0,
    "revised": 0,
    "skipped": 0,
    "queued": 0,
    "failed": 0,
}


def collector_poll_dedupe_key(provider_id: str, stream_key: str) -> str:
    return f"collector_poll:{provider_id}:{stream_key}"


def collector_process_dedupe_key(event_id: int, revision: int) -> str:
    return f"collector_process:{event_id}:{revision}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CollectorService:
    async def get_or_create_task_run(
        self,
        db: AsyncSession,
        *,
        task_id: str,
        provider_id: str,
        stream_key: str,
        trigger: CollectorRunTrigger,
    ) -> CollectorRun:
        result = await db.execute(
            select(CollectorRun).where(CollectorRun.task_id == task_id)
        )
        run = result.scalar_one_or_none()
        if run is not None:
            return run
        run = CollectorRun(
            provider_id=provider_id,
            stream_key=stream_key,
            trigger=trigger.value,
            status=CollectorRunStatus.QUEUED.value,
            task_id=task_id,
            counts=dict(EMPTY_COUNTS),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    async def configuration_snapshot(
        self,
        db: AsyncSession,
        provider: CollectorProvider,
    ) -> dict[str, Any]:
        settings = SettingsService(db)  # type: ignore[arg-type]
        prefix = f"{provider.settings_prefix}."
        config: dict[str, Any] = {}
        for key in SETTINGS_REGISTRY:
            if key.startswith(prefix):
                config[key.removeprefix(prefix)] = await settings.get(key)
        return config

    async def enqueue_run(
        self,
        db: AsyncSession,
        *,
        provider_id: str,
        stream_key: str,
        trigger: CollectorRunTrigger,
        max_pages: int | None = None,
        since: datetime | None = None,
        dedupe_key: str | None = None,
        reschedule: bool = False,
    ) -> tuple[CollectorRun, str]:
        collector_registry.require(provider_id)
        run = CollectorRun(
            provider_id=provider_id,
            stream_key=stream_key,
            trigger=trigger.value,
            status=CollectorRunStatus.QUEUED.value,
            counts=dict(EMPTY_COUNTS),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        if run.id is None:
            raise RuntimeError("Collector run did not receive an identifier")

        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_COLLECTOR_POLL

        payload: dict[str, Any] = {
            "run_id": run.id,
            "provider_id": provider_id,
            "stream_key": stream_key,
            "reschedule": reschedule,
        }
        if max_pages is not None:
            payload["max_pages"] = max_pages
        if since is not None:
            payload["since"] = since.isoformat()

        try:
            task_id = await get_task_queue_service().enqueue(
                task_name=TASK_COLLECTOR_POLL,
                payload=payload,
                priority=10 if trigger is CollectorRunTrigger.SCHEDULED else 20,
                dedupe_key=dedupe_key,
            )
        except Exception as exc:
            run.status = CollectorRunStatus.FAILED.value
            run.finished_at = _utcnow()
            run.error_code, run.error_summary = redacted_error(
                CollectorErrorCode.PROVIDER_UNAVAILABLE,
                exc,
            )
            db.add(run)
            await db.commit()
            raise

        run.task_id = task_id
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run, task_id

    async def poll(
        self,
        db: AsyncSession,
        *,
        provider_id: str,
        stream_key: str = "default",
        run_id: int | None = None,
        trigger: CollectorRunTrigger = CollectorRunTrigger.MANUAL,
        task_id: str | None = None,
        dry_run: bool = False,
        max_pages: int | None = None,
        since: datetime | None = None,
    ) -> dict[str, int]:
        provider = collector_registry.require(provider_id)
        config = await self.configuration_snapshot(db, provider)
        if not dry_run and config.get("enabled") is not True:
            raise CollectorSecurityError(
                CollectorErrorCode.CONFIGURATION_INVALID,
                "Collector provider is disabled",
            )

        configured_limit = int(config.get("max_pages_per_run") or 100)
        page_limit = min(max_pages or configured_limit, configured_limit, 1000)
        if page_limit < 1:
            raise CollectorSecurityError(
                CollectorErrorCode.CONFIGURATION_INVALID,
                "Collector max_pages_per_run must be at least one",
            )

        checkpoint_result = await db.execute(
            select(CollectorCheckpoint).where(
                CollectorCheckpoint.provider_id == provider_id,
                CollectorCheckpoint.stream_key == stream_key,
            )
        )
        checkpoint_row = checkpoint_result.scalar_one_or_none()
        checkpoint = dict(checkpoint_row.cursor) if checkpoint_row and checkpoint_row.cursor else None
        checkpoint_version = checkpoint_row.version if checkpoint_row else 0
        if since is not None:
            checkpoint = {"since": since.isoformat()}

        counts = dict(EMPTY_COUNTS)
        run: CollectorRun | None = None
        if not dry_run:
            if run_id is None:
                run = CollectorRun(
                    provider_id=provider_id,
                    stream_key=stream_key,
                    trigger=trigger.value,
                    task_id=task_id,
                    counts=dict(EMPTY_COUNTS),
                )
                db.add(run)
                await db.flush()
                run_id = run.id
            else:
                run = await db.get(CollectorRun, run_id)
                if run is None or run.provider_id != provider_id or run.stream_key != stream_key:
                    raise ValueError("Collector run does not match the requested provider stream")
                if run.status == CollectorRunStatus.SUCCEEDED.value:
                    return dict(run.counts or EMPTY_COUNTS)
                counts.update(run.counts or {})
            run.status = CollectorRunStatus.RUNNING.value
            run.started_at = run.started_at or _utcnow()
            run.finished_at = None
            run.error_code = None
            run.error_summary = None
            run.checkpoint_before = run.checkpoint_before if run.checkpoint_before is not None else checkpoint
            db.add(run)
            await db.commit()
        else:
            # Settings/checkpoint reads use an implicit transaction. Providers
            # must never perform network I/O while a database transaction is open.
            await db.rollback()

        current_checkpoint = checkpoint
        has_more = False
        pages_processed = 0
        try:
            while pages_processed < page_limit:
                context = CollectorContext(
                    provider_id=provider_id,
                    stream_key=stream_key,
                    config=config,
                    run_id=run_id,
                )
                request_started = time.monotonic()
                try:
                    page = await provider.fetch_page(checkpoint=current_checkpoint, context=context)
                except Exception as exc:
                    record_provider_request(
                        provider_id,
                        "failed",
                        time.monotonic() - request_started,
                    )
                    if isinstance(exc, CollectorSecurityError):
                        raise
                    raise CollectorSecurityError(
                        CollectorErrorCode.PROVIDER_UNAVAILABLE
                    ) from None
                record_provider_request(
                    provider_id,
                    "succeeded",
                    time.monotonic() - request_started,
                )
                if not isinstance(page, CollectionPage):
                    raise CollectorSecurityError(CollectorErrorCode.INVALID_PROVIDER_RESPONSE)

                normalized_events = [self._normalize(provider, event) for event in page.events]
                counts["discovered"] += len(normalized_events)
                pages_processed += 1

                if dry_run:
                    counts["new"] += len(normalized_events)
                    if page.has_more and page.next_checkpoint == current_checkpoint:
                        raise CollectorSecurityError(
                            CollectorErrorCode.INVALID_PROVIDER_RESPONSE,
                            "Provider pagination did not advance",
                        )
                    current_checkpoint = page.next_checkpoint
                    has_more = page.has_more
                    if not has_more:
                        break
                    continue

                changed = await self._persist_page(
                    db,
                    provider=provider,
                    stream_key=stream_key,
                    run_id=run_id,  # type: ignore[arg-type]
                    events=normalized_events,
                    counts=counts,
                )
                await self._enqueue_changed_events(db, changed, counts)

                if page.has_more and page.next_checkpoint == current_checkpoint:
                    raise CollectorSecurityError(
                        CollectorErrorCode.INVALID_PROVIDER_RESPONSE,
                        "Provider pagination did not advance",
                    )
                checkpoint_version = await self._advance_checkpoint(
                    db,
                    provider_id=provider_id,
                    stream_key=stream_key,
                    cursor=page.next_checkpoint,
                    expected_version=checkpoint_version,
                    events=[event for event, _normalized in normalized_events],
                    run_id=run_id,  # type: ignore[arg-type]
                )
                current_checkpoint = page.next_checkpoint
                has_more = page.has_more
                await self._update_run_progress(db, run_id, counts, current_checkpoint)
                if not has_more:
                    break

            if not dry_run:
                run = await db.get(CollectorRun, run_id)
                if run is not None:
                    run.status = (
                        CollectorRunStatus.PARTIAL.value
                        if has_more
                        else CollectorRunStatus.SUCCEEDED.value
                    )
                    run.counts = counts
                    run.checkpoint_after = current_checkpoint
                    run.finished_at = _utcnow()
                    db.add(run)
                    checkpoint_row = await self._get_checkpoint(db, provider_id, stream_key, lock=True)
                    if checkpoint_row is not None and not has_more:
                        checkpoint_row.last_successful_run_id = run_id
                        db.add(checkpoint_row)
                    await db.commit()
            return counts
        except Exception as exc:
            await db.rollback()
            if not dry_run and run_id is not None:
                await self.mark_run_failed(
                    db,
                    run_id,
                    exc,
                    partial=any(counts.values()),
                    counts=counts,
                )
            raise

    def _normalize(
        self,
        provider: CollectorProvider,
        event: ExternalEvent,
    ) -> tuple[ExternalEvent, NormalizedEvent]:
        validate_external_event(event.external_id, event.raw_payload)
        try:
            normalized = provider.normalize(event)
            if not isinstance(normalized, NormalizedEvent):
                normalized = NormalizedEvent.model_validate(normalized)
            if normalized.source_url is not None:
                validate_allowed_url(str(normalized.source_url), provider.allowed_url_hosts)
            canonical_hash(normalized.model_dump(mode="json"))
            return event, normalized
        except CollectorSecurityError:
            raise
        except Exception:
            raise CollectorSecurityError(CollectorErrorCode.NORMALIZATION_FAILED) from None

    async def _persist_page(
        self,
        db: AsyncSession,
        *,
        provider: CollectorProvider,
        stream_key: str,
        run_id: int,
        events: list[tuple[ExternalEvent, NormalizedEvent]],
        counts: dict[str, int],
    ) -> list[tuple[int, int]]:
        now = _utcnow()
        changed: list[tuple[int, int]] = []
        for external, normalized in events:
            payload = normalized.model_dump(mode="json")
            payload_hash = canonical_hash(payload)
            insert_result = await db.execute(
                pg_insert(CollectorEvent)
                .values(
                    provider_id=provider.provider_id,
                    stream_key=stream_key,
                    external_id=external.external_id,
                    revision=1,
                    external_created_at=external.external_created_at,
                    external_updated_at=external.external_updated_at,
                    payload_hash=payload_hash,
                    normalized_payload=payload,
                    normalized_schema_version=normalized.schema_version,
                    status=CollectorEventStatus.DISCOVERED.value,
                    latest_run_id=run_id,
                    processor_version=provider.processor_version,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["provider_id", "stream_key", "external_id"]
                )
                .returning(CollectorEvent.id, CollectorEvent.revision)
            )
            inserted = insert_result.first()
            if inserted is not None:
                counts["new"] += 1
                changed.append((inserted.id, inserted.revision))
                await self._persist_revision_snapshot(
                    db,
                    event_id=inserted.id,
                    revision=inserted.revision,
                    payload_hash=payload_hash,
                    payload=payload,
                    external_updated_at=external.external_updated_at,
                    processor_version=provider.processor_version,
                    run_id=run_id,
                    created_at=now,
                )
                continue

            revised_result = await db.execute(
                update(CollectorEvent)
                .where(
                    CollectorEvent.provider_id == provider.provider_id,
                    CollectorEvent.stream_key == stream_key,
                    CollectorEvent.external_id == external.external_id,
                    CollectorEvent.payload_hash != payload_hash,
                )
                .values(
                    revision=CollectorEvent.revision + 1,
                    external_created_at=external.external_created_at,
                    external_updated_at=external.external_updated_at,
                    payload_hash=payload_hash,
                    normalized_payload=payload,
                    normalized_schema_version=normalized.schema_version,
                    status=CollectorEventStatus.DISCOVERED.value,
                    skip_code=None,
                    error_code=None,
                    error_summary=None,
                    validation_request=None,
                    validation_result=None,
                    latest_run_id=run_id,
                    processor_version=provider.processor_version,
                    processing_started_at=None,
                    updated_at=now,
                )
                .returning(CollectorEvent.id, CollectorEvent.revision)
            )
            revised = revised_result.first()
            if revised is not None:
                counts["revised"] += 1
                changed.append((revised.id, revised.revision))
                await self._persist_revision_snapshot(
                    db,
                    event_id=revised.id,
                    revision=revised.revision,
                    payload_hash=payload_hash,
                    payload=payload,
                    external_updated_at=external.external_updated_at,
                    processor_version=provider.processor_version,
                    run_id=run_id,
                    created_at=now,
                )
                continue

            await db.execute(
                update(CollectorEvent)
                .where(
                    CollectorEvent.provider_id == provider.provider_id,
                    CollectorEvent.stream_key == stream_key,
                    CollectorEvent.external_id == external.external_id,
                )
                .values(latest_run_id=run_id, updated_at=now)
            )
            counts["unchanged"] += 1

        await db.commit()
        return changed

    async def _persist_revision_snapshot(
        self,
        db: AsyncSession,
        *,
        event_id: int,
        revision: int,
        payload_hash: str,
        payload: dict[str, Any],
        external_updated_at: datetime | None,
        processor_version: str,
        run_id: int,
        created_at: datetime,
    ) -> None:
        await db.execute(
            pg_insert(CollectorEventRevision)
            .values(
                collector_event_id=event_id,
                revision=revision,
                payload_hash=payload_hash,
                normalized_payload=payload,
                external_updated_at=external_updated_at,
                processor_version=processor_version,
                observed_run_id=run_id,
                created_at=created_at,
            )
            .on_conflict_do_nothing(index_elements=["collector_event_id", "revision"])
        )

    async def _enqueue_changed_events(
        self,
        db: AsyncSession,
        changed: list[tuple[int, int]],
        counts: dict[str, int],
    ) -> None:
        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_COLLECTOR_PROCESS

        for event_id, revision in changed:
            try:
                await get_task_queue_service().enqueue(
                    task_name=TASK_COLLECTOR_PROCESS,
                    payload={"event_id": event_id, "revision": revision},
                    priority=20,
                    dedupe_key=collector_process_dedupe_key(event_id, revision),
                )
                counts["queued"] += 1
            except Exception:
                counts["failed"] += 1
                logger.exception(
                    "Collector event enqueue failed; reconciliation will recover it",
                    extra={"event_id": event_id, "revision": revision},
                )

    async def _advance_checkpoint(
        self,
        db: AsyncSession,
        *,
        provider_id: str,
        stream_key: str,
        cursor: dict[str, Any] | None,
        expected_version: int,
        events: list[ExternalEvent],
        run_id: int,
    ) -> int:
        now = _utcnow()
        await db.execute(
            pg_insert(CollectorCheckpoint)
            .values(
                provider_id=provider_id,
                stream_key=stream_key,
                cursor=None,
                version=1,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["provider_id", "stream_key"])
        )
        checkpoint = await self._get_checkpoint(db, provider_id, stream_key, lock=True)
        if checkpoint is None:
            raise RuntimeError("Collector checkpoint could not be created")
        actual_expected = 1 if expected_version == 0 else expected_version
        if checkpoint.version != actual_expected:
            raise CollectorSecurityError(
                CollectorErrorCode.STALE_REVISION,
                "Collector checkpoint changed during the run",
            )
        timestamps = [event.external_updated_at for event in events if event.external_updated_at]
        checkpoint.cursor = cursor
        checkpoint.version += 1
        checkpoint.updated_at = now
        if timestamps:
            page_high_watermark = max(timestamps)
            if checkpoint.high_watermark is None or page_high_watermark > checkpoint.high_watermark:
                checkpoint.high_watermark = page_high_watermark
        db.add(checkpoint)
        await db.commit()
        return checkpoint.version

    async def _get_checkpoint(
        self,
        db: AsyncSession,
        provider_id: str,
        stream_key: str,
        *,
        lock: bool = False,
    ) -> CollectorCheckpoint | None:
        statement = select(CollectorCheckpoint).where(
            CollectorCheckpoint.provider_id == provider_id,
            CollectorCheckpoint.stream_key == stream_key,
        )
        if lock:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def _update_run_progress(
        self,
        db: AsyncSession,
        run_id: int,
        counts: dict[str, int],
        checkpoint: dict[str, Any] | None,
    ) -> None:
        run = await db.get(CollectorRun, run_id)
        if run is not None:
            run.counts = dict(counts)
            run.checkpoint_after = checkpoint
            db.add(run)
            await db.commit()

    async def mark_run_failed(
        self,
        db: AsyncSession,
        run_id: int,
        exc: BaseException,
        *,
        partial: bool = False,
        counts: dict[str, int] | None = None,
    ) -> None:
        run = await db.get(CollectorRun, run_id)
        if run is None or run.status == CollectorRunStatus.SUCCEEDED.value:
            return
        code = exc.code if isinstance(exc, CollectorSecurityError) else CollectorErrorCode.PROVIDER_UNAVAILABLE
        run.status = CollectorRunStatus.PARTIAL.value if partial else CollectorRunStatus.FAILED.value
        run.error_code, run.error_summary = redacted_error(code, exc)
        run.finished_at = _utcnow()
        if counts is not None:
            run.counts = dict(counts)
        db.add(run)
        await db.commit()

    async def process_event(
        self,
        db: AsyncSession,
        *,
        event_id: int,
        revision: int,
    ) -> bool:
        event_result = await db.execute(
            select(CollectorEvent).where(CollectorEvent.id == event_id).with_for_update()
        )
        event = event_result.scalar_one_or_none()
        if event is None or event.revision != revision:
            await db.rollback()
            return False
        provider = collector_registry.require(event.provider_id)
        event.status = CollectorEventStatus.PROCESSING.value
        event.processing_started_at = _utcnow()
        event.error_code = None
        event.error_summary = None
        db.add(event)
        await db.commit()

        config = await self.configuration_snapshot(db, provider)
        normalized = NormalizedEvent.model_validate(event.normalized_payload)
        await db.rollback()
        context = CollectorContext(
            provider_id=event.provider_id,
            stream_key=event.stream_key,
            config=config,
            run_id=event.latest_run_id,
            event_id=event_id,
            event_revision=revision,
        )
        try:
            evaluation = await provider.evaluate(event=normalized, context=context)
            if evaluation.outcome is EvaluationOutcome.SKIPPED:
                await self._set_event_outcome(
                    db,
                    event_id,
                    revision,
                    status=CollectorEventStatus.SKIPPED,
                    skip_code=evaluation.skip_code,
                )
                return True

            if evaluation.outcome is EvaluationOutcome.AWAITING_VALIDATION:
                request = evaluation.validation_request
                if request is None:
                    raise ValueError("Deferred evaluation did not contain a validation request")
                await self._set_event_outcome(
                    db,
                    event_id,
                    revision,
                    status=CollectorEventStatus.AWAITING_VALIDATION,
                    validation_request=request.model_dump(mode="json"),
                )
                try:
                    await provider.request_validation(request=request, context=context)
                except Exception:
                    raise CollectorSecurityError(CollectorErrorCode.VALIDATION_FAILED) from None
                return True

            await self._ingest_findings(
                db,
                provider=provider,
                event_id=event_id,
                revision=revision,
                findings=evaluation.findings,
            )
            return True
        except Exception as exc:
            await db.rollback()
            code = (
                exc.code
                if isinstance(exc, CollectorSecurityError)
                else CollectorErrorCode.ALERT_INGESTION_FAILED
            )
            await self._set_event_failure(
                db,
                event_id,
                revision,
                code,
            )
            if isinstance(exc, CollectorSecurityError):
                raise
            raise CollectorSecurityError(code) from None

    async def _ingest_findings(
        self,
        db: AsyncSession,
        *,
        provider: CollectorProvider,
        event_id: int,
        revision: int,
        findings: list[NormalizedFinding],
    ) -> None:
        produced_keys: set[str] = set()
        for finding in findings:
            if finding.finding_key in produced_keys:
                raise ValueError("Provider produced duplicate finding keys for one event")
            produced_keys.add(finding.finding_key)
            await alert_ingestion_service.upsert_collector_finding(
                db,
                provider=provider,
                event_id=event_id,
                event_revision=revision,
                finding=finding,
            )

        existing_result = await db.execute(
            select(CollectorFinding).where(
                CollectorFinding.collector_event_id == event_id,
                CollectorFinding.status != CollectorFindingStatus.SUPERSEDED.value,
            )
        )
        for existing in existing_result.scalars().all():
            if existing.finding_key not in produced_keys:
                existing.status = CollectorFindingStatus.SUPERSEDED.value
                existing.updated_at = _utcnow()
                db.add(existing)

        event_result = await db.execute(
            select(CollectorEvent).where(CollectorEvent.id == event_id).with_for_update()
        )
        event = event_result.scalar_one_or_none()
        if event is None or event.revision != revision:
            await db.rollback()
            raise CollectorSecurityError(CollectorErrorCode.STALE_REVISION)
        event.status = CollectorEventStatus.IMPORTED.value
        event.processing_started_at = None
        event.updated_at = _utcnow()
        db.add(event)
        await db.commit()

    async def _set_event_outcome(
        self,
        db: AsyncSession,
        event_id: int,
        revision: int,
        *,
        status: CollectorEventStatus,
        skip_code: str | None = None,
        validation_request: dict[str, Any] | None = None,
    ) -> None:
        result = await db.execute(
            update(CollectorEvent)
            .where(CollectorEvent.id == event_id, CollectorEvent.revision == revision)
            .values(
                status=status.value,
                skip_code=skip_code,
                validation_request=validation_request,
                processing_started_at=None,
                updated_at=_utcnow(),
            )
        )
        if not result.rowcount:
            await db.rollback()
            raise CollectorSecurityError(CollectorErrorCode.STALE_REVISION)
        await db.commit()

    async def _set_event_failure(
        self,
        db: AsyncSession,
        event_id: int,
        revision: int,
        code: CollectorErrorCode,
    ) -> None:
        error_code, error_summary = redacted_error(code)
        await db.execute(
            update(CollectorEvent)
            .where(CollectorEvent.id == event_id, CollectorEvent.revision == revision)
            .values(
                status=CollectorEventStatus.FAILED.value,
                error_code=error_code,
                error_summary=error_summary,
                processing_started_at=None,
                updated_at=_utcnow(),
            )
        )
        await db.commit()

    async def record_validation(
        self,
        db: AsyncSession,
        *,
        provider_id: str,
        event_id: int,
        validator_identity: str,
        result: ValidationResult,
    ) -> None:
        canonical_hash(result.model_dump(mode="json"))
        event_result = await db.execute(
            select(CollectorEvent).where(CollectorEvent.id == event_id).with_for_update()
        )
        event = event_result.scalar_one_or_none()
        if event is None or event.provider_id != provider_id:
            raise ValueError("Collector event not found")
        if event.revision != result.event_revision:
            raise CollectorSecurityError(CollectorErrorCode.STALE_REVISION)
        provider = collector_registry.require(provider_id)
        try:
            provider.validate_validation_result(result)
        except Exception:
            raise CollectorSecurityError(CollectorErrorCode.VALIDATION_FAILED) from None
        request = event.validation_request or {}
        expected_validator = request.get("validator_id")
        if (
            not expected_validator
            or result.validator_id != expected_validator
            or validator_identity != expected_validator
        ):
            raise CollectorSecurityError(CollectorErrorCode.AUTHORIZATION_FAILED)

        event.validation_result = result.model_dump(mode="json")
        event.updated_at = _utcnow()
        if result.skipped:
            event.status = CollectorEventStatus.SKIPPED.value
            event.skip_code = result.skip_code
            db.add(event)
            await db.commit()
            return
        event.status = CollectorEventStatus.READY.value
        db.add(event)
        await db.commit()

        findings = [
            finding.model_copy(
                update={
                    "validation_payload": result.evidence,
                    "validation_report_ref": result.validation_report_ref,
                    "validator_version": result.validator_version,
                }
            )
            for finding in result.findings
        ]
        await self._ingest_findings(
            db,
            provider=provider,
            event_id=event_id,
            revision=result.event_revision,
            findings=findings,
        )

    async def retry_event(self, db: AsyncSession, event: CollectorEvent) -> str:
        from app.services.task_queue_service import get_task_queue_service
        from app.services.tasks import TASK_COLLECTOR_PROCESS

        event.status = CollectorEventStatus.DISCOVERED.value
        event.error_code = None
        event.error_summary = None
        event.processing_started_at = None
        provider = collector_registry.require(event.provider_id)
        event.processor_version = provider.processor_version
        event.updated_at = _utcnow()
        db.add(event)
        await db.commit()
        return await get_task_queue_service().enqueue(
            task_name=TASK_COLLECTOR_PROCESS,
            payload={"event_id": event.id, "revision": event.revision},
            priority=20,
            dedupe_key=collector_process_dedupe_key(event.id, event.revision),  # type: ignore[arg-type]
        )

    async def reconcile(self, db: AsyncSession) -> int:
        settings = SettingsService(db)  # type: ignore[arg-type]
        stale_seconds = int(await settings.get("collectors.processing_stale_seconds", 1800))
        cutoff = _utcnow() - timedelta(seconds=max(stale_seconds, 60))
        result = await db.execute(
            select(CollectorEvent).where(
                (CollectorEvent.status == CollectorEventStatus.DISCOVERED.value)
                | (CollectorEvent.status == CollectorEventStatus.READY.value)
                | (
                    (CollectorEvent.status == CollectorEventStatus.PROCESSING.value)
                    & (CollectorEvent.processing_started_at < cutoff)
                )
            )
        )
        recovered = 0
        for event in result.scalars().all():
            if event.status == CollectorEventStatus.PROCESSING.value:
                event.status = CollectorEventStatus.DISCOVERED.value
                event.processing_started_at = None
                db.add(event)
                await db.commit()
            try:
                await self.retry_event(db, event)
                recovered += 1
            except Exception:
                logger.exception(
                    "Collector reconciliation enqueue failed",
                    extra={"event_id": event.id, "provider_id": event.provider_id},
                )
        return recovered

    async def test_provider(
        self,
        db: AsyncSession,
        provider_id: str,
        stream_key: str = "default",
    ) -> CollectorConnectionTestResponse:
        provider = collector_registry.require(provider_id)
        config = await self.configuration_snapshot(db, provider)
        await db.rollback()
        context = CollectorContext(provider_id=provider_id, stream_key=stream_key, config=config)
        try:
            page = await provider.test_connection(context=context)
            for event in page.events:
                self._normalize(provider, event)
            return CollectorConnectionTestResponse(
                provider_id=provider_id,
                ok=True,
                event_count=len(page.events),
                has_more=page.has_more,
            )
        except Exception as exc:
            code = exc.code if isinstance(exc, CollectorSecurityError) else CollectorErrorCode.PROVIDER_UNAVAILABLE
            error_code, summary = redacted_error(code, exc)
            return CollectorConnectionTestResponse(
                provider_id=provider_id,
                ok=False,
                error_code=CollectorErrorCode(error_code),
                error_summary=summary,
            )

    async def provider_statuses(self, db: AsyncSession) -> list[CollectorProviderStatus]:
        statuses: list[CollectorProviderStatus] = []
        settings = SettingsService(db)  # type: ignore[arg-type]
        now = _utcnow()
        for provider in collector_registry.list():
            prefix = provider.settings_prefix
            pending_result = await db.execute(
                select(CollectorEvent.status, func.count(CollectorEvent.id))
                .where(
                    CollectorEvent.provider_id == provider.provider_id,
                    CollectorEvent.status.in_(
                        [
                            CollectorEventStatus.DISCOVERED.value,
                            CollectorEventStatus.PROCESSING.value,
                            CollectorEventStatus.AWAITING_VALIDATION.value,
                            CollectorEventStatus.READY.value,
                            CollectorEventStatus.FAILED.value,
                        ]
                    ),
                )
                .group_by(CollectorEvent.status)
            )
            latest_checkpoint = await db.execute(
                select(func.max(CollectorCheckpoint.updated_at)).where(
                    CollectorCheckpoint.provider_id == provider.provider_id
                )
            )
            checkpoint_at = latest_checkpoint.scalar_one_or_none()
            statuses.append(
                CollectorProviderStatus(
                    provider_id=provider.provider_id,
                    display_name=provider.display_name,
                    enabled=bool(await settings.get(f"{prefix}.enabled", False)),
                    schedule_enabled=bool(await settings.get(f"{prefix}.schedule_enabled", False)),
                    schedule_time_utc=await settings.get(f"{prefix}.schedule_time_utc", "") or None,
                    streams=list(provider.stream_keys),
                    checkpoint_age_seconds=(now - checkpoint_at).total_seconds() if checkpoint_at else None,
                    pending_events={status: count for status, count in pending_result.all()},
                )
            )
        return statuses


collector_service = CollectorService()
