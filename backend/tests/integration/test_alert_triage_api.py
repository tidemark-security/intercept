from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from pgqueuer.errors import MaxRetriesExceeded

from app.models.enums import (
    AlertStatus,
    CaseStatus,
    Priority,
    RealtimeEventType,
    RecommendationStatus,
    RejectionCategory,
    TriageDisposition,
)
from app.models.models import Alert, Case, TriageRecommendation
from app.services.tasks import _handle_triage_terminal_failure, _mark_triage_failed
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _make_retries_exhausted_error(message: str) -> MaxRetriesExceeded:
    try:
        raise RuntimeError(message)
    except RuntimeError as root_cause:
        try:
            raise MaxRetriesExceeded(4) from root_cause
        except MaxRetriesExceeded as exc:
            return exc


async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> str:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_manual_triage_auto_rejects_pending_recommendation(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Suspicious script",
            description="Potential malicious PowerShell",
            priority=Priority.HIGH,
            source="EDR",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.NEEDS_INVESTIGATION,
            confidence=0.64,
            reasoning_bullets=["Observed suspicious process ancestry"],
            recommended_actions=[],
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage",
        json={
            "status": AlertStatus.CLOSED_TP.value,
            "triage_notes": "Confirmed true positive",
            "escalate_to_case": False,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.status == AlertStatus.CLOSED_TP
        assert refreshed_alert.triaged_at is not None
        assert refreshed_alert.assignee is not None

        refreshed_recommendation = await session.get(TriageRecommendation, recommendation.id)
        assert refreshed_recommendation is not None
        assert refreshed_recommendation.status == RecommendationStatus.REJECTED
        assert refreshed_recommendation.rejection_category == RejectionCategory.SUPERSEDED_MANUAL_TRIAGE


@pytest.mark.asyncio
async def test_link_case_auto_rejects_pending_recommendation(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        case = Case(
            title="Active investigation",
            description="Test case",
            priority=Priority.MEDIUM,
            status=CaseStatus.IN_PROGRESS,
            assignee="analyst",
            created_by="analyst",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            timeline_items=[],
            tags=[],
        )
        session.add(case)
        await session.flush()

        alert = Alert(
            title="Unlinked alert",
            description="Needs case link",
            priority=Priority.MEDIUM,
            source="SIEM",
            status=AlertStatus.NEW,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.TRUE_POSITIVE,
            confidence=0.77,
            reasoning_bullets=["Likely malicious"],
            recommended_actions=[],
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()

        alert_id = alert.id
        case_id = case.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/link-case/{case_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == case_id
        assert refreshed_alert.status == AlertStatus.ESCALATED
        assert refreshed_alert.triaged_at is not None
        assert refreshed_alert.assignee is not None

        refreshed_recommendation = await session.get(TriageRecommendation, recommendation.id)
        assert refreshed_recommendation is not None
        assert refreshed_recommendation.status == RecommendationStatus.REJECTED
        assert refreshed_recommendation.rejection_category == RejectionCategory.SUPERSEDED_MANUAL_TRIAGE


@pytest.mark.asyncio
async def test_mark_triage_failed_emits_realtime_event(
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.triage-failure")

    async with session_maker() as session:
        session.add(analyst)
        alert = Alert(
            title="Triage failure alert",
            description="Test alert",
            priority=Priority.MEDIUM,
            source="SIEM",
            status=AlertStatus.NEW,
            created_by=analyst.username,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.UNKNOWN,
            confidence=0.0,
            reasoning_bullets=[],
            recommended_actions=[],
            created_by="system",
            status=RecommendationStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id
        recommendation_id = recommendation.id

    emitted_events: list[dict[str, object]] = []

    async def fake_emit_event(
        db: Any,
        *,
        entity_type: str,
        entity_id: int,
        event_type: RealtimeEventType,
        performed_by: str,
        item_id: str | None = None,
    ) -> None:
        emitted_events.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_type": event_type,
                "performed_by": performed_by,
                "item_id": item_id,
            }
        )

    monkeypatch.setattr("app.services.tasks.emit_event", fake_emit_event)
    monkeypatch.setattr("app.services.tasks.async_session_factory", session_maker)

    await _mark_triage_failed(alert_id, "worker triage failed")

    assert emitted_events == [
        {
            "entity_type": "alert",
            "entity_id": alert_id,
            "event_type": RealtimeEventType.TRIAGE_COMPLETED,
            "performed_by": "system",
            "item_id": None,
        }
    ]

    async with session_maker() as session:
        refreshed_recommendation = await session.get(TriageRecommendation, recommendation_id)
        assert refreshed_recommendation is not None
        assert refreshed_recommendation.status == RecommendationStatus.FAILED
        assert refreshed_recommendation.error_message == "worker triage failed"


@pytest.mark.asyncio
async def test_triage_terminal_failure_marks_recommendation_failed_after_retries_exhausted(
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyst = analyst_user_factory(username="analyst.triage-terminal-failure")

    async with session_maker() as session:
        session.add(analyst)
        alert = Alert(
            title="Triage terminal failure alert",
            description="Test alert",
            priority=Priority.MEDIUM,
            source="SIEM",
            status=AlertStatus.NEW,
            created_by=analyst.username,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.UNKNOWN,
            confidence=0.0,
            reasoning_bullets=[],
            recommended_actions=[],
            created_by="system",
            status=RecommendationStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id
        recommendation_id = recommendation.id

    monkeypatch.setattr("app.services.tasks.async_session_factory", session_maker)

    await _handle_triage_terminal_failure(
        {"alert_id": alert_id},
        _make_retries_exhausted_error("langflow unavailable"),
    )

    async with session_maker() as session:
        refreshed_recommendation = await session.get(TriageRecommendation, recommendation_id)
        assert refreshed_recommendation is not None
        assert refreshed_recommendation.status == RecommendationStatus.FAILED
        assert refreshed_recommendation.error_message == "Retries exhausted: langflow unavailable"
