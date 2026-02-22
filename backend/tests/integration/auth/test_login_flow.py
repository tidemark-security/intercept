from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import UserStatus
from app.models.models import UserAccount
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_login_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user"]["id"] == str(user.id)
    assert data["user"]["username"] == user.username
    assert data["session"]["sessionId"]
    assert "expiresAt" in data["session"]

    set_cookie = response.headers.get("set-cookie")
    assert set_cookie is not None and set_cookie.startswith("intercept_session=")

    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert refreshed.failed_login_attempts == 0
        assert refreshed.status == UserStatus.ACTIVE
        assert refreshed.last_login_at is not None
        assert refreshed.lockout_expires_at is None


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "totally-wrong"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["message"] == "Unable to sign in with the provided credentials."
    assert data["fields"] == []

    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert refreshed.failed_login_attempts == 1
        assert refreshed.status == UserStatus.ACTIVE
        assert refreshed.lockout_expires_at is None


@pytest.mark.asyncio
async def test_login_lockout_after_repeated_failures(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    for attempt in range(5):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": "wrong-password"},
        )

        if attempt < 4:
            assert response.status_code == 401
        else:
            assert response.status_code == 401
            data = response.json()
            assert data["message"] == "Unable to sign in with the provided credentials."

    async with session_maker() as session:
        refreshed = await session.execute(
            select(UserAccount).where(UserAccount.id == user.id)
        )
        refreshed_user = refreshed.scalar_one()
        assert refreshed_user.status == UserStatus.LOCKED
        assert refreshed_user.lockout_expires_at is not None
        assert refreshed_user.lockout_expires_at > datetime.now(timezone.utc)
        assert refreshed_user.failed_login_attempts >= 5

    # Even with correct password, account remains locked until expiry
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 401

    data = response.json()
    assert data["message"] == "Unable to sign in with the provided credentials."
