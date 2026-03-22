"""Integration tests for MCP transport endpoint behavior."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import UserAccount
from app.services.api_key_service import api_key_service


@pytest.fixture
async def mcp_api_key(session_maker: async_sessionmaker[AsyncSession]) -> str:
    async with session_maker() as session:
        user = UserAccount(
            username="mcp_tool_user",
            email="mcp_tool@test.com",
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
            name="MCP tool transport key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        _, raw_key = api_key_result
        await session.commit()
        return raw_key


@pytest.mark.asyncio
async def test_mcp_namespace_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/mcp/does-not-exist")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_mcp_request_passes_auth_middleware(
    client: AsyncClient,
    mcp_api_key: str,
) -> None:
    response = await client.get(
        "/mcp/does-not-exist",
        headers={"Authorization": f"Bearer {mcp_api_key}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_tool_call_endpoint_removed(
    client: AsyncClient,
    mcp_api_key: str,
) -> None:
    response = await client.post(
        "/mcp/v1/tools/call",
        headers={"Authorization": f"Bearer {mcp_api_key}"},
        json={"name": "get_cases_api_v1_cases_get", "arguments": {"limit": 10}},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_tool_list_endpoint_removed(
    client: AsyncClient,
    mcp_api_key: str,
) -> None:
    response = await client.post(
        "/mcp/v1/tools/list",
        headers={"Authorization": f"Bearer {mcp_api_key}"},
    )
    assert response.status_code == 404
