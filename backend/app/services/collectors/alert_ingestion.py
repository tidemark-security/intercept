"""Atomic collector finding-to-alert persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RealtimeEventType
from app.models.models import Alert, AlertCreate, CollectorEvent, CollectorFinding
from app.services.alert_service import alert_service
from app.services.audit_service import get_audit_service
from app.services.collectors.base import CollectorProvider
from app.services.collectors.models import (
    CollectorErrorCode,
    CollectorFindingStatus,
    NormalizedFinding,
    TriageEnqueueStatus,
    TriagePolicy,
)
from app.services.collectors.security import canonical_hash, validate_allowed_url
from app.services.realtime_service import emit_event
from app.services.tag_filter_utils import normalize_persisted_tags


@dataclass(slots=True)
class AlertIngestionResult:
    finding_id: int
    alert_id: int
    changed: bool
    triage_status: TriageEnqueueStatus


def build_alert_projection(provider: CollectorProvider, finding: NormalizedFinding) -> dict:
    source_url = str(finding.source_url) if finding.source_url else None
    if source_url is not None:
        validate_allowed_url(source_url, provider.allowed_url_hosts)
    return {
        "title": finding.title,
        "description": finding.description,
        "priority": finding.priority.value if finding.priority else None,
        "source": provider.alert_source,
        "tags": normalize_persisted_tags(finding.tags),
        "source_url": source_url,
        "metadata": finding.metadata,
    }


class AlertIngestionService:
    async def upsert_collector_finding(
        self,
        db: AsyncSession,
        *,
        provider: CollectorProvider,
        event_id: int,
        event_revision: int,
        finding: NormalizedFinding,
    ) -> AlertIngestionResult:
        projection = build_alert_projection(provider, finding)
        payload_hash = canonical_hash(projection)
        actor = f"collector:{provider.provider_id}"
        now = datetime.now(timezone.utc)

        try:
            event_result = await db.execute(
                select(CollectorEvent)
                .where(CollectorEvent.id == event_id)
                .with_for_update()
            )
            event = event_result.scalar_one_or_none()
            if event is None or event.revision != event_revision:
                raise ValueError(CollectorErrorCode.STALE_REVISION.value)

            await db.execute(
                pg_insert(CollectorFinding)
                .values(
                    collector_event_id=event_id,
                    event_revision=event_revision,
                    finding_key=finding.finding_key,
                    payload_hash=payload_hash,
                    alert_projection=projection,
                    assessment=finding.assessment,
                    validation_payload=finding.validation_payload,
                    validation_report_ref=finding.validation_report_ref,
                    validator_version=finding.validator_version,
                    status=CollectorFindingStatus.PENDING.value,
                    triage_policy=finding.triage_policy.value,
                    triage_status=(
                        TriageEnqueueStatus.PENDING.value
                        if finding.triage_policy is TriagePolicy.STANDARD
                        else TriageEnqueueStatus.NOT_REQUESTED.value
                    ),
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["collector_event_id", "finding_key"]
                )
            )
            finding_result = await db.execute(
                select(CollectorFinding)
                .where(
                    CollectorFinding.collector_event_id == event_id,
                    CollectorFinding.finding_key == finding.finding_key,
                )
                .with_for_update()
            )
            db_finding = finding_result.scalar_one()
            if db_finding.id is None:
                raise RuntimeError("Collector finding did not receive an identifier")

            unchanged = db_finding.alert_id is not None and db_finding.payload_hash == payload_hash
            if unchanged:
                previous_triage_policy = db_finding.triage_policy
                db_finding.event_revision = event_revision
                db_finding.status = CollectorFindingStatus.IMPORTED.value
                db_finding.assessment = finding.assessment
                db_finding.validation_payload = finding.validation_payload
                db_finding.validator_version = finding.validator_version
                db_finding.validation_report_ref = finding.validation_report_ref
                db_finding.triage_policy = finding.triage_policy.value
                should_enqueue_triage = (
                    finding.triage_policy is TriagePolicy.STANDARD
                    and previous_triage_policy != TriagePolicy.STANDARD.value
                )
                if should_enqueue_triage:
                    db_finding.triage_status = TriageEnqueueStatus.PENDING.value
                    db_finding.triage_error_code = None
                elif finding.triage_policy is TriagePolicy.SKIP:
                    db_finding.triage_status = TriageEnqueueStatus.NOT_REQUESTED.value
                    db_finding.triage_error_code = None
                db_finding.updated_at = now
                await db.commit()
                triage_status = TriageEnqueueStatus(db_finding.triage_status)
                if should_enqueue_triage:
                    outcome = await alert_service._auto_enqueue_triage(
                        db,
                        db_finding.alert_id,  # type: ignore[arg-type]
                    )
                    triage_status = TriageEnqueueStatus(outcome)
                    refreshed_finding = await db.get(CollectorFinding, db_finding.id)
                    if refreshed_finding is not None:
                        refreshed_finding.triage_status = triage_status.value
                        refreshed_finding.triage_error_code = (
                            CollectorErrorCode.ALERT_INGESTION_FAILED.value
                            if triage_status is TriageEnqueueStatus.FAILED
                            else None
                        )
                        refreshed_finding.updated_at = datetime.now(timezone.utc)
                        db.add(refreshed_finding)
                        await db.commit()
                return AlertIngestionResult(
                    finding_id=db_finding.id,
                    alert_id=db_finding.alert_id,  # type: ignore[arg-type]
                    changed=False,
                    triage_status=triage_status,
                )

            before = dict(db_finding.alert_projection or {})
            db_alert: Alert | None = None
            if db_finding.alert_id is not None:
                alert_result = await db.execute(
                    select(Alert).where(Alert.id == db_finding.alert_id).with_for_update()
                )
                db_alert = alert_result.scalar_one_or_none()

            if db_alert is None:
                db_alert = await alert_service.persist_alert(
                    db,
                    AlertCreate(
                        title=finding.title,
                        description=finding.description,
                        priority=finding.priority,
                        source=provider.alert_source,
                    ),
                    tags=finding.tags,
                )
                if db_alert.id is None:
                    raise RuntimeError("Collector alert did not receive an identifier")
                db_finding.alert_id = db_alert.id
            else:
                previous_collector_tags = {
                    str(tag).strip().lower() for tag in before.get("tags", []) if str(tag).strip()
                }
                preserved_tags = [
                    tag for tag in normalize_persisted_tags(db_alert.tags or [])
                    if tag.lower() not in previous_collector_tags
                ]
                db_alert.title = finding.title
                db_alert.description = finding.description
                db_alert.priority = finding.priority
                db_alert.source = provider.alert_source
                db_alert.tags = normalize_persisted_tags([*preserved_tags, *finding.tags])
                db_alert.updated_at = now
                db.add(db_alert)

            db_finding.event_revision = event_revision
            db_finding.payload_hash = payload_hash
            db_finding.alert_projection = projection
            db_finding.assessment = finding.assessment
            db_finding.validation_payload = finding.validation_payload
            db_finding.validation_report_ref = finding.validation_report_ref
            db_finding.validator_version = finding.validator_version
            db_finding.status = CollectorFindingStatus.IMPORTED.value
            db_finding.triage_policy = finding.triage_policy.value
            db_finding.triage_status = (
                TriageEnqueueStatus.PENDING.value
                if finding.triage_policy is TriagePolicy.STANDARD
                else TriageEnqueueStatus.NOT_REQUESTED.value
            )
            db_finding.triage_error_code = None
            db_finding.updated_at = now
            db.add(db_finding)

            await get_audit_service(db).log_event(
                event_type="collector.alert.upserted",
                entity_type="alert",
                entity_id=str(db_alert.id),
                description="Collector created or updated an alert",
                old_value=before or None,
                new_value=projection,
                performed_by=actor,
                extra_payload={
                    "provider_id": provider.provider_id,
                    "collector_event_id": event_id,
                    "collector_finding_id": db_finding.id,
                },
            )
            await emit_event(
                db,
                entity_type="alert",
                entity_id=db_alert.id,  # type: ignore[arg-type]
                event_type=RealtimeEventType.ENTITY_UPDATED,
                performed_by=actor,
            )
            await db.commit()

            triage_status = TriageEnqueueStatus.NOT_REQUESTED
            if finding.triage_policy is TriagePolicy.STANDARD:
                outcome = await alert_service._auto_enqueue_triage(db, db_alert.id)  # type: ignore[arg-type]
                triage_status = TriageEnqueueStatus(outcome)
                refreshed_finding = await db.get(CollectorFinding, db_finding.id)
                if refreshed_finding is not None:
                    refreshed_finding.triage_status = triage_status.value
                    refreshed_finding.triage_error_code = (
                        CollectorErrorCode.ALERT_INGESTION_FAILED.value
                        if triage_status is TriageEnqueueStatus.FAILED
                        else None
                    )
                    refreshed_finding.updated_at = datetime.now(timezone.utc)
                    db.add(refreshed_finding)
                    await db.commit()

            return AlertIngestionResult(
                finding_id=db_finding.id,
                alert_id=db_alert.id,  # type: ignore[arg-type]
                changed=True,
                triage_status=triage_status,
            )
        except Exception:
            await db.rollback()
            raise


alert_ingestion_service = AlertIngestionService()
