from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import RecommendationStatus, TriageDisposition
from app.models.models import Alert, TriageRecommendation
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
async def test_create_alert_returns_unloaded_optional_relationships_as_null(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    response = await client.post(
        "/api/v1/alerts",
        json={
            "title": "TEST",
            "description": "# This is a tes.t",
            "priority": "INFO",
            "source": "Swagger",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "TEST"
    assert payload["source"] == "Swagger"
    assert "triage_recommendation" in payload
    triage_recommendation = payload["triage_recommendation"]
    if triage_recommendation is not None:
        assert triage_recommendation["alert_id"] == payload["id"]


@pytest.mark.asyncio
async def test_update_alert_serializes_loaded_triage_recommendation(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Initial title",
            description="Initial description",
            source="EDR",
        )
        session.add(alert)
        await session.flush()
        assert alert.id is not None

        recommendation = TriageRecommendation(
            alert_id=alert.id,
            disposition=TriageDisposition.UNKNOWN,
            confidence=0.25,
            reasoning_bullets=["Needs review"],
            recommended_actions=[],
            created_by="test-ai",
            status=RecommendationStatus.PENDING,
        )
        session.add(recommendation)
        await session.commit()
        alert_id = alert.id

    response = await client.put(
        f"/api/v1/alerts/{alert_id}",
        json={"title": "Updated title"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Updated title"
    assert payload["triage_recommendation"] is not None
    assert payload["triage_recommendation"]["alert_id"] == alert_id