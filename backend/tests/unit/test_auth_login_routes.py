from datetime import datetime, timedelta, timezone
import json
import logging
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)

from app.api import route_utils
from app.api.routes import auth as auth_routes
from app.models.enums import UserRole, UserStatus
from app.services.auth_service import LoginResult
from app.services.password_hash_work_service import PasswordHashWorkCapacityError


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [
                (b"user-agent", b"auth-route-test"),
                (b"x-request-id", b"request-123"),
            ],
            "client": ("203.0.113.20", 4321),
            "server": ("testserver", 80),
            "scheme": "https",
            "query_string": b"",
        }
    )


def _login_result(*, username: str = "route.user") -> LoginResult:
    user = SimpleNamespace(
        id=uuid4(),
        username=username,
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        must_change_password=True,
        last_login_at=None,
    )
    session = SimpleNamespace(
        id=uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    return LoginResult(
        user=user,
        session=session,
        session_token="opaque-session-token",
    )


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]


def _assert_login_payload(
    payload: auth_routes.LoginResponse,
    login_result: LoginResult,
) -> None:
    assert payload.user.id == login_result.user.id
    assert payload.user.username == login_result.user.username
    assert payload.user.role == login_result.user.role
    assert payload.user.status == login_result.user.status
    assert payload.session.sessionId == login_result.session.id
    assert payload.session.expiresAt == login_result.session.expires_at
    assert payload.mustChangePassword is True
    assert payload.localCredentialManagementAllowed is False
    assert payload.passwordLoginAllowed is False
    assert payload.passkeyAllowed is False
    assert payload.apiKeyAllowed is False


def _assert_authenticated_cookie_contract(response: Response) -> None:
    cookies = _cookie_headers(response)
    assert len(cookies) == 2

    session_cookie = next(
        cookie for cookie in cookies if cookie.startswith("intercept_session=")
    )
    csrf_cookie = next(cookie for cookie in cookies if cookie.startswith("XSRF-TOKEN="))

    assert session_cookie.startswith("intercept_session=opaque-session-token;")
    assert "HttpOnly" in session_cookie
    assert "Path=/" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Secure" in session_cookie

    assert csrf_cookie.startswith("XSRF-TOKEN=fixed-csrf-token;")
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Secure" in csrf_cookie


@pytest.mark.asyncio
async def test_password_login_builds_payload_and_cookies_after_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login_result = _login_result()
    response = Response()
    db = cast(AsyncSession, object())
    events: list[str] = []

    async def check_rate_limit(
        received_db: AsyncSession,
        source_address: str | None,
    ):
        assert received_db is db
        assert source_address == "203.0.113.20"
        events.append("rate-limit")
        return True, None

    async def authenticate(received_db: AsyncSession, **kwargs):
        assert received_db is db
        assert kwargs["username"] == "Route.User"
        assert kwargs["password"] == "password"
        assert kwargs["metadata"].to_payload() == {
            "correlation_id": "request-123",
            "ip_address": "203.0.113.20",
            "user_agent": "auth-route-test",
        }
        events.append("authenticate-and-audit")
        return login_result

    real_issue_cookies = auth_routes.issue_authenticated_session_cookies

    def issue_cookies(*args):
        events.append("cookies")
        return real_issue_cookies(*args)

    async def credential_capabilities(*_args, **_kwargs):
        events.append("credential-policy")
        return SimpleNamespace(
            password_login_allowed=False,
            passkey_allowed=False,
            api_key_allowed=False,
        )

    monkeypatch.setattr(auth_routes.auth_service, "check_rate_limit", check_rate_limit)
    monkeypatch.setattr(auth_routes.auth_service, "login", authenticate)
    monkeypatch.setattr(
        auth_routes,
        "issue_authenticated_session_cookies",
        issue_cookies,
    )
    monkeypatch.setattr(
        auth_routes,
        "_local_credential_capabilities",
        credential_capabilities,
    )
    monkeypatch.setattr(route_utils, "generate_csrf_token", lambda: "fixed-csrf-token")

    payload = await auth_routes.login(
        request=_request("/api/v1/auth/login"),
        response=response,
        body=auth_routes.LoginRequest(username="Route.User", password="password"),
        db=db,
    )

    assert isinstance(payload, auth_routes.LoginResponse)
    _assert_login_payload(payload, login_result)
    _assert_authenticated_cookie_contract(response)
    assert events == [
        "rate-limit",
        "authenticate-and-audit",
        "cookies",
        "credential-policy",
    ]


@pytest.mark.asyncio
async def test_password_login_returns_retryable_capacity_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Response()
    db = cast(AsyncSession, object())

    async def check_rate_limit(*_args, **_kwargs):
        return True, None

    async def capacity_full(*_args, **_kwargs):
        raise PasswordHashWorkCapacityError(retry_after_seconds=17)

    monkeypatch.setattr(auth_routes.auth_service, "check_rate_limit", check_rate_limit)
    monkeypatch.setattr(auth_routes.auth_service, "login", capacity_full)

    result = await auth_routes.login(
        request=_request("/api/v1/auth/login"),
        response=response,
        body=auth_routes.LoginRequest(username="Route.User", password="password"),
        db=db,
    )

    assert result.status_code == 429
    assert result.headers["Retry-After"] == "17"
    assert json.loads(result.body) == {
        "message": "Password processing is busy. Please try again later.",
        "fields": [],
    }


