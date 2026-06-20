from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import AlertStatus, RecommendationStatus, TriageDisposition
from app.models.models import Alert, Case, TriageRecommendation
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _timeline_values(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        return [item for item in items.values() if isinstance(item, dict)]
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


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
    session_cookie = await _login_and_get_session_cookie(
        client,
        session_maker,
        analyst_user_factory,
    )

    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "Case serialization check",
            "description": "Created through API",
            "tags": [" Review ", "review", "Null", "escalated"],
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Case serialization check"
    assert payload["human_id"].startswith("CAS-")
    assert payload["timeline_items"] == {}
    assert payload["tags"] == ["Review", "escalated"]


@pytest.mark.asyncio
async def test_update_case_normalizes_tags(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        case = Case(
            title="Case with tags",
            description="Stored before update",
            created_by="seed-user",
            tags=["existing"],
        )
        session.add(case)
        await session.commit()
        assert case.id is not None
        case_id = case.id

    response = await client.put(
        f"/api/v1/cases/{case_id}",
        json={"tags": [" existing ", "Existing", "Null", "triage"]},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["existing", "triage"]


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
@pytest.mark.parametrize(
    "search_template",
    ["CAS-{case_id:07d}", "cas-{case_id:07d}", "{case_id}"],
)
async def test_get_cases_search_matches_case_human_id(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    search_template: str,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        matching_case = Case(
            title="Human ID target",
            description="Should be found by case number",
            created_by="seed-user",
        )
        other_case = Case(
            title="Different case",
            description="Does not mention the target number",
            created_by="seed-user",
        )
        session.add_all([matching_case, other_case])
        await session.flush()
        assert matching_case.id is not None
        assert other_case.id is not None
        matching_case_id = matching_case.id
        other_case_id = other_case.id
        await session.commit()

    response = await client.get(
        "/api/v1/cases",
        params={"search": search_template.format(case_id=matching_case_id)},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    result_ids = {item["id"] for item in payload["items"]}
    assert matching_case_id in result_ids
    assert other_case_id not in result_ids


@pytest.mark.asyncio
async def test_get_cases_search_matches_long_case_human_id(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        matching_case = Case(
            id=10000000,
            title="Long human ID target",
            description="Should be found by its full case number",
            created_by="seed-user",
        )
        session.add(matching_case)
        await session.commit()

    response = await client.get(
        "/api/v1/cases",
        params={"search": "CAS-10000000"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    result_ids = {item["id"] for item in payload["items"]}
    assert 10000000 in result_ids


@pytest.mark.asyncio
async def test_get_cases_filters_unassigned_sentinel(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        unassigned_case = Case(
            title="Unassigned case",
            description="Should match sentinel filter",
            created_by="seed-user",
            assignee=None,
        )
        assigned_case = Case(
            title="Assigned case",
            description="Should not match sentinel filter",
            created_by="seed-user",
            assignee="analyst-user",
        )
        session.add_all([unassigned_case, assigned_case])
        await session.commit()

    response = await client.get(
        "/api/v1/cases",
        params={"assignee": "__unassigned__"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["items"]}
    assert "Unassigned case" in titles
    assert "Assigned case" not in titles


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


@pytest.mark.asyncio
async def test_closing_case_with_summary_adds_case_timeline_note_only(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        case = Case(
            title="Closure summary case",
            description="Case closed with a markdown summary",
            created_by="seed-user",
        )
        session.add(case)
        await session.flush()
        assert case.id is not None

        alert = Alert(
            title="Linked alert",
            description="Should close unchanged",
            source="SIEM",
            case_id=case.id,
        )
        session.add(alert)
        await session.commit()
        case_id = case.id
        alert_id = alert.id
        assert alert_id is not None

    summary = "  **Resolution**\n\n- Confirmed benign  "
    response = await client.put(
        f"/api/v1/cases/{case_id}",
        json={
            "status": "CLOSED",
            "alert_closure_updates": [
                {"alert_id": alert_id, "status": "CLOSED_FP"},
            ],
            "closure_summary": summary,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200, response.text
    case_items = _timeline_values(response.json()["timeline_items"])
    summary_notes = [
        item for item in case_items
        if item["type"] == "note" and item["description"] == summary.strip()
    ]
    assert len(summary_notes) == 1
    assert summary_notes[0]["tags"] == ["case-closure"]

    async with session_maker() as session:
        linked_alert = await session.get(Alert, alert_id)
        assert linked_alert is not None
        assert linked_alert.status == AlertStatus.CLOSED_FP
        alert_items = _timeline_values(linked_alert.timeline_items)
        assert all(item.get("description") != summary.strip() for item in alert_items)
        assert any(
            item.get("type") == "note"
            and "Alert closed automatically as False Positive due to case" in item.get("description", "")
            for item in alert_items
        )


@pytest.mark.asyncio
async def test_closing_case_with_blank_summary_creates_no_timeline_note(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async with session_maker() as session:
        case = Case(
            title="Blank closure summary case",
            description="Case closed without a note",
            created_by="seed-user",
        )
        session.add(case)
        await session.commit()
        case_id = case.id
        assert case_id is not None

    response = await client.put(
        f"/api/v1/cases/{case_id}",
        json={
            "status": "CLOSED",
            "closure_summary": "  \n\t  ",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200, response.text
    assert _timeline_values(response.json()["timeline_items"]) == []
