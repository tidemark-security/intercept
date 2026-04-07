from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import RecommendationStatus, TriageDisposition
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
async def test_create_case_serializes_response_after_reload(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "Case serialization check",
            "description": "Created through API",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Case serialization check"
    assert payload["human_id"].startswith("CAS-")
    assert payload["timeline_items"] == {}


@pytest.mark.asyncio
async def test_get_cases_serializes_legacy_list_backed_timeline_items(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    now = datetime.now(timezone.utc)

    async with session_maker() as session:
        case = Case(
            title="Legacy list-backed case",
            description="Stored before object timeline migration",
            created_by="seed-user",
            timeline_items=[],
            created_at=now,
            updated_at=now,
        )
        session.add(case)
        await session.commit()

    response = await client.get(
        "/api/v1/cases",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    matching_case = next(item for item in payload["items"] if item["title"] == "Legacy list-backed case")
    assert matching_case["timeline_items"] == {}


@pytest.mark.asyncio
async def test_get_case_serializes_nested_alert_triage_recommendation(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        case = Case(
            title="Nested serialization case",
            description="Contains alerts",
            created_by="seed-user",
        )
        session.add(case)
        await session.flush()
        assert case.id is not None

        alert_with_recommendation = Alert(
            title="Alert with recommendation",
            description="Nested in case detail",
            source="SIEM",
            case_id=case.id,
        )
        alert_without_recommendation = Alert(
            title="Alert without recommendation",
            description="Also nested in case detail",
            source="EDR",
            case_id=case.id,
        )
        session.add_all([alert_with_recommendation, alert_without_recommendation])
        await session.flush()
        assert alert_with_recommendation.id is not None
        assert alert_without_recommendation.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert_with_recommendation.id,
            disposition=TriageDisposition.UNKNOWN,
            confidence=0.5,
            reasoning_bullets=["Nested recommendation"],
            recommended_actions=[],
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
        )
        session.add(recommendation)
        await session.commit()
        case_id = case.id
        alert_with_recommendation_id = alert_with_recommendation.id
        alert_without_recommendation_id = alert_without_recommendation.id

    response = await client.get(
        f"/api/v1/cases/{case_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == case_id

    alerts_by_id = {alert["id"]: alert for alert in payload["alerts"]}
    assert alerts_by_id[alert_with_recommendation_id]["triage_recommendation"] is not None
    assert alerts_by_id[alert_with_recommendation_id]["triage_recommendation"]["alert_id"] == alert_with_recommendation_id
    assert alerts_by_id[alert_without_recommendation_id]["triage_recommendation"] is None