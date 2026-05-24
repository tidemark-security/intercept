from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import AlertStatus, CaseStatus, Priority
from app.models.models import Alert, AuditLog, Case
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


async def _seed_alerts(session_maker: Any, count: int = 2) -> list[int]:
    async with session_maker() as session:
        alerts = [
            Alert(
                title=f"Bulk alert {index}",
                description="Bulk action target",
                priority=Priority.MEDIUM,
                source="SIEM",
                status=AlertStatus.NEW,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                tags=[],
            )
            for index in range(count)
        ]
        session.add_all(alerts)
        await session.flush()
        alert_ids = [alert.id for alert in alerts]
        await session.commit()
        return [alert_id for alert_id in alert_ids if alert_id is not None]


async def _seed_case(session_maker: Any) -> int:
    async with session_maker() as session:
        case = Case(
            title="Bulk target case",
            description="Existing case",
            priority=Priority.MEDIUM,
            status=CaseStatus.IN_PROGRESS,
            assignee="analyst",
            created_by="analyst",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            timeline_items={},
            tags=[],
        )
        session.add(case)
        await session.flush()
        assert case.id is not None
        case_id = case.id
        await session.commit()
        return case_id


@pytest.mark.asyncio
async def test_bulk_status_update_audits_every_alert(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    alert_ids = await _seed_alerts(session_maker)

    response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={
            "alert_ids": alert_ids,
            "action": "update_status",
            "status": AlertStatus.CLOSED_FP.value,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    assert response.json()["updated_count"] == len(alert_ids)

    async with session_maker() as session:
        for alert_id in alert_ids:
            alert = await session.get(Alert, alert_id)
            assert alert is not None
            assert alert.status == AlertStatus.CLOSED_FP
            assert alert.triaged_at is not None

            audit_result = await session.execute(
                select(AuditLog)
                .where(AuditLog.entity_type == "alert")
                .where(AuditLog.entity_id == str(alert_id))
                .where(AuditLog.event_type == "entity.updated")
            )
            assert audit_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_bulk_link_existing_case_links_all_selected_alerts(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    alert_ids = await _seed_alerts(session_maker)
    case_id = await _seed_case(session_maker)

    response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={"alert_ids": alert_ids, "action": "link_case", "case_id": case_id},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    async with session_maker() as session:
        for alert_id in alert_ids:
            alert = await session.get(Alert, alert_id)
            assert alert is not None
            assert alert.case_id == case_id
            assert alert.status == AlertStatus.ESCALATED


@pytest.mark.asyncio
async def test_bulk_create_case_creates_one_case_and_links_selected_alerts(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    alert_ids = await _seed_alerts(session_maker, count=3)

    response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={
            "alert_ids": alert_ids,
            "action": "create_case",
            "case_title": "Bulk investigation",
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] is not None
    assert data["case_human_id"].startswith("CAS-")

    async with session_maker() as session:
        cases = (await session.execute(select(Case))).scalars().all()
        assert len(cases) == 1
        for alert_id in alert_ids:
            alert = await session.get(Alert, alert_id)
            assert alert is not None
            assert alert.case_id == data["case_id"]
            assert alert.status == AlertStatus.ESCALATED


@pytest.mark.asyncio
async def test_bulk_close_duplicate_requires_target_and_add_tags_merges(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)
    alert_ids = await _seed_alerts(session_maker)
    case_id = await _seed_case(session_maker)

    invalid_response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={"alert_ids": alert_ids, "action": "close_duplicate"},
        cookies={"intercept_session": session_cookie},
    )
    assert invalid_response.status_code == 422

    duplicate_response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={
            "alert_ids": alert_ids,
            "action": "close_duplicate",
            "duplicate_target_case_id": case_id,
        },
        cookies={"intercept_session": session_cookie},
    )
    assert duplicate_response.status_code == 200

    tag_response = await client.post(
        "/api/v1/alerts/bulk-actions",
        json={"alert_ids": alert_ids, "action": "add_tags", "tags": ["bulk", "review"]},
        cookies={"intercept_session": session_cookie},
    )
    assert tag_response.status_code == 200

    async with session_maker() as session:
        for alert_id in alert_ids:
            alert = await session.get(Alert, alert_id)
            assert alert is not None
            assert alert.status == AlertStatus.CLOSED_DUPLICATE
            assert alert.case_id == case_id
            assert alert.tags == ["bulk", "review"]