@pytest.mark.asyncio
async def test_passkey_login_builds_payload_and_cookies_after_session_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login_result = _login_result(username="passkey.user")
    response = Response()
    db = cast(AsyncSession, object())
    events: list[str] = []

    async def finish_authentication(received_db: AsyncSession, **kwargs):
        assert received_db is db
        assert kwargs == {
            "challenge": "challenge-123",
            "credential": {"id": "credential-123"},
        }
        events.append("passkey-authentication")
        return SimpleNamespace(user=login_result.user)

    async def create_session(received_db: AsyncSession, **kwargs):
        assert received_db is db
        assert kwargs["user"] is login_result.user
        assert kwargs["metadata"].to_payload() == {
            "correlation_id": "request-123",
            "ip_address": "203.0.113.20",
            "user_agent": "auth-route-test",
        }
        events.append("session-and-audit")
        return login_result

    real_issue_cookies = auth_routes.issue_authenticated_session_cookies

    def issue_cookies(*args):
        events.append("cookies")
        return real_issue_cookies(*args)

    async def credential_capabilities(*_args, **_kwargs):
        events.append("credential-policy")
        return SimpleNamespace(
            password_login_allowed=False,
            passkey_allowed=False,
            api_key_allowed=False,
        )

    monkeypatch.setattr(
        auth_routes.passkey_service,
        "finish_authentication",
        finish_authentication,
    )
    monkeypatch.setattr(
        auth_routes.auth_service,
        "create_session_for_user",
        create_session,
    )
    monkeypatch.setattr(
        auth_routes,
        "issue_authenticated_session_cookies",
        issue_cookies,
    )
    monkeypatch.setattr(
        auth_routes,
        "_local_credential_capabilities",
        credential_capabilities,
    )
    monkeypatch.setattr(route_utils, "generate_csrf_token", lambda: "fixed-csrf-token")

    payload = await auth_routes.finish_passkey_authentication(
        request=_request("/api/v1/auth/passkeys/authenticate/verify"),
        response=response,
        body=auth_routes.PasskeyFinishAuthenticationRequest(
            challenge="challenge-123",
            credential={"id": "credential-123"},
        ),
        db=db,
    )

    assert isinstance(payload, auth_routes.LoginResponse)
    _assert_login_payload(payload, login_result)
    _assert_authenticated_cookie_contract(response)
    assert login_result.user.last_login_at is not None
    assert events == [
        "passkey-authentication",
        "session-and-audit",
        "cookies",
        "credential-policy",
    ]


@pytest.mark.asyncio
async def test_passkey_registration_returns_client_error_for_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login_result = _login_result(username="passkey.user")
    db = cast(AsyncSession, object())

    async def require_user(*_args, **_kwargs):
        return login_result

    async def reject_registration(*_args, **_kwargs):
        raise InvalidRegistrationResponse("invalid registration response")

    monkeypatch.setattr(auth_routes, "_require_human_session_user", require_user)
    monkeypatch.setattr(
        auth_routes.passkey_service,
        "finish_registration",
        reject_registration,
    )

    response = await auth_routes.finish_passkey_registration(
        request=_request("/api/v1/auth/passkeys/register/verify"),
        body=auth_routes.PasskeyFinishRegistrationRequest(
            challenge="challenge-123",
            credential={"id": "credential-123"},
            name="Laptop",
        ),
        db=db,
    )

    assert response.status_code == 400
    assert json.loads(response.body) == {
        "message": "Unable to verify passkey registration.",
        "fields": [],
    }


@pytest.mark.asyncio
async def test_passkey_registration_reraises_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    login_result = _login_result(username="passkey.user")
    db = cast(AsyncSession, object())

    async def require_user(*_args, **_kwargs):
        return login_result

    async def fail_registration(*_args, **_kwargs):
        raise RuntimeError("database state is inconsistent")

    monkeypatch.setattr(auth_routes, "_require_human_session_user", require_user)
    monkeypatch.setattr(
        auth_routes.passkey_service,
        "finish_registration",
        fail_registration,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(
        RuntimeError,
        match="database state is inconsistent",
    ):
        await auth_routes.finish_passkey_registration(
            request=_request("/api/v1/auth/passkeys/register/verify"),
            body=auth_routes.PasskeyFinishRegistrationRequest(
                challenge="challenge-123",
                credential={"id": "credential-123"},
                name="Laptop",
            ),
            db=db,
        )

    assert "Unexpected error finishing passkey registration" in caplog.text


@pytest.mark.asyncio
async def test_passkey_authentication_returns_client_error_for_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = cast(AsyncSession, object())

    async def reject_authentication(*_args, **_kwargs):
        raise InvalidAuthenticationResponse("invalid authentication response")

    monkeypatch.setattr(
        auth_routes.passkey_service,
        "finish_authentication",
        reject_authentication,
    )

    response = await auth_routes.finish_passkey_authentication(
        request=_request("/api/v1/auth/passkeys/authenticate/verify"),
        response=Response(),
        body=auth_routes.PasskeyFinishAuthenticationRequest(
            challenge="challenge-123",
            credential={"id": "credential-123"},
        ),
        db=db,
    )

    assert response.status_code == 401
    assert json.loads(response.body) == {
        "message": "Unable to verify passkey authentication.",
        "fields": [],
    }


@pytest.mark.asyncio
async def test_passkey_authentication_reraises_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = cast(AsyncSession, object())

    async def fail_authentication(*_args, **_kwargs):
        raise RuntimeError("database state is inconsistent")

    monkeypatch.setattr(
        auth_routes.passkey_service,
        "finish_authentication",
        fail_authentication,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(
        RuntimeError,
        match="database state is inconsistent",
    ):
        await auth_routes.finish_passkey_authentication(
            request=_request("/api/v1/auth/passkeys/authenticate/verify"),
            response=Response(),
            body=auth_routes.PasskeyFinishAuthenticationRequest(
                challenge="challenge-123",
                credential={"id": "credential-123"},
            ),
            db=db,
        )

    assert "Unexpected error finishing passkey authentication" in caplog.text
