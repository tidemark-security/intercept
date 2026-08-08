from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import api_keys as api_key_routes
from app.models.enums import UserRole
from app.services.api_key_service import (
    ApiKeyExpirationError,
    ApiKeyUserNotFoundError,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/api-keys",
            "headers": [],
            "client": ("203.0.113.10", 1234),
            "server": ("testserver", 80),
            "scheme": "https",
            "query_string": b"",
        }
    )


def _body() -> api_key_routes.CreateApiKeyRequest:
    return api_key_routes.CreateApiKeyRequest(
        name="automation",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ApiKeyExpirationError("Expiration date must be in the future"), 400),
        (ApiKeyUserNotFoundError("User not found"), 404),
    ],
)
async def test_create_api_key_maps_only_expected_service_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    create = AsyncMock(side_effect=error)
    monkeypatch.setattr(api_key_routes.api_key_service, "create_api_key", create)
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.ANALYST)

    with pytest.raises(HTTPException) as exc_info:
        await api_key_routes.create_api_key(
            request=_request(),
            body=_body(),
            db=cast(AsyncSession, object()),
            current_user=current_user,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail["message"] == str(error)


@pytest.mark.asyncio
async def test_create_api_key_does_not_misclassify_unexpected_value_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = AsyncMock(side_effect=ValueError("service defect"))
    monkeypatch.setattr(api_key_routes.api_key_service, "create_api_key", create)
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.ANALYST)

    with pytest.raises(ValueError, match="service defect"):
        await api_key_routes.create_api_key(
            request=_request(),
            body=_body(),
            db=cast(AsyncSession, object()),
            current_user=current_user,  # type: ignore[arg-type]
        )
