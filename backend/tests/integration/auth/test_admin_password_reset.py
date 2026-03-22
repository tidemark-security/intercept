"""Integration tests for admin-issued password reset endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import SessionRevokedReason
from app.models.models import AdminResetRequest, AuthSession, UserAccount
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_admin_issue_password_reset_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        analyst_id = analyst.id

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login_response.cookies.get("intercept_session")

    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst_id)},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["resetToken"]
    assert "expiresAt" in data

    async with session_maker() as session:
        reset_result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.target_user_id == analyst_id)
        )
        reset_request = reset_result.scalar_one()
        user_result = await session.execute(select(UserAccount).where(UserAccount.id == analyst_id))
        updated_analyst = user_result.scalar_one()

        assert reset_request.token_hash
        assert reset_request.consumed_at is None
        assert updated_analyst.password_hash is None
        assert updated_analyst.must_change_password is False


@pytest.mark.asyncio
async def test_admin_reset_revokes_active_sessions(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id

    analyst_login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert analyst_login.status_code == 200

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_session_cookie = admin_login.cookies.get("intercept_session")

    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst_id)},
        cookies={"intercept_session": admin_session_cookie},
    )
    assert response.status_code == 201

    async with session_maker() as session:
        result = await session.execute(select(AuthSession).where(AuthSession.user_id == analyst_id))
        all_sessions = result.scalars().all()
        assert all_sessions
        for session_record in all_sessions:
            assert session_record.revoked_at is not None
            assert session_record.revoked_reason == SessionRevokedReason.RESET_REQUIRED


@pytest.mark.asyncio
async def test_reset_token_can_be_consumed_and_new_password_can_login(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    new_password = "BrandNewPassword123!"

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_session_cookie = admin_login.cookies.get("intercept_session")

    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst_id)},
        cookies={"intercept_session": admin_session_cookie},
    )
    reset_token = reset_response.json()["resetToken"]

    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "newPassword": new_password},
    )
    assert consume_response.status_code == 204

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": new_password},
    )
    assert login_response.status_code == 200

    async with session_maker() as session:
        result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.target_user_id == analyst_id)
        )
        reset_request = result.scalar_one()
        assert reset_request.consumed_at is not None


@pytest.mark.asyncio
async def test_expired_reset_token_is_rejected(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_session_cookie = admin_login.cookies.get("intercept_session")

    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst_id)},
        cookies={"intercept_session": admin_session_cookie},
    )
    reset_token = reset_response.json()["resetToken"]

    async with session_maker() as session:
        result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.target_user_id == analyst_id)
        )
        reset_request = result.scalar_one()
        reset_request.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "newPassword": "BrandNewPassword123!"},
    )
    assert consume_response.status_code == 400


@pytest.mark.asyncio
async def test_admin_reset_authorization_and_not_found(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    viewer = analyst_user_factory(username="viewer.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        session.add(viewer)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        admin_id = admin.id
        analyst_id = analyst.id

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_cookie = admin_login.cookies.get("intercept_session")

    own_reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(admin_id)},
        cookies={"intercept_session": admin_cookie},
    )
    assert own_reset_response.status_code == 400

    analyst_login = await client.post(
        "/api/v1/auth/login",
        json={"username": viewer.username, "password": DEFAULT_TEST_PASSWORD},
    )
    analyst_cookie = analyst_login.cookies.get("intercept_session")

    forbidden_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst_id)},
        cookies={"intercept_session": analyst_cookie},
    )
    assert forbidden_response.status_code == 403

    not_found_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": "00000000-0000-0000-0000-000000000000"},
        cookies={"intercept_session": admin_cookie},
    )
    assert not_found_response.status_code == 404
