from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import admin_auth
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.models import UserAccount
from app.services.api_key_service import ApiKeyScopeError
from app.core.api_key_scopes import API_WRITE_SCOPE


@pytest.fixture
def role_dependency_app() -> FastAPI:
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(admin_auth.require_authenticated_user)])

    @router.get("/admin")
    async def admin_endpoint(
        _current_user: UserAccount = Depends(admin_auth.require_admin_user),
    ) -> dict[str, bool]:
        return {"allowed": True}

    @router.get("/non-auditor")
    async def non_auditor_endpoint(
        _current_user: UserAccount = Depends(admin_auth.require_non_auditor_user),
    ) -> dict[str, bool]:
        return {"allowed": True}

    app.include_router(router)

    async def override_get_db() -> None:
        return None

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "role", "expected_status", "expected_message"),
    [
        ("/admin", UserRole.ADMIN, status.HTTP_200_OK, None),
        (
            "/admin",
            UserRole.ANALYST,
            status.HTTP_403_FORBIDDEN,
            "Admin role required for this operation",
        ),
        ("/non-auditor", UserRole.ANALYST, status.HTTP_200_OK, None),
        (
            "/non-auditor",
            UserRole.AUDITOR,
            status.HTTP_403_FORBIDDEN,
            "Auditor accounts have read-only access",
        ),
    ],
)
async def test_router_and_role_dependency_authenticate_once(
    monkeypatch: pytest.MonkeyPatch,
    role_dependency_app: FastAPI,
    path: str,
    role: UserRole,
    expected_status: int,
    expected_message: str | None,
) -> None:
    authentication_calls = 0

    async def authenticate(_request: Request, _db: AsyncSession) -> UserAccount:
        nonlocal authentication_calls
        authentication_calls += 1
        return cast(
            UserAccount,
            SimpleNamespace(role=role, must_change_password=False),
        )

    monkeypatch.setattr(admin_auth, "_authenticate_from_request", authenticate)

    async with AsyncClient(
        transport=ASGITransport(app=role_dependency_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(path)

    assert response.status_code == expected_status
    assert authentication_calls == 1
    if expected_message is not None:
        assert response.json()["detail"]["message"] == expected_message


@pytest.mark.asyncio
async def test_router_and_role_dependency_preserve_unauthenticated_response(
    monkeypatch: pytest.MonkeyPatch,
    role_dependency_app: FastAPI,
) -> None:
    authentication_calls = 0
    authenticate_from_request = admin_auth._authenticate_from_request

    async def counting_authenticate(request: Request, db: AsyncSession) -> UserAccount:
        nonlocal authentication_calls
        authentication_calls += 1
        return await authenticate_from_request(request, db)

    monkeypatch.setattr(admin_auth, "_authenticate_from_request", counting_authenticate)

    async with AsyncClient(
        transport=ASGITransport(app=role_dependency_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/admin")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"]["message"] == "Authentication required"
    assert authentication_calls == 1


@pytest.mark.asyncio
async def test_under_scoped_api_key_never_falls_back_to_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/write",
            "headers": [
                (b"authorization", b"Bearer tmi_read_only"),
                (b"cookie", b"intercept_session=valid-session"),
            ],
            "query_string": b"",
        }
    )
    validate_api_key = AsyncMock(
        side_effect=ApiKeyScopeError({API_WRITE_SCOPE})
    )
    validate_session = AsyncMock()
    monkeypatch.setattr(
        admin_auth.api_key_service,
        "validate_api_key",
        validate_api_key,
    )
    monkeypatch.setattr(
        admin_auth.auth_service,
        "validate_session",
        validate_session,
    )

    with pytest.raises(HTTPException) as exc_info:
        await admin_auth._authenticate_from_request(
            request,
            cast(AsyncSession, object()),
        )

    assert exc_info.value.status_code == 403
    validate_session.assert_not_awaited()
