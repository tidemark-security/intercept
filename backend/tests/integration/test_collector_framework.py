from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.models.enums import Priority
from app.models.models import (
    Alert,
    CollectorCheckpoint,
    CollectorEvent,
    CollectorEventRevision,
    CollectorFinding,
    CollectorRun,
)
from app.services.collectors.base import CollectorProvider
from app.services.collectors.models import (
    CollectionPage,
    CollectorContext,
    CollectorErrorCode,
    CollectorEventStatus,
    CollectorRunTrigger,
    EvaluationResult,
    ExternalEvent,
    NormalizedEvent,
    NormalizedFinding,
    TriagePolicy,
    ValidationResult,
)
from app.services.collectors.registry import collector_registry
from app.services.collectors.security import CollectorSecurityError
from app.services.collectors.service import EMPTY_COUNTS, collector_service


class _FixtureCollector(CollectorProvider):
    provider_id = "framework_test"
    display_name = "Framework Test"
    settings_prefix = "collectors.framework_test"
    alert_source = "Framework Test"
    processor_version = "test-1"

    def __init__(self) -> None:
        self.title = "First revision"

    async def fetch_page(
        self,
        *,
        checkpoint: dict | None,
        context: CollectorContext,
    ) -> CollectionPage:
        return CollectionPage(
            events=[
                ExternalEvent(
                    external_id="external-1",
                    external_updated_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
                    raw_payload={"title": self.title},
                )
            ],
            next_checkpoint={"cursor": "complete"},
            has_more=False,
        )

    def normalize(self, event: ExternalEvent) -> NormalizedEvent:
        return NormalizedEvent(
            title=str(event.raw_payload["title"]),
            description="Normalized provider event",
            provider_updated_at=event.external_updated_at,
        )

    async def evaluate(
        self,
        *,
        event: NormalizedEvent,
        context: CollectorContext,
    ) -> EvaluationResult:
        return EvaluationResult.ready(
            [
                NormalizedFinding(
                    finding_key="target:one",
                    title=event.title,
                    description=event.description,
                    priority=Priority.HIGH,
                    tags=["framework-test"],
                    assessment="confirmed",
                    triage_policy=TriagePolicy.SKIP,
                )
            ]
        )


@pytest.fixture
def fixture_collector() -> _FixtureCollector:
    provider = _FixtureCollector()
    collector_registry._providers[provider.provider_id] = provider
    return provider


