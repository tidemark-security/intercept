from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from sqlmodel import select

from app.models.enums import (
    AlertStatus,
    Priority,
    RecommendationStatus,
    RejectionCategory,
    TriageDisposition,
)
from app.models.models import Alert, TriageRecommendation
from app.services import triage_recommendation_service


async def _create_alert(session: Any) -> Alert:
    alert = Alert(
        title="Service normalization alert",
        description="Direct service caller test",
        priority=Priority.MEDIUM,
        source="SIEM",
        status=AlertStatus.NEW,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(alert)
    await session.flush()
    assert alert.id is not None
    return alert


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "input_escalate", "input_status", "expected_escalate", "expected_status"),
    [
        ("BENIGN", True, AlertStatus.ESCALATED.value, False, AlertStatus.CLOSED_BP),
        ("UNKNOWN", False, AlertStatus.CLOSED_UNRESOLVED.value, True, AlertStatus.ESCALATED),
    ],
)
async def test_create_or_replace_recommendation_normalizes_direct_callers(
    session_maker: Any,
    disposition: str,
    input_escalate: bool,
    input_status: str,
    expected_escalate: bool,
    expected_status: AlertStatus,
) -> None:
    async with session_maker() as session:
        alert = await _create_alert(session)

        recommendation = await triage_recommendation_service.create_or_replace_recommendation(
            db=session,
            alert_id=alert.id,
            data={
                "disposition": disposition,
                "confidence": 0.8,
                "reasoning_bullets": ["Direct caller supplied contradictory case-path data"],
                "recommended_actions": [],
                "suggested_status": input_status,
                "request_escalate_to_case": input_escalate,
            },
            created_by="service-test",
        )

    assert recommendation.request_escalate_to_case is expected_escalate
    assert recommendation.suggested_status == expected_status


@pytest.mark.asyncio
async def test_create_or_replace_recommendation_rejects_invalid_suggested_status(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        alert = await _create_alert(session)

        with pytest.raises(
            triage_recommendation_service.TriageRecommendationValidationError,
            match="Invalid suggested_status",
        ):
            await triage_recommendation_service.create_or_replace_recommendation(
                db=session,
                alert_id=alert.id,
                data={
                    "disposition": "TRUE_POSITIVE",
                    "confidence": 0.8,
                    "reasoning_bullets": [],
                    "recommended_actions": [],
                    "suggested_status": "NOT_A_STATUS",
                    "request_escalate_to_case": False,
                },
                created_by="service-test",
            )


@pytest.mark.asyncio
async def test_create_or_replace_recommendation_rejects_dismissal_work(
    session_maker: Any,
) -> None:
    async with session_maker() as session:
        alert = await _create_alert(session)

        with pytest.raises(
            triage_recommendation_service.TriageRecommendationValidationError,
            match="Dismissal recommendations cannot include work recommendations",
        ):
            await triage_recommendation_service.create_or_replace_recommendation(
                db=session,
                alert_id=alert.id,
                data={
                    "disposition": "FALSE_POSITIVE",
                    "confidence": 0.8,
                    "reasoning_bullets": [],
                    "recommended_actions": [{"title": "Investigate anyway"}],
                    "request_escalate_to_case": True,
                },
                created_by="service-test",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing_status",
    [RecommendationStatus.ACCEPTED, RecommendationStatus.REJECTED],
)
async def test_enqueue_triage_resets_existing_recommendation_in_place(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
    existing_status: RecommendationStatus,
) -> None:
    enqueue = AsyncMock(return_value="job-1")

    async def fake_get(self, key: str):
        assert key == "langflow.alert_triage_flow_id"
        return "flow-1"

    monkeypatch.setattr(
        "app.services.settings_service.SettingsService.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: SimpleNamespace(enqueue=enqueue),
    )

    async with session_maker() as session:
        alert = await _create_alert(session)
        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.TRUE_POSITIVE,
            confidence=0.9,
            reasoning_bullets=["old reasoning"],
            recommended_actions=[{"title": "old action"}],
            suggested_status=AlertStatus.ESCALATED,
            suggested_priority=Priority.HIGH,
            suggested_assignee="old-user",
            suggested_tags_add=["old-tag"],
            request_escalate_to_case=True,
            created_by="old-user",
            status=existing_status,
            reviewed_by="reviewer",
            reviewed_at=datetime.now(timezone.utc),
            rejection_category=RejectionCategory.OTHER,
            rejection_reason="old reason",
            applied_changes=[{"field": "status"}],
        )
        session.add(recommendation)
        await session.commit()
        await session.refresh(recommendation)
        original_id = recommendation.id

        queued = await triage_recommendation_service.enqueue_triage(
            session,
            alert.id,
            enqueued_by="analyst",
        )

        rows = (await session.execute(
            select(TriageRecommendation).where(TriageRecommendation.alert_id == alert.id)
        )).scalars().all()

    assert len(rows) == 1
    assert queued.id == original_id
    assert queued.status == RecommendationStatus.QUEUED
    assert queued.disposition == TriageDisposition.UNKNOWN
    assert queued.confidence == 0.0
    assert queued.reasoning_bullets == []
    assert queued.recommended_actions == []
    assert queued.suggested_status is None
    assert queued.suggested_priority is None
    assert queued.suggested_assignee is None
    assert queued.suggested_tags_add == []
    assert queued.request_escalate_to_case is False
    assert queued.reviewed_by is None
    assert queued.reviewed_at is None
    assert queued.rejection_category is None
    assert queued.rejection_reason is None
    assert queued.applied_changes == []
    assert queued.error_message is None
    enqueue.assert_awaited_once_with(
        task_name="triage_alert",
        payload={"alert_id": alert.id},
        dedupe_key=f"triage_alert:{alert.id}",
    )


