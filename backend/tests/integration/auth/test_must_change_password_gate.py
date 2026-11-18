from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import UserAccount
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _create_forced_change_session(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> tuple[UserAccount, str]:
    user = analyst_user_factory()
    user.must_change_password = True
    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["mustChangePassword"] is True
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return user, session_cookie


@pytest.mark.asyncio
async def test_forced_change_session_is_restricted_to_recovery_routes(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    _user, session_cookie = await _create_forced_change_session(
        client,
        session_maker,
        analyst_user_factory,
    )
    cookies = {"intercept_session": session_cookie}

    session_response = await client.get("/api/v1/auth/session", cookies=cookies)
    alerts_response = await client.get("/api/v1/alerts", cookies=cookies)
    passkeys_response = await client.get("/api/v1/auth/passkeys", cookies=cookies)
    logout_response = await client.post("/api/v1/auth/logout", cookies=cookies)

    assert session_response.status_code == 200
    assert session_response.json()["mustChangePassword"] is True
    assert alerts_response.status_code == 403
    assert "password change" in str(alerts_response.json()).lower()
    assert passkeys_response.status_code == 403
    assert "password change" in str(passkeys_response.json()).lower()
    assert logout_response.status_code == 204


@pytest.mark.asyncio
async def test_successful_password_change_removes_authorization_gate(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user, session_cookie = await _create_forced_change_session(
        client,
        session_maker,
        analyst_user_factory,
    )
    cookies = {"intercept_session": session_cookie}

    blocked_response = await client.get("/api/v1/alerts", cookies=cookies)
    assert blocked_response.status_code == 403

    change_response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": "ReplacementSecure!Pass123",
        },
        cookies=cookies,
    )
    assert change_response.status_code == 204, change_response.text
    rotated_cookie = change_response.cookies.get("intercept_session")
    assert rotated_cookie is not None

    allowed_response = await client.get(
        "/api/v1/alerts",
        cookies={"intercept_session": rotated_cookie},
    )
    assert allowed_response.status_code == 200, allowed_response.text

    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert refreshed.must_change_password is False
