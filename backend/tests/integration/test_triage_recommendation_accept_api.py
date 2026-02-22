from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import AlertStatus, CaseStatus, Priority, RecommendationStatus, TriageDisposition
from app.models.models import Alert, Case, TriageRecommendation
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


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
async def test_accept_manual_recommendation_creates_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Suspicious command execution",
            description="Unknown command chain on endpoint",
            priority=Priority.MEDIUM,
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
            confidence=0.42,
            reasoning_bullets=["Signal is ambiguous and needs analyst validation"],
            recommended_actions=[{"title": "Collect host triage artifacts"}],
            suggested_status=AlertStatus.IN_PROGRESS,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is not None
    assert data["case_human_id"].startswith("CAS-")
    assert data["recommendation"]["status"] == RecommendationStatus.ACCEPTED.value

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == data["case_id"]
        assert refreshed_alert.status == AlertStatus.ESCALATED
        timeline_items = refreshed_alert.timeline_items or []
        note_items = [item for item in timeline_items if item.get("type") == "note"]
        assert any(
            "accepted AI recommendation" in (item.get("description") or "")
            and "linked alert to case" in (item.get("description") or "")
            for item in note_items
        )


@pytest.mark.asyncio
async def test_accept_closed_recommendation_closes_without_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Known scanner noise",
            description="Expected vulnerability scan traffic",
            priority=Priority.LOW,
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
            disposition=TriageDisposition.FALSE_POSITIVE,
            confidence=0.91,
            reasoning_bullets=["Matched known scanner signatures"],
            recommended_actions=[],
            suggested_status=AlertStatus.CLOSED_FP,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is None

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id is None
        assert refreshed_alert.status == AlertStatus.CLOSED_FP
        timeline_items = refreshed_alert.timeline_items or []
        note_items = [item for item in timeline_items if item.get("type") == "note"]
        assert any(
            "accepted AI recommendation" in (item.get("description") or "")
            and "set status to CLOSED_FP" in (item.get("description") or "")
            for item in note_items
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("disposition", "expected_closed_status"),
    [
        (TriageDisposition.FALSE_POSITIVE, AlertStatus.CLOSED_FP),
        (TriageDisposition.BENIGN, AlertStatus.CLOSED_BP),
        (TriageDisposition.DUPLICATE, AlertStatus.CLOSED_DUPLICATE),
    ],
)
async def test_accept_dismiss_disposition_without_suggested_status_closes_without_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    disposition: TriageDisposition,
    expected_closed_status: AlertStatus,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Alert with inferred close status",
            description="Recommendation omits suggested_status",
            priority=Priority.LOW,
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
            disposition=disposition,
            confidence=0.9,
            reasoning_bullets=["Disposition implies dismissal"],
            recommended_actions=[],
            suggested_status=None,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is None
    assert data["case_human_id"] is None

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id is None
        assert refreshed_alert.status == expected_closed_status


@pytest.mark.asyncio
async def test_accept_closed_recommendation_with_status_patch_disabled_escalates(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Potential false positive event",
            description="Needs confirmation",
            priority=Priority.LOW,
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
            disposition=TriageDisposition.FALSE_POSITIVE,
            confidence=0.88,
            reasoning_bullets=["Likely benign scanner behavior"],
            recommended_actions=[],
            suggested_status=AlertStatus.CLOSED_FP,
            request_escalate_to_case=False,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": False,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is not None
    assert data["case_human_id"].startswith("CAS-")

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == data["case_id"]
        assert refreshed_alert.status == AlertStatus.ESCALATED


@pytest.mark.asyncio
async def test_accept_escalation_on_already_linked_alert_reuses_case(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        existing_case = Case(
            title="Active investigation",
            description="Existing case",
            priority=Priority.HIGH,
            status=CaseStatus.IN_PROGRESS,
            assignee="analyst",
            created_by="analyst",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            timeline_items=[],
            tags=[],
        )
        session.add(existing_case)
        await session.flush()

        alert = Alert(
            title="Alert already linked",
            description="Linked alert should not create new case",
            priority=Priority.HIGH,
            source="EDR",
            status=AlertStatus.IN_PROGRESS,
            case_id=existing_case.id,
            linked_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.TRUE_POSITIVE,
            confidence=0.95,
            reasoning_bullets=["Clear malicious behavior"],
            recommended_actions=[{"title": "Isolate host"}],
            suggested_status=AlertStatus.ESCALATED,
            request_escalate_to_case=True,
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(recommendation)
        await session.commit()

        alert_id = alert.id
        existing_case_id = existing_case.id

    response = await client.post(
        f"/api/v1/alerts/{alert_id}/triage-recommendation/accept",
        json={
            "apply_status": True,
            "apply_priority": True,
            "apply_assignee": True,
            "apply_tags": True,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == existing_case_id

    async with session_maker() as session:
        refreshed_alert = await session.get(Alert, alert_id)
        assert refreshed_alert is not None
        assert refreshed_alert.case_id == existing_case_id
        assert refreshed_alert.status == AlertStatus.ESCALATED
