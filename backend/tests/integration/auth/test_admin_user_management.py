"""Integration tests for admin user management endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import UserRole, UserStatus
from app.models.models import AdminResetRequest, AuthSession, UserAccount
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_cookie(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200
    session_cookie = response.cookies.get("intercept_session")
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_admin_create_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin can successfully create a new analyst account with temporary credentials."""
    admin = admin_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
    
    # Login as admin to get session
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Create new user
    new_user_data = {
        "username": "new.analyst",
        "email": "new.analyst@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert "userId" in data
    assert "temporaryCredentialExpiresAt" in data
    assert data["deliveryChannel"] == "SECURE_EMAIL"
    
    # Verify user was created in database
    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.username == new_user_data["username"])
        )
        created_user = result.scalar_one_or_none()
        
        assert created_user is not None
        assert created_user.email == new_user_data["email"]
        assert created_user.role == UserRole.ANALYST
        assert created_user.status == UserStatus.ACTIVE
        assert created_user.must_change_password is True
        assert created_user.created_by_admin_id == admin.id
        assert created_user.password_hash  # Has a temporary password


@pytest.mark.asyncio
async def test_admin_create_user_requires_authentication(
    client: AsyncClient,
) -> None:
    """Creating a user without authentication returns 401."""
    new_user_data = {
        "username": "test.user",
        "email": "test@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_create_user_requires_admin_role(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Creating a user as non-admin returns 403."""
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(analyst)
        await session.commit()
    
    # Login as analyst
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to create user
    new_user_data = {
        "username": "test.user",
        "email": "test@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 403
    response_data = response.json()
    # HTTPException detail becomes the "detail" field in the response
    assert "detail" in response_data
    assert "admin" in response_data["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_create_user_rejects_duplicate_username(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Creating a user with duplicate username returns 400."""
    admin = admin_user_factory()
    existing_analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        session.add(existing_analyst)
        await session.commit()
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to create user with existing username
    new_user_data = {
        "username": existing_analyst.username,
        "email": "different@example.com",
        "role": "ANALYST",
    }
    
    response = await client.post(
        "/api/v1/admin/auth/users",
        json=new_user_data,
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    assert "username" in response_data["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_non_admin_can_get_users_summary(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    admin_user_factory,
) -> None:
    """Authenticated non-admin users can load active human users for assignee dropdowns."""
    analyst = analyst_user_factory(username="analyst.viewer")
    admin = admin_user_factory(username="admin.visible")
    disabled_user = analyst_user_factory(username="analyst.disabled")
    disabled_user.status = UserStatus.DISABLED

    async with session_maker() as session:
        session.add(analyst)
        session.add(admin)
        session.add(disabled_user)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, analyst.username)

    response = await client.get(
        "/api/v1/admin/auth/users/summary",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    usernames = [item["username"] for item in payload]

    assert analyst.username in usernames
    assert admin.username in usernames
    assert disabled_user.username not in usernames
    assert all(item["accountType"] == "HUMAN" for item in payload)


@pytest.mark.asyncio
async def test_users_summary_requires_authentication(
    client: AsyncClient,
) -> None:
    """Listing lightweight users still requires authentication."""
    response = await client.get("/api/v1/admin/auth/users/summary")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_list_full_users(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """The router split must not widen access to admin-only user management endpoints."""
    analyst = analyst_user_factory(username="analyst.noadmin")

    async with session_maker() as session:
        session.add(analyst)
        await session.commit()

    session_cookie = await _login_and_get_cookie(client, analyst.username)

    response = await client.get(
        "/api/v1/admin/auth/users",
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403
    response_data = response.json()
    assert "detail" in response_data
    assert "admin" in response_data["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_admin_disable_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Admin can successfully disable an active user account."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Disable the analyst
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 204
    
    # Verify user is disabled
    async with session_maker() as session:
        result = await session.get(UserAccount, analyst_id)
        assert result is not None
        assert result.status == UserStatus.DISABLED


@pytest.mark.asyncio
async def test_admin_disable_user_revokes_sessions(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Disabling a user revokes all their active sessions."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id
    
    # Login as analyst to create a session
    analyst_login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert analyst_login.status_code == 200
    
    # Login as admin
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_session_cookie = admin_login.cookies.get("intercept_session")
    assert admin_session_cookie is not None
    
    # Verify analyst has active session
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == analyst_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        active_sessions = result.scalars().all()
        assert len(active_sessions) == 1
    
    # Disable the analyst
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": admin_session_cookie},
    )
    assert response.status_code == 204
    
    # Verify all sessions are revoked
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == analyst_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        active_sessions = result.scalars().all()
        assert len(active_sessions) == 0


@pytest.mark.asyncio
async def test_admin_enable_user_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Admin can re-enable a disabled user account."""
    admin = admin_user_factory()
    analyst = analyst_user_factory()
    analyst.status = UserStatus.DISABLED
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        analyst_id = analyst.id
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Re-enable the analyst
    response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst_id}/status",
        json={"status": "ACTIVE"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 204
    
    # Verify user is active
    async with session_maker() as session:
        result = await session.get(UserAccount, analyst_id)
        assert result is not None
        assert result.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_admin_update_status_requires_authentication(
    client: AsyncClient,
) -> None:
    """Updating user status without authentication returns 401."""
    user_id = uuid4()
    
    response = await client.patch(
        f"/api/v1/admin/auth/users/{user_id}/status",
        json={"status": "DISABLED"},
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_update_status_requires_admin_role(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Updating user status as non-admin returns 403."""
    analyst = analyst_user_factory()
    target_user = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(analyst)
        session.add(target_user)
        await session.commit()
        target_id = target_user.id
    
    # Login as analyst
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to disable user
    response = await client.patch(
        f"/api/v1/admin/auth/users/{target_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_status_nonexistent_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Updating status of non-existent user returns 404."""
    admin = admin_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Try to disable non-existent user
    fake_id = uuid4()
    response = await client.patch(
        f"/api/v1/admin/auth/users/{fake_id}/status",
        json={"status": "DISABLED"},
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 404