@pytest.mark.asyncio
async def test_concurrent_enqueue_serializes_and_keeps_one_recommendation(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, key: str):
        assert key == "langflow.alert_triage_flow_id"
        return "flow-1"

    enqueue = AsyncMock(return_value="job-1")
    monkeypatch.setattr(
        "app.services.settings_service.SettingsService.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: SimpleNamespace(enqueue=enqueue),
    )

    async with session_maker() as session:
        alert = await _create_alert(session)
        await session.commit()
        alert_id = alert.id

    async def enqueue_as(username: str) -> None:
        async with session_maker() as session:
            await triage_recommendation_service.enqueue_triage(
                session,
                alert_id,
                enqueued_by=username,
            )

    await asyncio.gather(enqueue_as("analyst-one"), enqueue_as("analyst-two"))

    async with session_maker() as session:
        rows = (
            await session.execute(
                select(TriageRecommendation).where(
                    TriageRecommendation.alert_id == alert_id
                )
            )
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].status == RecommendationStatus.QUEUED
    assert rows[0].created_by in {"analyst-one", "analyst-two"}
    assert enqueue.await_count == 2
    assert {
        call.kwargs["dedupe_key"] for call in enqueue.await_args_list
    } == {f"triage_alert:{alert_id}"}


@pytest.mark.asyncio
async def test_older_enqueue_failure_does_not_overwrite_newer_success(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, key: str):
        assert key == "langflow.alert_triage_flow_id"
        return "flow-1"

    first_started = asyncio.Event()
    second_finished = asyncio.Event()
    calls = 0

    async def enqueue(**_: Any) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            await second_finished.wait()
            raise ConnectionError("queue write failed")
        second_finished.set()
        return "job-2"

    monkeypatch.setattr(
        "app.services.settings_service.SettingsService.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.task_queue_service.get_task_queue_service",
        lambda: SimpleNamespace(enqueue=enqueue),
    )

    async with session_maker() as session:
        alert = await _create_alert(session)
        await session.commit()
        alert_id = alert.id

    async def enqueue_as(username: str) -> None:
        async with session_maker() as session:
            await triage_recommendation_service.enqueue_triage(
                session,
                alert_id,
                enqueued_by=username,
            )

    first = asyncio.create_task(enqueue_as("older-attempt"))
    await first_started.wait()
    await enqueue_as("newer-attempt")
    await first

    async with session_maker() as session:
        recommendation = (
            await session.execute(
                select(TriageRecommendation).where(
                    TriageRecommendation.alert_id == alert_id
                )
            )
        ).scalar_one()

    assert recommendation.created_by == "newer-attempt"
    assert recommendation.status == RecommendationStatus.QUEUED
    assert recommendation.error_message is None


@pytest.mark.asyncio
async def test_acceptance_refreshes_stale_alert_after_lock(
    session_maker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage_recommendation_service, "emit_event", AsyncMock())
    async with session_maker() as setup_session:
        alert = await _create_alert(setup_session)
        alert.tags = ["base"]
        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.FALSE_POSITIVE,
            confidence=0.9,
            reasoning_bullets=["Known activity"],
            recommended_actions=[],
            suggested_status=AlertStatus.CLOSED_FP,
            suggested_tags_add=["triage"],
            request_escalate_to_case=False,
            created_by="triage-agent",
            status=RecommendationStatus.PENDING,
        )
        setup_session.add(recommendation)
        await setup_session.commit()
        alert_id = alert.id

    async with session_maker() as acceptance_session, session_maker() as writer_session:
        stale_alert = await acceptance_session.get(Alert, alert_id)
        assert stale_alert is not None
        assert stale_alert.tags == ["base"]

        writer_alert = await writer_session.get(Alert, alert_id)
        assert writer_alert is not None
        writer_alert.tags = ["base", "writer"]
        await writer_session.commit()

        await triage_recommendation_service.accept_recommendation(
            acceptance_session,
            alert_id=alert_id,
            options=triage_recommendation_service.AcceptRecommendationOptions(),
            reviewed_by="analyst",
        )

    async with session_maker() as verification_session:
        stored_alert = await verification_session.get(Alert, alert_id)

    assert stored_alert is not None
    assert stored_alert.tags == ["base", "writer", "triage"]
