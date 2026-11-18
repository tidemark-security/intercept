from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import cases
from app.api.routes.admin_auth import (
    require_authenticated_user,
    require_non_auditor_user,
)
from app.core.database import get_db
from app.models.models import UserAccount


@pytest.fixture
def bulk_case_app() -> FastAPI:
    app = FastAPI()
    app.include_router(cases.router, prefix="/api/v1")

    async def override_get_db() -> AsyncSession:
        return cast(AsyncSession, None)

    async def override_current_user() -> UserAccount:
        return cast(UserAccount, SimpleNamespace(username="bulk-case-user"))

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = override_current_user
    app.dependency_overrides[require_non_auditor_user] = override_current_user
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", ["42", "CAS-0000042"])
async def test_bulk_update_accepts_numeric_and_canonical_case_ids(
    bulk_case_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
) -> None:
    update_case = AsyncMock(return_value=None)
    monkeypatch.setattr(cases.case_service, "update_case", update_case)

    async with AsyncClient(
        transport=ASGITransport(app=bulk_case_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/cases/bulk-update",
            json={"case_ids": [case_id], "case_update": {"title": "Updated"}},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []
    update_case.assert_awaited_once()
    assert update_case.await_args.args[1] == 42


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "expected_message"),
    [
        ("not-an-id", "Invalid ID format"),
        ("ALT-0000042", "has alert prefix but expected 'case'"),
    ],
)
async def test_bulk_update_rejects_malformed_or_wrong_prefix_ids(
    bulk_case_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    expected_message: str,
) -> None:
    update_case = AsyncMock(return_value=None)
    monkeypatch.setattr(cases.case_service, "update_case", update_case)

    async with AsyncClient(
        transport=ASGITransport(app=bulk_case_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/cases/bulk-update",
            json={"case_ids": [case_id], "case_update": {"title": "Updated"}},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert expected_message in response.json()["detail"]
    update_case.assert_not_awaited()
