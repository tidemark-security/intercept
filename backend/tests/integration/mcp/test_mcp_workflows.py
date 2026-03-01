"""Workflow-level MCP tests for current transport contract."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import UserAccount
from app.services.api_key_service import api_key_service


@pytest.fixture
async def workflow_api_key(session_maker: async_sessionmaker[AsyncSession]) -> str:
    async with session_maker() as session:
        user = UserAccount(
            username="workflow_user",
            email="workflow@test.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name="Workflow Test Key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        _, raw_key = api_key_result
        await session.commit()
        return raw_key


@pytest.mark.asyncio
async def test_authenticated_mcp_namespace_request(
    client: AsyncClient,
    workflow_api_key: str,
) -> None:
    response = await client.get(
        "/mcp/does-not-exist",
        headers={"Authorization": f"Bearer {workflow_api_key}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_removed_legacy_routes_stay_removed(
    client: AsyncClient,
    workflow_api_key: str,
) -> None:
    headers = {"Authorization": f"Bearer {workflow_api_key}"}

    list_response = await client.post("/mcp/v1/tools/list", headers=headers)
    call_response = await client.post(
        "/mcp/v1/tools/call",
        headers=headers,
        json={"name": "create_case_api_v1_cases_post", "arguments": {"title": "x"}},
    )

    assert list_response.status_code == 404
    assert call_response.status_code == 404
