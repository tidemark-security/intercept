from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import select

from app.core.security import hash_opaque_token
from app.models.enums import SessionRevokedReason, SettingType, UserRole, UserStatus
from app.models.models import AppSetting, AuthSession, PasskeyCredential, UserAccount
from app.services.auth_service import (
    AuthenticationConcurrencyError,
    SessionNotFoundError,
    auth_service,
)
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
async def test_parallel_shared_session_validation_is_read_only_and_deadlock_free(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    """Concurrent read requests must not upgrade shared credential locks."""
    user = analyst_user_factory(username="parallel-shared-session-user")
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_token = login_response.cookies.get("intercept_session")
    assert session_token is not None

    session_id = UUID(login_response.json()["session"]["sessionId"])
    async with session_maker() as read_db:
        stored_session = await read_db.get(AuthSession, session_id)
        assert stored_session is not None
        original_last_seen_at = stored_session.last_seen_at

    validation_barrier = asyncio.Barrier(2)

    async def validate_and_commit() -> None:
        async with session_maker() as validation_db:
            result = await auth_service.validate_session(
                validation_db,
                session_token=session_token,
                shared_lock=True,
            )
            assert result.user.id == user.id
            await validation_barrier.wait()
            await validation_db.commit()

    await asyncio.wait_for(
        asyncio.gather(validate_and_commit(), validate_and_commit()),
        timeout=3,
    )

    async with session_maker() as read_db:
        stored_session = await read_db.get(AuthSession, session_id)
        assert stored_session is not None
        assert stored_session.last_seen_at == original_last_seen_at

    # The HTTP dependency applies the queued activity touch only after the
    # protected shared-lock transaction has committed.
    response = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session_token},
    )
    assert response.status_code == 200
    async with session_maker() as read_db:
        stored_session = await read_db.get(AuthSession, session_id)
        assert stored_session is not None
        assert stored_session.last_seen_at > original_last_seen_at


