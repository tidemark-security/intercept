from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import admin_auth as admin_auth_routes
from app.api.routes import auth as auth_routes
from app.models.enums import UserRole, UserStatus
from app.services.admin_auth_service import (
    AdminAuthConflictError,
    AdminAuthNotFoundError,
    AdminAuthService,
    AdminAuthValidationError,
    admin_auth_service,
)


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("203.0.113.10", 4321),
            "server": ("testserver", 80),
            "scheme": "https",
            "query_string": b"",
        }
    )


async def _invoke_admin_route(operation: str) -> object:
    admin_user = SimpleNamespace(id=uuid4())
    target_user_id = uuid4()
    db = cast(AsyncSession, object())

    if operation == "create":
        return await admin_auth_routes.create_user(
            request=_request("/api/v1/admin/auth/users"),
            payload=admin_auth_routes.AdminCreateUserRequest(
                username="new.user",
                email="new.user@example.com",
                role=UserRole.ANALYST,
            ),
            db=db,
            admin_user=admin_user,
        )
    if operation == "status":
        return await admin_auth_routes.update_user_status(
            user_id=target_user_id,
            request=_request(f"/api/v1/admin/auth/users/{target_user_id}/status"),
            payload=admin_auth_routes.AdminUpdateStatusRequest(status=UserStatus.DISABLED),
            db=db,
            admin_user=admin_user,
        )
    if operation == "update":
        return await admin_auth_routes.update_user(
            user_id=target_user_id,
            request=_request(f"/api/v1/admin/auth/users/{target_user_id}"),
            payload=admin_auth_routes.AdminUpdateUserRequest(description="Detection engineer"),
            db=db,
            admin_user=admin_user,
        )
    if operation == "reset":
        return await admin_auth_routes.issue_password_reset(
            request=_request("/api/v1/admin/auth/password-resets"),
            payload=admin_auth_routes.AdminResetPasswordRequest(userId=target_user_id),
            db=db,
            admin_user=admin_user,
        )
    raise AssertionError(f"Unknown operation: {operation}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "error", "expected_status"),
    [
        (
            "create",
            AdminAuthConflictError("Username 'new.user' already exists"),
            status.HTTP_400_BAD_REQUEST,
        ),
        (
            "status",
            AdminAuthNotFoundError("User with ID 1 not found"),
            status.HTTP_404_NOT_FOUND,
        ),
        (
            "update",
            AdminAuthValidationError("Only NHI accounts can be made assignable"),
            status.HTTP_400_BAD_REQUEST,
        ),
        (
            "reset",
            AdminAuthNotFoundError("User with ID 1 not found"),
            status.HTTP_404_NOT_FOUND,
        ),
    ],
)
async def test_admin_routes_map_only_typed_domain_errors(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    error: Exception,
    expected_status: int,
) -> None:
    method_name = {
        "create": "create_user",
        "status": "update_user_status",
        "update": "update_user",
        "reset": "issue_password_reset",
    }[operation]
    monkeypatch.setattr(
        admin_auth_service,
        method_name,
        AsyncMock(side_effect=error),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _invoke_admin_route(operation)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == {
        "message": str(error),
        "fields": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "status", "update", "reset"])
async def test_admin_routes_do_not_misclassify_unexpected_value_errors(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    method_name = {
        "create": "create_user",
        "status": "update_user_status",
        "update": "update_user",
        "reset": "issue_password_reset",
    }[operation]
    monkeypatch.setattr(
        admin_auth_service,
        method_name,
        AsyncMock(side_effect=ValueError("internal serialization defect")),
    )

    with pytest.raises(ValueError, match="internal serialization defect"):
        await _invoke_admin_route(operation)


@pytest.mark.asyncio
async def test_admin_auth_service_uses_conflict_for_duplicate_username() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(object())),
    )
    service = AdminAuthService(password_hasher=SimpleNamespace())

    with pytest.raises(AdminAuthConflictError, match="already exists"):
        await service.create_user(
            admin_user_id=uuid4(),
            username="existing.user",
            email=None,
            role=UserRole.ANALYST,
            request_metadata=SimpleNamespace(),
            db=cast(AsyncSession, db),
        )


@pytest.mark.asyncio
async def test_admin_auth_service_uses_not_found_for_missing_target() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(None)),
    )
    service = AdminAuthService(password_hasher=SimpleNamespace())

    with pytest.raises(AdminAuthNotFoundError, match="not found"):
        await service.update_user_status(
            admin_user_id=uuid4(),
            target_user_id=uuid4(),
            new_status=UserStatus.DISABLED,
            request_metadata=SimpleNamespace(),
            db=cast(AsyncSession, db),
        )


@pytest.mark.asyncio
async def test_admin_auth_service_uses_validation_for_invalid_operation() -> None:
    user_id = uuid4()
    service = AdminAuthService(password_hasher=SimpleNamespace())

    with pytest.raises(AdminAuthValidationError, match="own account status"):
        await service.update_user_status(
            admin_user_id=user_id,
            target_user_id=user_id,
            new_status=UserStatus.DISABLED,
            request_metadata=SimpleNamespace(),
            db=cast(AsyncSession, object()),
        )


@pytest.mark.asyncio
async def test_admin_auth_service_uses_validation_for_invalid_reset_token() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(None)),
    )
    service = AdminAuthService(password_hasher=SimpleNamespace())

    with pytest.raises(AdminAuthValidationError, match="token is invalid"):
        await service.consume_reset_token(
            token="missing-reset-token",
            new_password="NewSecurePassword123!",
            request_metadata=SimpleNamespace(),
            db=cast(AsyncSession, db),
        )


@pytest.mark.asyncio
async def test_reset_token_route_maps_only_typed_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "Password reset token is invalid"
    monkeypatch.setattr(
        admin_auth_service,
        "consume_reset_token",
        AsyncMock(side_effect=AdminAuthValidationError(message)),
    )

    response = await auth_routes.reset_password_with_token(
        request=_request("/api/v1/auth/reset-password"),
        body=auth_routes.PasswordResetTokenRequest(
            token="reset-token",
            newPassword="NewSecurePassword123!",
        ),
        db=cast(AsyncSession, object()),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert json.loads(response.body) == {"message": message, "fields": []}


@pytest.mark.asyncio
async def test_reset_token_route_propagates_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin_auth_service,
        "consume_reset_token",
        AsyncMock(side_effect=ValueError("internal token defect")),
    )

    with pytest.raises(ValueError, match="internal token defect"):
        await auth_routes.reset_password_with_token(
            request=_request("/api/v1/auth/reset-password"),
            body=auth_routes.PasswordResetTokenRequest(
                token="reset-token",
                newPassword="NewSecurePassword123!",
            ),
            db=cast(AsyncSession, object()),
        )