@pytest.mark.asyncio
async def test_collection_processing_and_revision_update_are_idempotent(
    session_maker: Any,
    fixture_collector: _FixtureCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = SimpleNamespace(enqueue=AsyncMock(return_value="job-1"))
    monkeypatch.setattr("app.services.task_queue_service.get_task_queue_service", lambda: queue)

    async def config_snapshot(db, provider):
        return {"enabled": True, "max_pages_per_run": 10}

    monkeypatch.setattr(collector_service, "configuration_snapshot", config_snapshot)

    async with session_maker() as db:
        first_counts = await collector_service.poll(
            db,
            provider_id=fixture_collector.provider_id,
        )
        assert first_counts["new"] == 1
        event = (await db.execute(select(CollectorEvent))).scalar_one()
        assert event.revision == 1
        await collector_service.process_event(db, event_id=event.id, revision=1)  # type: ignore[arg-type]

    async with session_maker() as db:
        alert = (await db.execute(select(Alert))).scalar_one()
        original_alert_id = alert.id
        assert alert.title == "First revision"

        unchanged_counts = await collector_service.poll(
            db,
            provider_id=fixture_collector.provider_id,
        )
        assert unchanged_counts["unchanged"] == 1
        assert (await db.execute(select(func.count(CollectorEvent.id)))).scalar_one() == 1

    fixture_collector.title = "Second revision"
    async with session_maker() as db:
        revised_counts = await collector_service.poll(
            db,
            provider_id=fixture_collector.provider_id,
        )
        assert revised_counts["revised"] == 1
        event = (await db.execute(select(CollectorEvent))).scalar_one()
        assert event.revision == 2
        await collector_service.process_event(db, event_id=event.id, revision=2)  # type: ignore[arg-type]

    async with session_maker() as db:
        alerts = (await db.execute(select(Alert))).scalars().all()
        findings = (await db.execute(select(CollectorFinding))).scalars().all()
        revisions = (await db.execute(select(CollectorEventRevision))).scalars().all()
        assert len(alerts) == 1
        assert alerts[0].id == original_alert_id
        assert alerts[0].title == "Second revision"
        assert len(findings) == 1
        assert findings[0].event_revision == 2
        assert len(revisions) == 2


@pytest.mark.asyncio
async def test_dry_run_does_not_mutate_collector_state(
    session_maker: Any,
    fixture_collector: _FixtureCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def config_snapshot(db, provider):
        return {"enabled": False, "max_pages_per_run": 10}

    monkeypatch.setattr(collector_service, "configuration_snapshot", config_snapshot)
    async with session_maker() as db:
        counts = await collector_service.poll(
            db,
            provider_id=fixture_collector.provider_id,
            dry_run=True,
        )
        assert counts["discovered"] == 1
        assert (await db.execute(select(func.count(CollectorRun.id)))).scalar_one() == 0
        assert (await db.execute(select(func.count(CollectorEvent.id)))).scalar_one() == 0
        assert (await db.execute(select(func.count(CollectorCheckpoint.id)))).scalar_one() == 0


@pytest.mark.asyncio
async def test_concurrent_event_receipts_create_one_event(
    session_maker: Any,
    fixture_collector: _FixtureCollector,
) -> None:
    async with session_maker() as setup_db:
        runs = [
            CollectorRun(
                provider_id=fixture_collector.provider_id,
                stream_key="default",
                trigger=CollectorRunTrigger.MANUAL.value,
                counts=dict(EMPTY_COUNTS),
            )
            for _ in range(2)
        ]
        setup_db.add_all(runs)
        await setup_db.commit()
        run_ids = [run.id for run in runs]

    external = ExternalEvent(external_id="same", raw_payload={"title": "same"})
    normalized = fixture_collector.normalize(external)

    async def persist(run_id: int) -> dict[str, int]:
        counts = dict(EMPTY_COUNTS)
        async with session_maker() as db:
            await collector_service._persist_page(
                db,
                provider=fixture_collector,
                stream_key="default",
                run_id=run_id,
                events=[(external, normalized)],
                counts=counts,
            )
        return counts

    counts = await asyncio.gather(*(persist(run_id) for run_id in run_ids if run_id is not None))
    assert sorted(item["new"] for item in counts) == [0, 1]

    async with session_maker() as db:
        assert (await db.execute(select(func.count(CollectorEvent.id)))).scalar_one() == 1
        assert (await db.execute(select(func.count(CollectorEventRevision.id)))).scalar_one() == 1


@pytest.mark.asyncio
async def test_validation_callback_rejects_stale_revision_and_wrong_validator(
    session_maker: Any,
    fixture_collector: _FixtureCollector,
) -> None:
    async with session_maker() as db:
        event = CollectorEvent(
            provider_id=fixture_collector.provider_id,
            stream_key="default",
            external_id="deferred-1",
            revision=2,
            payload_hash="a" * 64,
            normalized_payload={
                "schema_version": 1,
                "title": "Deferred event",
                "description": "Requires validation",
                "metadata": {},
            },
            status=CollectorEventStatus.AWAITING_VALIDATION.value,
            validation_request={
                "schema_version": 1,
                "validator_id": "supply-chain-validator",
                "evidence": {},
            },
            processor_version=fixture_collector.processor_version,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        event_id = event.id
        assert event_id is not None

        finding = NormalizedFinding(
            finding_key="target:validated",
            title="Validated exposure",
            assessment="confirmed",
            triage_policy=TriagePolicy.SKIP,
        )
        stale = ValidationResult(
            event_revision=1,
            validator_id="supply-chain-validator",
            validator_version="validator-1",
            assessment="confirmed",
            findings=[finding],
            evidence={"release": "main"},
        )
        with pytest.raises(CollectorSecurityError) as stale_error:
            await collector_service.record_validation(
                db,
                provider_id=fixture_collector.provider_id,
                event_id=event_id,
                validator_identity="supply-chain-validator",
                result=stale,
            )
        assert stale_error.value.code is CollectorErrorCode.STALE_REVISION
        await db.rollback()

        current = stale.model_copy(update={"event_revision": 2})
        with pytest.raises(CollectorSecurityError) as identity_error:
            await collector_service.record_validation(
                db,
                provider_id=fixture_collector.provider_id,
                event_id=event_id,
                validator_identity="different-validator",
                result=current,
            )
        assert identity_error.value.code is CollectorErrorCode.AUTHORIZATION_FAILED
        await db.rollback()

        await collector_service.record_validation(
            db,
            provider_id=fixture_collector.provider_id,
            event_id=event_id,
            validator_identity="supply-chain-validator",
            result=current,
        )

    async with session_maker() as db:
        imported_event = await db.get(CollectorEvent, event_id)
        assert imported_event is not None
        assert imported_event.status == CollectorEventStatus.IMPORTED.value
        assert (await db.execute(select(func.count(Alert.id)))).scalar_one() == 1
