from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from httpx import AsyncClient

from app.models.enums import RecommendationStatus, TriageDisposition
from app.models.models import Alert, ContextEntry, TriageRecommendation
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
        json={
            "title": "Updated title",
            "tags": [" Review ", "review", "Null", "escalated"],
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Updated title"
    assert payload["tags"] == ["Review", "escalated"]
    assert payload["triage_recommendation"] is not None
    assert payload["triage_recommendation"]["alert_id"] == alert_id


@pytest.mark.asyncio
async def test_get_alert_includes_global_context(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        alert = Alert(
            title="Context visibility alert",
            description="Alert should show global analyst context",
            source="Network IDS",
        )
        context_entry = ContextEntry(
            criteria=[],
            body="This is test context for all alerts",
            author="admin",
            expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        )
        session.add_all([alert, context_entry])
        await session.commit()
        assert alert.id is not None
        alert_id = alert.id
        assert context_entry.id is not None
        context_entry_id = context_entry.id

    response = await client.get(
        f"/api/v1/alerts/{alert_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["context"]["total_count"] == 1
    assert payload["context"]["omitted_count"] == 0
    assert payload["context"]["items"][0]["id"] == context_entry_id
    assert payload["context"]["items"][0]["criteria"] == []
    assert payload["context"]["items"][0]["body"] == "This is test context for all alerts"
    assert payload["context"]["items"][0]["author"] == "admin"


@pytest.mark.asyncio
async def test_get_alerts_serializes_legacy_list_backed_timeline_items(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    now = datetime.now(timezone.utc)

    async with session_maker() as session:
        alert = Alert(
            title="Legacy list-backed alert",
            description="Stored before object timeline migration",
            source="seed",
            timeline_items=cast(Any, []),
            created_at=now,
            updated_at=now,
        )
        session.add(alert)
        await session.commit()

    response = await client.get(
        "/api/v1/alerts",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    matching_alert = next(item for item in payload["items"] if item["title"] == "Legacy list-backed alert")
    assert matching_alert["timeline_items"] == {}


@pytest.mark.asyncio
async def test_get_alerts_filters_unassigned_sentinel(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        unassigned_alert = Alert(
            title="Unassigned alert",
            description="Should match sentinel filter",
            source="seed",
            assignee=None,
        )
        assigned_alert = Alert(
            title="Assigned alert",
            description="Should not match sentinel filter",
            source="seed",
            assignee="analyst-user",
        )
        session.add_all([unassigned_alert, assigned_alert])
        await session.commit()

    response = await client.get(
        "/api/v1/alerts",
        params={"assignee": "__unassigned__"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["items"]}
    assert "Unassigned alert" in titles
    assert "Assigned alert" not in titles
