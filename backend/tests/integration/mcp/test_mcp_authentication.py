"""Integration tests for MCP authentication on current transport endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app as intercept_app
from app.models.enums import AccountType, UserRole, UserStatus
from app.models.models import ApiKey, UserAccount
from app.services.api_key_service import api_key_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


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


async def _initialize_mcp(
    client: AsyncClient,
    headers: dict[str, str] | None = None,
    *,
    enter_lifespan: bool = False,
) -> int:
    request_headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "auth-test", "version": "1"},
        },
    }

    if enter_lifespan:
        runtime = intercept_app.runtime
        assert runtime is not None
        async with runtime.http_app.lifespan(runtime.http_app):
            response = await client.post(
                "/mcp/streamable/",
                headers=request_headers,
                json=request,
            )
    else:
        response = await client.post(
            "/mcp/streamable/",
            headers=request_headers,
            json=request,
        )
    return response.status_code


async def _assert_auth_failure_is_audited(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Callable[..., UserAccount],
    *,
    reason: str,
) -> None:
    admin = admin_user_factory(username=f"audit_{reason}")
    async with session_maker() as session:
        session.add(admin)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None

    audit_response = await client.get(
        "/api/v1/admin/audit",
        params={"event_type": "auth.api_key.auth_failure", "size": 10},
        cookies={"intercept_session": session_cookie},
    )
    assert audit_response.status_code == 200
    failure_payloads: list[dict[str, Any]] = [
        json.loads(item["new_value"])
        for item in audit_response.json()["items"]
    ]
    assert {payload["reason"] for payload in failure_payloads} == {reason}


@pytest.mark.asyncio
async def test_mcp_namespace_requires_authentication(client: AsyncClient) -> None:
    status_code = await _initialize_mcp(client)
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

    status_code = await _initialize_mcp(
        client,
        headers={"Authorization": f"Bearer {raw_key}"},
        enter_lifespan=True,
    )
    assert status_code == 200


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

    status_code = await _initialize_mcp(
        client,
        headers={"X-API-Key": raw_key},
        enter_lifespan=True,
    )
    assert status_code == 200


@pytest.mark.asyncio
async def test_mcp_rejects_expired_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Callable[..., UserAccount],
) -> None:
    _, api_key_id, raw_key = await _create_api_key(
        session_maker,
        username="mcp_expired_user",
        email="mcp_expired@test.com",
    )

    async with session_maker() as session:
        api_key = await session.get(ApiKey, api_key_id)
        assert api_key is not None
        api_key.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()

    status_code = await _initialize_mcp(
        client,
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert status_code == 401
    await _assert_auth_failure_is_audited(
        client,
        session_maker,
        admin_user_factory,
        reason="key_expired",
    )


@pytest.mark.asyncio
async def test_mcp_rejects_revoked_key(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Callable[..., UserAccount],
) -> None:
    _, api_key_id, raw_key = await _create_api_key(
        session_maker,
        username="mcp_revoked_user",
        email="mcp_revoked@test.com",
    )

    async with session_maker() as session:
        await api_key_service.revoke_api_key(session, api_key_id=api_key_id)
        await session.commit()

    status_code = await _initialize_mcp(
        client,
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert status_code == 401
    await _assert_auth_failure_is_audited(
        client,
        session_maker,
        admin_user_factory,
        reason="key_revoked",
    )


@pytest.mark.asyncio
async def test_mcp_rejects_disabled_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Callable[..., UserAccount],
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

    status_code = await _initialize_mcp(
        client,
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert status_code == 401
    await _assert_auth_failure_is_audited(
        client,
        session_maker,
        admin_user_factory,
        reason="user_inactive",
    )


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_key_and_persists_audit(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory: Callable[..., UserAccount],
) -> None:
    status_code = await _initialize_mcp(
        client,
        headers={"Authorization": "Bearer int_invalid_key_12345"},
    )
    assert status_code == 401
    await _assert_auth_failure_is_audited(
        client,
        session_maker,
        admin_user_factory,
        reason="key_not_found",
    )
