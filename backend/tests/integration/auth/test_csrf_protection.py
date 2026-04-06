from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_registry import get_local
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_auth_cookies(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> tuple[str, str]:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    session_cookie = login_response.cookies.get(get_local("auth.session.cookie_name"))
    csrf_cookie = login_response.cookies.get(get_local("auth.csrf.cookie_name"))
    assert session_cookie is not None
    assert csrf_cookie is not None
    return session_cookie, csrf_cookie


@pytest.mark.asyncio
@pytest.mark.skipif(
    not get_local("auth.csrf.enabled"),
    reason="CSRF protection is disabled",
)
async def test_password_change_rejects_missing_csrf_header(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    session_cookie, csrf_cookie = await _login_and_get_auth_cookies(client, session_maker, analyst_user_factory)

    response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": "BrandNewPassword123!",
        },
        cookies={
            get_local("auth.session.cookie_name"): session_cookie,
            get_local("auth.csrf.cookie_name"): csrf_cookie,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["message"] == "CSRF validation failed"


@pytest.mark.asyncio
async def test_password_change_accepts_matching_csrf_header(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    session_cookie, csrf_cookie = await _login_and_get_auth_cookies(client, session_maker, analyst_user_factory)

    response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": "BrandNewPassword123!",
        },
        cookies={
            get_local("auth.session.cookie_name"): session_cookie,
            get_local("auth.csrf.cookie_name"): csrf_cookie,
        },
        headers={get_local("auth.csrf.header_name"): csrf_cookie},
    )

    assert response.status_code == 204