@pytest.mark.asyncio
async def test_oidc_linked_non_bypass_password_login_is_denied_when_oidc_is_disabled(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(username="linked-local-login-user")
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "linked-local-login-subject"

    async with session_maker() as session:
        session.add_all(
            [
                user,
                AppSetting(
                    key="oidc.enabled",
                    value="false",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oidc_break_glass_users_can_password_login_when_oidc_is_disabled(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="linked-break-glass-admin")
    admin.oidc_issuer = "https://issuer.example"
    admin.oidc_subject = "linked-break-glass-admin-subject"
    bypass_user = analyst_user_factory(username="linked-break-glass-analyst")
    bypass_user.oidc_issuer = "https://issuer.example"
    bypass_user.oidc_subject = "linked-break-glass-analyst-subject"

    async with session_maker() as session:
        session.add_all(
            [
                admin,
                bypass_user,
                PasskeyCredential(
                    user_id=admin.id,
                    name="Break-glass administrator passkey",
                    credential_id="linked-break-glass-admin-credential",
                    credential_public_key="linked-break-glass-admin-public-key",
                ),
                AppSetting(
                    key="oidc.enabled",
                    value="false",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                ),
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value='["linked-break-glass-analyst"]',
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await session.commit()

    admin_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    bypass_response = await client.post(
        "/api/v1/auth/login",
        json={"username": bypass_user.username, "password": DEFAULT_TEST_PASSWORD},
    )

    assert admin_response.status_code == 200
    assert bypass_response.status_code == 200


@pytest.mark.asyncio
async def test_public_password_failures_cannot_lock_admin_break_glass(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory(username="non-lockable-break-glass-admin")
    admin.oidc_issuer = "https://issuer.example"
    admin.oidc_subject = "non-lockable-break-glass-admin-subject"
    async with session_maker() as session:
        session.add_all(
            [
                admin,
                AppSetting(
                    key="oidc.enabled",
                    value="true",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await session.commit()

    for _ in range(5):
        rejected = await client.post(
            "/api/v1/auth/login",
            json={"username": admin.username, "password": "IncorrectPassword123!"},
        )
        assert rejected.status_code == 401

    async with session_maker() as session:
        persisted = await session.get(UserAccount, admin.id)
        assert persisted is not None
        assert persisted.status == UserStatus.ACTIVE
        assert persisted.lockout_expires_at is None

    accepted = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_password_issued_before_disable_cannot_login_after_reenable(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    issuer = admin_user_factory(username="credential-cutoff-admin")
    target = admin_user_factory(username="credential-cutoff-target")
    target.oidc_issuer = "https://issuer.example"
    target.oidc_subject = "credential-cutoff-target-subject"
    replacement_password = "PostDisableBreakglassPassword123!"

    async with session_maker() as session:
        session.add_all([issuer, target])
        await session.commit()

    issuer_login = await client.post(
        "/api/v1/auth/login",
        json={"username": issuer.username, "password": DEFAULT_TEST_PASSWORD},
    )
    issuer_cookie = issuer_login.cookies.get("intercept_session")

    for status_value in ("DISABLED", "ACTIVE"):
        status_response = await client.patch(
            f"/api/v1/admin/auth/users/{target.id}/status",
            json={"status": status_value},
            cookies={"intercept_session": issuer_cookie},
        )
        assert status_response.status_code == 204, status_response.text

    stale_password_login = await client.post(
        "/api/v1/auth/login",
        json={"username": target.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert stale_password_login.status_code == 401
    assert stale_password_login.json()["message"] == (
        "Unable to sign in with the provided credentials."
    )

    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(target.id)},
        cookies={"intercept_session": issuer_cookie},
    )
    assert reset_response.status_code == 201
    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_response.json()["resetToken"],
            "newPassword": replacement_password,
        },
    )
    assert consume_response.status_code == 204

    fresh_password_login = await client.post(
        "/api/v1/auth/login",
        json={"username": target.username, "password": replacement_password},
    )
    assert fresh_password_login.status_code == 200


@pytest.mark.asyncio
async def test_pre_cutoff_session_cannot_resurrect_after_missed_row_revocation(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    cutoff = datetime.now(timezone.utc)
    raw_token = "pre-cutoff-session-token"
    user = analyst_user_factory(username="session-cutoff-target")
    user.credentials_invalidated_at = cutoff
    auth_session = AuthSession(
        session_token_hash=hash_opaque_token(raw_token),
        user_id=user.id,
        issued_at=cutoff - timedelta(seconds=1),
        last_seen_at=cutoff,
        expires_at=cutoff + timedelta(hours=1),
    )
    async with session_maker() as session:
        session.add_all([user, auth_session])
        await session.commit()

    async with session_maker() as session:
        with pytest.raises(SessionNotFoundError):
            await auth_service.validate_session(
                session,
                session_token=raw_token,
            )
        await session.commit()

    async with session_maker() as session:
        persisted = await session.get(AuthSession, auth_session.id)
        assert persisted is not None
        assert persisted.revoked_at is not None
        assert persisted.revoked_reason == SessionRevokedReason.ADMIN_FORCE


@pytest.mark.asyncio
async def test_session_validation_crossing_role_downgrade_fails_closed_then_retries(
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """A crossing request fails fast, then a retry observes the new role."""
    user = admin_user_factory(username="session-role-downgrade-race")
    session_token = "session-role-downgrade-race-token"
    now = datetime.now(timezone.utc)
    auth_session = AuthSession(
        id=uuid4(),
        user_id=user.id,
        session_token_hash=hash_opaque_token(session_token),
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )
    async with session_maker() as setup_db:
        setup_db.add_all([user, auth_session])
        await setup_db.commit()

    session_snapshot_read = asyncio.Event()

    class SignallingValidationSession(AsyncSession):
        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            result = await super().execute(statement, *args, **kwargs)
            if (
                str(statement).lstrip().upper().startswith("SELECT")
                and "auth_sessions" in str(statement)
            ):
                session_snapshot_read.set()
            return result

    validation_session_maker = async_sessionmaker(
        async_engine,
        expire_on_commit=False,
        class_=SignallingValidationSession,
    )

    async def validate_role() -> UserRole:
        async with validation_session_maker() as validation_db:
            result = await auth_service.validate_session(
                validation_db,
                session_token=session_token,
            )
            await validation_db.commit()
            return result.user.role

    async with session_maker() as downgrade_db:
        locked_user = await downgrade_db.get(
            UserAccount,
            user.id,
            populate_existing=True,
            with_for_update=True,
        )
        assert locked_user is not None
        locked_user.role = UserRole.ANALYST
        await downgrade_db.flush()

        validation_task = asyncio.create_task(validate_role())
        await asyncio.wait_for(session_snapshot_read.wait(), timeout=2)
        with pytest.raises(AuthenticationConcurrencyError):
            await asyncio.wait_for(validation_task, timeout=2)
        await downgrade_db.commit()

    validated_role = await validate_role()
    assert validated_role == UserRole.ANALYST


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


@pytest.mark.asyncio
async def test_temporary_password_lock_does_not_block_existing_session(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(username="session-survives-password-lock")

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    initial_login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert initial_login.status_code == 200
    session_token = initial_login.cookies.get("intercept_session")
    assert session_token is not None

    for _attempt in range(5):
        wrong_password = await client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": "wrong-password"},
        )
        assert wrong_password.status_code == 401

    session_response = await client.get(
        "/api/v1/auth/session",
        cookies={"intercept_session": session_token},
    )
    assert session_response.status_code == 200
    assert session_response.json()["user"]["id"] == str(user.id)

    password_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert password_response.status_code == 401

    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert refreshed.status is UserStatus.LOCKED
        assert refreshed.failed_login_attempts >= 5
        assert refreshed.lockout_expires_at is not None
        assert refreshed.lockout_expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_administratively_locked_account_cannot_self_unlock(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()
    user.status = UserStatus.LOCKED
    user.lockout_expires_at = None

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["message"] == "Unable to sign in with the provided credentials."

    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert refreshed.status == UserStatus.LOCKED
        assert refreshed.lockout_expires_at is None
        assert refreshed.last_login_at is None


@pytest.mark.asyncio
async def test_expired_temporary_lock_allows_login(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory()
    user.status = UserStatus.LOCKED
    user.failed_login_attempts = 5
    user.lockout_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 200, response.text
    async with session_maker() as session:
        refreshed = await session.get(UserAccount, user.id)
        assert refreshed is not None
        assert refreshed.status == UserStatus.ACTIVE
        assert refreshed.failed_login_attempts == 0
        assert refreshed.lockout_expires_at is None
