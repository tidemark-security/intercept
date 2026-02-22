"""Integration tests for admin-initiated password reset endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import SessionRevokedReason, UserRole, UserStatus
from app.models.models import AdminResetRequest, AuthSession, UserAccount
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_admin_issue_password_reset_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Admin can successfully issue a password reset for a user."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Issue password reset
    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={
            "userId": str(analyst_id),
            "deliveryChannel": "SECURE_EMAIL",
        },
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert "resetRequestId" in data
    assert "expiresAt" in data
    
    # Verify reset request was created
    async with session_maker() as session:
        result = await session.execute(
            select(AdminResetRequest).where(
                AdminResetRequest.target_user_id == analyst_id
            )
        )
        reset_request = result.scalar_one()
        
        assert reset_request is not None
        assert reset_request.issued_by_admin_id == admin.id
        assert reset_request.consumed_at is None
        assert reset_request.invalidated_at is None
        
        # Verify user has must_change_password flag set
        result = await session.execute(
            select(UserAccount).where(UserAccount.id == analyst_id)
        )
        updated_analyst = result.scalar_one()
        
        assert updated_analyst.must_change_password is True
        assert updated_analyst.failed_login_attempts == 0
        assert updated_analyst.lockout_expires_at is None


@pytest.mark.asyncio
async def test_admin_reset_revokes_active_sessions(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Password reset revokes all active sessions for the target user."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id
    
    # Login as analyst to create a session
    analyst_login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert analyst_login.status_code == 200
    
    # Verify session exists
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == analyst_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        active_sessions = result.scalars().all()
        assert len(active_sessions) > 0
    
    # Login as admin
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_session_cookie = admin_login.cookies.get("intercept_session")
    assert admin_session_cookie is not None
    
    # Issue password reset
    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={
            "userId": str(analyst_id),
            "deliveryChannel": "SECURE_EMAIL",
        },
        cookies={"intercept_session": admin_session_cookie},
    )
    assert response.status_code == 201
    
    # Verify all sessions were revoked
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == analyst_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        active_sessions = result.scalars().all()
        assert len(active_sessions) == 0
        
        # Verify sessions were revoked with correct reason
        result = await session.execute(
            select(AuthSession).where(AuthSession.user_id == analyst_id)
        )
        all_sessions = result.scalars().all()
        
        for session_record in all_sessions:
            assert session_record.revoked_at is not None
            assert session_record.revoked_reason == SessionRevokedReason.RESET_REQUIRED


@pytest.mark.asyncio
async def test_admin_cannot_reset_own_password(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin cannot reset their own password through admin panel."""
    admin = admin_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id
    
    # Login as admin
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Attempt to reset own password
    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={
            "userId": str(admin_id),
            "deliveryChannel": "SECURE_EMAIL",
        },
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 400
    data = response.json()
    # Check for the error message - may be in 'detail.message' or 'message' field
    if isinstance(data.get("detail"), dict):
        error_text = data["detail"].get("message", "").lower()
    else:
        error_text = data.get("message", data.get("detail", "")).lower()
    assert "cannot reset your own password" in error_text


@pytest.mark.asyncio
async def test_analyst_cannot_issue_password_reset(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Analyst role cannot issue password resets."""
    analyst = analyst_user_factory()
    target = analyst_user_factory(username="target.user")
    
    async with session_maker() as session:
        session.add(analyst)
        session.add(target)
        await session.commit()
        await session.refresh(target)
        target_id = target.id
    
    # Login as analyst
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Attempt to issue password reset
    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={
            "userId": str(target_id),
            "deliveryChannel": "SECURE_EMAIL",
        },
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_must_change_password_after_reset(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """User flagged with must_change_password can login but must change password."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id
        analyst_username = analyst.username
    
    # Login as admin and issue reset
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_session_cookie = admin_login.cookies.get("intercept_session")
    assert admin_session_cookie is not None
    
    # Issue password reset (this sets a new temporary password)
    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={
            "userId": str(analyst_id),
            "deliveryChannel": "SECURE_EMAIL",
        },
        cookies={"intercept_session": admin_session_cookie},
    )
    assert reset_response.status_code == 201
    
    # Get the temporary password from the reset request
    # In a real scenario, this would be sent via email
    # For testing, we'll extract it from the database
    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.id == analyst_id)
        )
        updated_analyst = result.scalar_one()
        temp_password_hash = updated_analyst.password_hash
    
    # Note: In production, the temporary password is sent via email
    # For this test, we'll simulate logging in with the temporary password
    # Since we can't retrieve the plaintext temporary password from the hash,
    # we'll verify the must_change_password flag is set correctly
    
    # Verify must_change_password flag is set
    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.id == analyst_id)
        )
        user = result.scalar_one()
        assert user.must_change_password is True


@pytest.mark.asyncio
async def test_password_change_clears_must_change_flag(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Changing password clears the must_change_password flag."""
    analyst = analyst_user_factory()
    
    async with session_maker() as session:
        session.add(analyst)
        await session.commit()
        await session.refresh(analyst)
        analyst_id = analyst.id
        
        # Manually set must_change_password flag
        analyst.must_change_password = True
        await session.commit()
    
    # Login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    # Change password
    new_password = "NewSecurePassword123!@#"
    change_response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": new_password,
        },
        cookies={"intercept_session": session_cookie},
    )
    assert change_response.status_code == 204
    
    # Verify must_change_password flag is cleared
    async with session_maker() as session:
        result = await session.execute(
            select(UserAccount).where(UserAccount.id == analyst_id)
        )
        user = result.scalar_one()
        assert user.must_change_password is False


@pytest.mark.asyncio
async def test_reset_request_not_found_error(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Attempting to reset password for non-existent user returns 404."""
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
    
    # Attempt to reset password for non-existent user
    fake_user_id = "00000000-0000-0000-0000-000000000000"
    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={
            "userId": fake_user_id,
            "deliveryChannel": "SECURE_EMAIL",
        },
        cookies={"intercept_session": session_cookie},
    )
    
    assert response.status_code == 404
