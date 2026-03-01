"""Integration tests for MCP authentication on current transport endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import UserAccount
from app.services.api_key_service import api_key_service


async def _create_api_key(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    username: str,
    email: str,
    role: UserRole = UserRole.ANALYST,
    status: UserStatus = UserStatus.ACTIVE,
    expires_at: datetime | None = None,
) -> tuple[int, int, str]:
    async with session_maker() as session:
        user = UserAccount(
            username=username,
            email=email,
            role=role,
            status=status,
            account_type=AccountType.NHI,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_key_result = await api_key_service.create_api_key(
            session,
            user_id=user.id,
            name=f"{username} key",
            expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=30)),
        )
        api_key, raw_key = api_key_result
        await session.commit()
        return user.id, api_key.id, raw_key


async def _get_mcp_missing_route_status(client: AsyncClient, headers: dict[str, str] | None = None) -> int:
    response = await client.get("/mcp/does-not-exist", headers=headers)
    return response.status_code


@pytest.mark.asyncio
async def test_mcp_namespace_requires_authentication(client: AsyncClient) -> None:
    status_code = await _get_mcp_missing_route_status(client)
    assert status_code == 401


@pytest.mark.asyncio
async def test_mcp_accepts_valid_bearer_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_key = await _create_api_key(
        session_maker,
        username="mcp_auth_user",
        email="mcp_auth@test.com",
    )

    status_code = await _get_mcp_missing_route_status(client, headers={"Authorization": f"Bearer {raw_key}"})
    assert status_code == 404


@pytest.mark.asyncio
async def test_mcp_accepts_x_api_key_header(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_key = await _create_api_key(
        session_maker,
        username="mcp_auth_user_header",
        email="mcp_auth_header@test.com",
    )

    status_code = await _get_mcp_missing_route_status(client, headers={"X-API-Key": raw_key})
    assert status_code == 404


@pytest.mark.asyncio
async def test_mcp_rejects_expired_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_key = await _create_api_key(
        session_maker,
        username="mcp_expired_user",
        email="mcp_expired@test.com",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    status_code = await _get_mcp_missing_route_status(client, headers={"Authorization": f"Bearer {raw_key}"})
    assert status_code == 401


@pytest.mark.asyncio
async def test_mcp_rejects_revoked_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, api_key_id, raw_key = await _create_api_key(
        session_maker,
        username="mcp_revoked_user",
        email="mcp_revoked@test.com",
    )

    async with session_maker() as session:
        await api_key_service.revoke_api_key(session, api_key_id=api_key_id)
        await session.commit()

    status_code = await _get_mcp_missing_route_status(client, headers={"Authorization": f"Bearer {raw_key}"})
    assert status_code == 401


@pytest.mark.asyncio
async def test_mcp_rejects_disabled_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id, _, raw_key = await _create_api_key(
        session_maker,
        username="mcp_disabled_user",
        email="mcp_disabled@test.com",
    )

    async with session_maker() as session:
        user = await session.get(UserAccount, user_id)
        assert user is not None
        user.status = UserStatus.DISABLED
        session.add(user)
        await session.commit()

    status_code = await _get_mcp_missing_route_status(client, headers={"Authorization": f"Bearer {raw_key}"})
    assert status_code == 403


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_key(client: AsyncClient) -> None:
    status_code = await _get_mcp_missing_route_status(
        client,
        headers={"Authorization": "Bearer int_invalid_key_12345"},
    )
    assert status_code == 401
