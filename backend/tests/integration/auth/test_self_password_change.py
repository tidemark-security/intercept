"""
Integration tests for voluntary (self-service) password change flow.

Tests cover User Story 4: Analyst proactively changes own password.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import SessionRevokedReason
from app.models.models import AuthSession, UserAccount
from app.services.security.password_hasher import PasswordHasher
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_voluntary_password_change_success(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    password_hasher: PasswordHasher,
) -> None:
    """Test that an authenticated analyst can successfully change their password."""
    user = analyst_user_factory()
    new_password = "NewSecure!Pass123"

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    # Login to get session cookie
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    # Extract session cookie
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None

    # Change password
    change_response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": new_password,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert change_response.status_code == 204

    # Verify password was updated in database
    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert password_hasher.verify(refreshed.password_hash, new_password)
        assert refreshed.must_change_password is False
        assert refreshed.password_updated_at is not None

    # Verify can login with new password
    new_login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": new_password},
    )
    assert new_login_response.status_code == 200


@pytest.mark.asyncio
async def test_password_change_rejects_incorrect_current_password(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Test that password change fails if current password is incorrect."""
    user = analyst_user_factory()
    new_password = "NewSecure!Pass123"

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    # Login to get session cookie
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")

    # Attempt to change password with wrong current password
    change_response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": "WrongPassword123!",
            "newPassword": new_password,
        },
        cookies={"intercept_session": session_cookie},
    )

    assert change_response.status_code == 401
    data = change_response.json()
    assert "Invalid current password" in data["message"]

    # Verify password was NOT changed in database
    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        # Should still have original password
        from app.core.settings_registry import get_local
        from app.services.security.password_hasher import Argon2Parameters, PasswordHasher
        hasher = PasswordHasher(
            Argon2Parameters(
                time_cost=get_local("auth.argon2.time_cost"),
                memory_cost=get_local("auth.argon2.memory_cost_kib"),
                parallelism=get_local("auth.argon2.parallelism"),
                hash_len=get_local("auth.argon2.hash_len"),
                salt_len=get_local("auth.argon2.salt_len"),
                encoding=get_local("auth.argon2.encoding"),
            )
        )
        assert hasher.verify(refreshed.password_hash, DEFAULT_TEST_PASSWORD)


@pytest.mark.asyncio
async def test_password_change_enforces_password_policy(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Test that password change enforces password policy requirements."""
    user = analyst_user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    # Login to get session cookie
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")

    # Test: password too short
    response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": "Short1!",
        },
        cookies={"intercept_session": session_cookie},
    )
    # Pydantic validation returns 422 (Unprocessable Entity)
    assert response.status_code == 422
    response_data = response.json()
    assert "detail" in response_data

    # Test: password missing uppercase (validated in service layer, returns 400)
    response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": "nouppercase123!",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 400

    # Test: password missing special character (validated in service layer, returns 400)
    response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": "NoSpecialChar123",
        },
        cookies={"intercept_session": session_cookie},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_password_change_requires_authentication(
    client: AsyncClient,
) -> None:
    """Test that password change endpoint requires an active session."""
    response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": "SomePassword123!",
            "newPassword": "NewPassword123!",
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert "No active session" in data["message"]


@pytest.mark.asyncio
async def test_password_change_preserves_current_session(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Test that password change keeps the current session active."""
    user = analyst_user_factory()
    new_password = "NewSecure!Pass123"

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    # Login to get session cookie
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    session_data = login_response.json()
    current_session_id = session_data["session"]["sessionId"]

    # Change password
    change_response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": new_password,
        },
        cookies={"intercept_session": session_cookie},
    )
    assert change_response.status_code == 204

    # Verify current session is still active by calling session endpoint
    session_check_response = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session_cookie},
    )
    assert session_check_response.status_code == 200
    check_data = session_check_response.json()
    assert check_data["session"]["sessionId"] == current_session_id


@pytest.mark.asyncio
async def test_password_change_revokes_other_sessions(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Test that password change revokes all other active sessions."""
    user = analyst_user_factory()
    new_password = "NewSecure!Pass123"

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    # Create first session
    login1_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login1_response.status_code == 200
    session1_cookie = login1_response.cookies.get("intercept_session")
    session1_id = login1_response.json()["session"]["sessionId"]

    # Create second session (simulating login from another device)
    login2_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login2_response.status_code == 200
    session2_cookie = login2_response.cookies.get("intercept_session")
    session2_id = login2_response.json()["session"]["sessionId"]

    # Verify both sessions are initially active
    check1 = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session1_cookie},
    )
    assert check1.status_code == 200

    check2 = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session2_cookie},
    )
    assert check2.status_code == 200

    # Change password using first session
    change_response = await client.post(
        "/api/v1/auth/password/change",
        json={
            "currentPassword": DEFAULT_TEST_PASSWORD,
            "newPassword": new_password,
        },
        cookies={"intercept_session": session1_cookie},
    )
    assert change_response.status_code == 204

    # Verify first session is still active
    check1_after = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session1_cookie},
    )
    assert check1_after.status_code == 200

    # Verify second session was revoked
    check2_after = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session2_cookie},
    )
    assert check2_after.status_code == 401

    # Verify in database that session 2 was revoked with correct reason
    async with session_maker() as session:
        result = await session.execute(
            select(AuthSession).where(AuthSession.id == session2_id)
        )
        revoked_session = result.scalar_one_or_none()
        assert revoked_session is not None
        assert revoked_session.revoked_at is not None
        assert revoked_session.revoked_reason == SessionRevokedReason.RESET_REQUIRED


@pytest.mark.asyncio
async def test_password_change_audit_logging(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    caplog,
) -> None:
    """Test that password change events are properly audit logged."""
    import logging
    
    user = analyst_user_factory()
    new_password = "NewSecure!Pass123"

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    # Login to get session cookie
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")

    # Change password with audit logging enabled
    with caplog.at_level(logging.INFO, logger="app.audit.auth"):
        change_response = await client.post(
            "/api/v1/auth/password/change",
            json={
                "currentPassword": DEFAULT_TEST_PASSWORD,
                "newPassword": new_password,
            },
            cookies={"intercept_session": session_cookie},
        )
        assert change_response.status_code == 204

    # Verify audit log contains password change event
    audit_records = [r for r in caplog.records if r.name == "app.audit.auth"]
    assert len(audit_records) > 0
    
    password_change_logs = [
        r for r in audit_records 
        if hasattr(r, "auth") and r.auth.get("event") == "auth.password_changed"
    ]
    assert len(password_change_logs) > 0
    
    log_entry = password_change_logs[0].auth
    assert log_entry["user_id"] == str(user.id)
    assert log_entry["username"] == user.username
    assert log_entry["was_forced"] is False  # Voluntary change
    # correlation_id is optional, may be None in test environment
    assert "ip_address" in log_entry
