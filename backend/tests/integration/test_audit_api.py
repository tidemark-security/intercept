from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import AuditLog
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    user,
) -> str:
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200

    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_admin_can_read_paginated_audit_logs(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory(username="audit_admin")
    session_cookie = await _login_user(client, session_maker, admin)

    base_time = datetime.now(timezone.utc)
    async with session_maker() as session:
        session.add_all(
            [
                AuditLog(
                    event_type="auth.login.success",
                    entity_type="user",
                    entity_id="user-1",
                    description="User login succeeded",
                    performed_by="audit_admin",
                    performed_at=base_time,
                ),
                AuditLog(
                    event_type="settings.updated",
                    entity_type="setting",
                    entity_id="setting-1",
                    description="Updated retention policy",
                    performed_by="audit_admin",
                    performed_at=base_time - timedelta(minutes=1),
                ),
                AuditLog(
                    event_type="settings.deleted",
                    entity_type="setting",
                    entity_id="setting-2",
                    description="Deleted stale setting",
                    performed_by="audit_admin",
                    performed_at=base_time - timedelta(minutes=2),
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/admin/audit",
        params={"page": 1, "size": 1, "entity_type": "setting"},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["size"] == 1
    assert payload["total"] == 2
    assert payload["pages"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["event_type"] == "settings.updated"


@pytest.mark.asyncio
async def test_admin_can_filter_audit_logs(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory(username="filter_admin")
    session_cookie = await _login_user(client, session_maker, admin)

    base_time = datetime.now(timezone.utc)
    async with session_maker() as session:
        session.add_all(
            [
                AuditLog(
                    event_type="settings.updated",
                    entity_type="setting",
                    entity_id="setting-1",
                    description="Updated retention policy",
                    performed_by="filter_admin",
                    performed_at=base_time,
                ),
                AuditLog(
                    event_type="auth.login.failure",
                    entity_type="user",
                    entity_id="user-2",
                    description="User login failed",
                    performed_by="other_admin",
                    performed_at=base_time - timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/api/v1/admin/audit",
        params={
            "page": 1,
            "size": 10,
            "event_type": ["settings.updated"],
            "entity_type": "setting",
            "performed_by": "filter_admin",
            "search": "retention",
            "start_date": (base_time - timedelta(hours=1)).isoformat(),
            "end_date": (base_time + timedelta(hours=1)).isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["event_type"] == "settings.updated"
    assert payload["items"][0]["entity_type"] == "setting"


@pytest.mark.asyncio
async def test_non_admin_cannot_read_audit_logs(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    analyst = analyst_user_factory(username="audit_analyst")
    session_cookie = await _login_user(client, session_maker, analyst)

    response = await client.get(
        "/api/v1/admin/audit",
        params={"page": 1, "size": 10},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_audit_event_types(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory(username="event_type_admin")
    session_cookie = await _login_user(client, session_maker, admin)

    response = await client.get(
        "/api/v1/admin/audit/event-types",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "auth.login.success" in payload
    assert "settings.updated" in payload