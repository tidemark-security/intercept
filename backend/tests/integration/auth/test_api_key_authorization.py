"""Integration tests for API key authorization rules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.enums import AccountType
from app.models.models import ApiKey, UserAccount
from app.services.api_key_service import api_key_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_cookie(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_user_can_create_api_key_for_self(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=user.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "self-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(user.id)
    assert data["name"] == "self-key"
    assert data["key"]


@pytest.mark.asyncio
async def test_non_admin_cannot_create_api_key_for_other_user(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    acting_user = analyst_user_factory()
    target_user = analyst_user_factory()

    async with session_maker() as session:
        session.add(acting_user)
        session.add(target_user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=acting_user.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "forbidden-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_id": str(target_user.id),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    assert "admin" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_cannot_create_api_key_for_human_account(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    human_target = analyst_user_factory()

    async with session_maker() as session:
        session.add(admin)
        session.add(human_target)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "human-target-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_id": str(human_target.id),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    assert "nhi" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_can_create_api_key_for_nhi_account(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
) -> None:
    admin = admin_user_factory()
    nhi_user = UserAccount(
        username="svc.integration",
        role=admin.role,
        status=admin.status,
        account_type=AccountType.NHI,
        description="Integration account",
    )

    async with session_maker() as session:
        session.add(admin)
        session.add(nhi_user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "nhi-key",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "user_id": str(nhi_user.id),
        },
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(nhi_user.id)
    assert data["name"] == "nhi-key"


@pytest.mark.asyncio
async def test_admin_can_revoke_any_user_api_key(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    target_user = analyst_user_factory()

    async with session_maker() as session:
        session.add(admin)
        session.add(target_user)
        await session.commit()

        api_key, _ = await api_key_service.create_api_key(
            session,
            user_id=target_user.id,
            name="target-user-key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        await session.commit()
        key_id = api_key.id

    session_cookie = await _login_and_get_cookie(
        client,
        username=admin.username,
        password=DEFAULT_TEST_PASSWORD,
    )

    response = await client.delete(
        f"/api/v1/api-keys/{key_id}",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 204

    async with session_maker() as session:
        revoked_key = await session.get(ApiKey, key_id)
        assert revoked_key is not None
        assert revoked_key.revoked_at is not None
