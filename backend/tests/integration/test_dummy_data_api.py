from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlmodel import col

from app.models.enums import AlertStatus
from app.models.models import Alert, Case
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
@pytest.mark.parametrize(
    ("link_alerts", "expected_linked_count"),
    [
        (False, 0),
        (True, 1),
    ],
)
async def test_populate_dummy_data_persists_generated_alerts(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    link_alerts: bool,
    expected_linked_count: int,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    response = await client.post(
        f"/api/v1/dummy-data/populate?cases_count=1&alerts_count=1&link_alerts={str(link_alerts).lower()}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["cases_created"] == 1
    assert payload["data"]["random_alerts_created"] == 1
    assert payload["data"]["alerts_linked_to_cases"] == expected_linked_count

    alert_ids = payload["data"]["alert_ids"]
    case_ids = payload["data"]["case_ids"]

    async with session_maker() as session:
        alerts = (
            await session.execute(select(Alert).where(col(Alert.id).in_(alert_ids)))
        ).scalars().all()
        cases = (
            await session.execute(select(Case).where(col(Case.id).in_(case_ids)))
        ).scalars().all()

    assert len(alerts) == payload["data"]["alerts_created"]
    assert len(cases) == payload["data"]["cases_created"]

    linked_alerts = [alert for alert in alerts if alert.case_id is not None]
    assert len(linked_alerts) == expected_linked_count

    if link_alerts:
        assert all(alert.status == AlertStatus.ESCALATED for alert in linked_alerts)
    else:
        assert all(alert.case_id is None for alert in alerts)