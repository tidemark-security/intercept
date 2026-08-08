from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.csrf import CSRFMiddleware
from app.core.settings_registry import get_local
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import Case, UserAccount
from app.services.api_key_service import api_key_service
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
    session_cookie, csrf_cookie = await _login_and_get_auth_cookies(
        client,
        session_maker,
        analyst_user_factory,
    )

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
    session_cookie, csrf_cookie = await _login_and_get_auth_cookies(
        client,
        session_maker,
        analyst_user_factory,
    )

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


@pytest.mark.asyncio
async def test_password_change_rejects_invalid_authorization_header_without_csrf(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    monkeypatch.setenv("CSRF_ENABLED", "true")
    session_cookie, csrf_cookie = await _login_and_get_auth_cookies(
        client,
        session_maker,
        analyst_user_factory,
    )

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
        headers={"Authorization": "Bearer not-a-real-api-key"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["message"] == "CSRF validation failed"


@pytest.mark.asyncio
async def test_valid_api_key_request_skips_csrf_even_with_session_cookie(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    monkeypatch.setenv("CSRF_ENABLED", "true")
    human_user = analyst_user_factory()
    nhi_user = UserAccount(
        username=f"svc.csrf.{uuid4().hex[:6]}",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
        description="CSRF API key test account",
    )
    async with session_maker() as session:
        session.add(human_user)
        session.add(nhi_user)
        await session.commit()
        _, raw_key = await api_key_service.create_api_key(
            session,
            user_id=nhi_user.id,
            name="csrf-test-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": human_user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get(get_local("auth.session.cookie_name"))
    csrf_cookie = login_response.cookies.get(get_local("auth.csrf.cookie_name"))
    assert session_cookie is not None
    assert csrf_cookie is not None

    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "API key CSRF bypass check",
            "description": "Created by valid NHI API key",
        },
        cookies={
            get_local("auth.session.cookie_name"): session_cookie,
            get_local("auth.csrf.cookie_name"): csrf_cookie,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "API key CSRF bypass check"


@pytest.mark.asyncio
async def test_api_key_is_revalidated_after_csrf_middleware_authentication(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    monkeypatch.setenv("CSRF_ENABLED", "true")
    human_user = analyst_user_factory()
    nhi_user = UserAccount(
        username=f"svc.csrf.revalidate.{uuid4().hex[:6]}",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        account_type=AccountType.NHI,
        description="CSRF API key revalidation account",
    )
    async with session_maker() as session:
        session.add_all([human_user, nhi_user])
        await session.commit()
        api_key, raw_key = await api_key_service.create_api_key(
            session,
            user_id=nhi_user.id,
            name="csrf-revalidation-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        await session.commit()
        api_key_id = api_key.id

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": human_user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get(
        get_local("auth.session.cookie_name")
    )
    assert session_cookie is not None

    original_authenticate = CSRFMiddleware._authenticate_api_key
    revoked_after_middleware_auth = False

    async def authenticate_then_revoke(
        middleware: CSRFMiddleware,
        scope: dict[str, Any],
        headers: Any,
        presented_key: str,
    ) -> bool:
        nonlocal revoked_after_middleware_auth
        authenticated = await original_authenticate(
            middleware,
            scope,
            headers,
            presented_key,
        )
        if authenticated and not revoked_after_middleware_auth:
            async with session_maker() as session:
                await api_key_service.revoke_api_key(
                    session,
                    api_key_id=api_key_id,
                )
                await session.commit()
            revoked_after_middleware_auth = True
        return authenticated

    monkeypatch.setattr(
        CSRFMiddleware,
        "_authenticate_api_key",
        authenticate_then_revoke,
    )

    case_title = "Must not cross CSRF API-key revocation"
    response = await client.post(
        "/api/v1/cases",
        json={"title": case_title},
        cookies={get_local("auth.session.cookie_name"): session_cookie},
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert revoked_after_middleware_auth is True
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["message"] == "API key has been revoked"
    async with session_maker() as session:
        assert (
            await session.scalar(select(Case).where(Case.title == case_title))
            is None
        )
