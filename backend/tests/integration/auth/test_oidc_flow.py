from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_registry import get_local
from app.models.models import AuthSession
from app.services.auth_service import LoginResult
from app.services.oidc_service import OIDCStateError


class _FakeAuditService:
    async def oidc_login_success(self, **_: Any) -> None:
        return None

    async def oidc_login_failure(self, **_: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_begin_oidc_login_sets_browser_binding_cookie(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    async def fake_is_safe_redirect_target(_db, target: str) -> bool:
        return target == "http://localhost:5173/"

    async def fake_begin_login(_db, *, redirect_to: str, callback_url: str):
        assert redirect_to == "http://localhost:5173/"
        assert callback_url.endswith("/api/v1/auth/oidc/callback")
        return "https://idp.example/authorize", expires_at, "browser-binding-token"

    monkeypatch.setattr(oidc_routes.oidc_service, "is_safe_redirect_target", fake_is_safe_redirect_target)
    monkeypatch.setattr(oidc_routes.oidc_service, "begin_login", fake_begin_login)

    response = await client.get(
        "/api/v1/auth/oidc/login",
        params={"next": "http://localhost:5173/"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://idp.example/authorize"
    assert response.cookies.get(get_local("oidc.browser_binding.cookie_name")) == "browser-binding-token"


@pytest.mark.asyncio
async def test_oidc_callback_sets_session_and_csrf_cookies(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    user = analyst_user_factory(username="oidc.user")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    async def fake_exchange_code(
        _db,
        *,
        code: str,
        state: str,
        callback_url: str,
        browser_binding_token: str | None,
    ):
        assert code == "auth-code"
        assert state == "state-token"
        assert callback_url.endswith("/api/v1/auth/oidc/callback")
        assert browser_binding_token == "browser-binding-token"
        return user, "https://idp.example", "subject-123", "http://localhost:5173/"

    async def fake_create_session_for_user(_db, *, user, metadata):
        return LoginResult(
            user=user,
            session=AuthSession(
                id=uuid4(),
                user_id=user.id,
                issued_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
                expires_at=expires_at,
                session_token_hash="hash",
            ),
            session_token="oidc-session-token",
        )

    monkeypatch.setattr(oidc_routes.oidc_service, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(oidc_routes.auth_service, "create_session_for_user", fake_create_session_for_user)
    monkeypatch.setattr(oidc_routes, "get_audit_service", lambda _db: _FakeAuditService())

    response = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "auth-code", "state": "state-token"},
        cookies={get_local("oidc.browser_binding.cookie_name"): "browser-binding-token"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:5173/"
    assert response.cookies.get(get_local("auth.session.cookie_name")) == "oidc-session-token"
    assert response.cookies.get(get_local("auth.csrf.cookie_name")) is not None


@pytest.mark.asyncio
async def test_oidc_callback_rejects_missing_browser_binding_cookie(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.oidc as oidc_routes

    async def fake_exchange_code(
        _db,
        *,
        code: str,
        state: str,
        callback_url: str,
        browser_binding_token: str | None,
    ):
        assert code == "auth-code"
        assert state == "state-token"
        assert callback_url.endswith("/api/v1/auth/oidc/callback")
        assert browser_binding_token is None
        raise OIDCStateError("OIDC browser binding cookie is missing")

    monkeypatch.setattr(oidc_routes.oidc_service, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(oidc_routes, "get_audit_service", lambda _db: _FakeAuditService())

    response = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "auth-code", "state": "state-token"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "error=oidc_failed" in response.headers["location"]