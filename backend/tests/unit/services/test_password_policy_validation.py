import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import auth as auth_routes
from app.services import admin_auth_service as admin_auth_service_module
from app.services.admin_auth_service import AdminAuthService
from app.services.audit_service import AuditContext
from app.services.auth_service import (
    AuthService,
    PasswordPolicyViolation,
)


class _FakePasswordHasher:
    def __init__(self) -> None:
        self.hash_calls: list[str] = []

    def hash(self, password: str) -> str:
        self.hash_calls.append(password)
        return "hashed-password"

    def verify(self, _password_hash: str, _password: str) -> bool:
        return True


def _request(path: str, *, session_cookie: str | None = None) -> Request:
    headers = []
    if session_cookie is not None:
        headers.append((b"cookie", f"intercept_session={session_cookie}".encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers,
            "client": ("203.0.113.30", 4321),
            "server": ("testserver", 80),
            "scheme": "https",
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("password", "expected_message"),
    [
        ("  Short1!  ", "Password does not meet minimum length requirements"),
        (
            "nouppercase123!",
            "Password must include upper, lower, number, and special character",
        ),
    ],
)
async def test_auth_service_preserves_password_policy_errors_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    password: str,
    expected_message: str,
) -> None:
    hasher = _FakePasswordHasher()
    service = AuthService(password_hasher=hasher)  # type: ignore[arg-type]
    hasher.hash_calls.clear()
    db = AsyncMock(spec=AsyncSession)
    audit_factory = Mock()
    monkeypatch.setattr(
        "app.services.auth_service.get_audit_service",
        audit_factory,
    )

    with pytest.raises(PasswordPolicyViolation) as exc_info:
        await service.change_password(
            db,
            session_token="session-token",
            current_password="CurrentPassword123!",
            new_password=password,
            metadata=AuditContext(),
        )

    assert str(exc_info.value) == expected_message
    assert hasher.hash_calls == []
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    audit_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("password", "expected_message"),
    [
        ("  Short1!  ", "Password does not meet minimum length requirements"),
        (
            "nouppercase123!",
            "Password must include upper, lower, number, and special character",
        ),
    ],
)
async def test_admin_reset_preserves_password_policy_errors_before_token_lookup(
    monkeypatch: pytest.MonkeyPatch,
    password: str,
    expected_message: str,
) -> None:
    hasher = _FakePasswordHasher()
    service = AdminAuthService(password_hasher=hasher)  # type: ignore[arg-type]
    db = AsyncMock(spec=AsyncSession)
    audit_factory = Mock()
    monkeypatch.setattr(
        admin_auth_service_module,
        "get_audit_service",
        audit_factory,
    )

    with pytest.raises(PasswordPolicyViolation) as exc_info:
        await service.consume_reset_token(
            token="reset-token",
            new_password=password,
            request_metadata=AuditContext(),
            db=db,
        )

    assert str(exc_info.value) == expected_message
    assert hasher.hash_calls == []
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    audit_factory.assert_not_called()


@pytest.mark.asyncio
async def test_password_change_route_preserves_policy_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Password must include upper, lower, number, and special character"
    change_password = AsyncMock(side_effect=PasswordPolicyViolation(message))
    monkeypatch.setattr(auth_routes.auth_service, "change_password", change_password)

    result = await auth_routes.change_password(
        request=_request(
            "/api/v1/auth/password/change",
            session_cookie="session-token",
        ),
        response=Response(),
        body=auth_routes.PasswordChangeRequest(
            currentPassword="CurrentPassword123!",
            newPassword="nouppercase123!",
        ),
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.status_code == status.HTTP_400_BAD_REQUEST
    assert json.loads(result.body) == {"message": message, "fields": []}


@pytest.mark.asyncio
async def test_password_reset_route_preserves_policy_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Password does not meet minimum length requirements"
    consume_reset_token = AsyncMock(side_effect=PasswordPolicyViolation(message))
    monkeypatch.setattr(
        admin_auth_service_module.admin_auth_service,
        "consume_reset_token",
        consume_reset_token,
    )

    result = await auth_routes.reset_password_with_token(
        request=_request("/api/v1/auth/reset-password"),
        body=auth_routes.PasswordResetTokenRequest(
            token="reset-token",
            newPassword="ValidLengthButNoNumber!",
        ),
        db=AsyncMock(spec=AsyncSession),
    )

    assert result.status_code == status.HTTP_400_BAD_REQUEST
    assert json.loads(result.body) == {"message": message, "fields": []}
