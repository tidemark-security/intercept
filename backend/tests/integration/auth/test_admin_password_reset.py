"""Integration tests for admin-issued password reset endpoints."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import threading

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import SessionRevokedReason, SettingType, UserStatus
from app.models.models import AdminResetRequest, AppSetting, AuthSession, UserAccount
from app.core.authorization_lock import acquire_authorization_lock
from app.services.admin_auth_service import admin_auth_service
from app.services.security.password_hasher import PasswordHasher
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


class _HeldResetHasher:
    def __init__(self, result_hash: str) -> None:
        self.result_hash = result_hash
        self.started = threading.Event()
        self.release = threading.Event()

    def hash(self, _password: str) -> str:
        self.started.set()
        assert self.release.wait(timeout=5)
        return self.result_hash


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
async def test_admin_cannot_issue_password_reset_for_oidc_only_user(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="reset-policy-admin")
    analyst = analyst_user_factory(username="oidc-only-reset-target")
    analyst.oidc_issuer = "https://issuer.example"
    analyst.oidc_subject = "oidc-only-reset-target-subject"

    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login_response.cookies.get("intercept_session")

    response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst.id)},
        cookies={"intercept_session": session_cookie},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_issue_password_reset_for_oidc_break_glass_users(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    issuer = admin_user_factory(username="break-glass-reset-issuer")
    target_admin = admin_user_factory(username="linked-reset-target-admin")
    target_admin.oidc_issuer = "https://issuer.example"
    target_admin.oidc_subject = "linked-reset-target-admin-subject"
    target_bypass = analyst_user_factory(username="linked-reset-target-bypass")
    target_bypass.oidc_issuer = "https://issuer.example"
    target_bypass.oidc_subject = "linked-reset-target-bypass-subject"

    async with session_maker() as session:
        session.add_all(
            [
                issuer,
                target_admin,
                target_bypass,
                AppSetting(
                    key="oidc.enabled",
                    value="true",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                ),
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value='["linked-reset-target-bypass"]',
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": issuer.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login_response.cookies.get("intercept_session")

    for target in (target_admin, target_bypass):
        response = await client.post(
            "/api/v1/admin/auth/password-resets",
            json={"userId": str(target.id)},
            cookies={"intercept_session": session_cookie},
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_reset_token_cannot_restore_password_after_oidc_bypass_is_removed(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="consume-reset-policy-admin")
    analyst = analyst_user_factory(username="reset-token-bypass-target")
    analyst.oidc_issuer = "https://issuer.example"
    analyst.oidc_subject = "reset-token-bypass-target-subject"

    async with session_maker() as session:
        session.add_all(
            [
                admin,
                analyst,
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value='["reset-token-bypass-target"]',
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    session_cookie = login_response.cookies.get("intercept_session")
    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst.id)},
        cookies={"intercept_session": session_cookie},
    )
    assert reset_response.status_code == 201
    reset_token = reset_response.json()["resetToken"]

    remove_bypass_response = await client.put(
        "/api/v1/admin/settings/oidc.sso_bypass_users",
        json={"value": "[]"},
        cookies={"intercept_session": session_cookie},
    )
    assert remove_bypass_response.status_code == 200

    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "newPassword": "RejectedNewPassword123!"},
    )
    assert consume_response.status_code == 403

    restore_bypass_response = await client.put(
        "/api/v1/admin/settings/oidc.sso_bypass_users",
        json={"value": '["reset-token-bypass-target"]'},
        cookies={"intercept_session": session_cookie},
    )
    assert restore_bypass_response.status_code == 200

    replay_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "newPassword": "RejectedNewPassword123!"},
    )
    assert replay_response.status_code == 400

    replacement_reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst.id)},
        cookies={"intercept_session": session_cookie},
    )
    assert replacement_reset_response.status_code == 201
    allowed_consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": replacement_reset_response.json()["resetToken"],
            "newPassword": "RestoredBypassPassword123!",
        },
    )
    assert allowed_consume_response.status_code == 204


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
async def test_password_change_during_off_lock_reset_hash_invalidates_token(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
    password_hasher: PasswordHasher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = admin_user_factory(username="reset-version-admin")
    analyst = analyst_user_factory(username="reset-version-target")
    initial_password_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    token_created_at = initial_password_time + timedelta(minutes=1)
    analyst.password_updated_at = initial_password_time
    token = "reset-token-bound-to-password-version"
    reset_request = AdminResetRequest(
        target_user_id=analyst.id,
        issued_by_admin_id=admin.id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        created_at=token_created_at,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    emergency_hash = password_hasher.hash("EmergencyResetPassword123!")
    async with session_maker() as db:
        db.add_all([admin, analyst, reset_request])
        await db.commit()

    held_hasher = _HeldResetHasher("must-not-be-persisted")
    monkeypatch.setattr(admin_auth_service, "_hasher", held_hasher)
    consume_task = asyncio.create_task(
        client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "newPassword": "StaleResetPassword123!"},
        )
    )
    assert await asyncio.to_thread(held_hasher.started.wait, 3)

    async def emergency_password_change() -> None:
        async with session_maker() as db:
            await acquire_authorization_lock(
                db,
                user_id=analyst.id,
                shared=False,
            )
            stored = await db.get(UserAccount, analyst.id, with_for_update=True)
            assert stored is not None
            stored.password_hash = emergency_hash
            stored.password_updated_at = datetime.now(timezone.utc)
            await db.commit()

    try:
        await asyncio.wait_for(emergency_password_change(), timeout=1)
    finally:
        held_hasher.release.set()

    response = await asyncio.wait_for(consume_task, timeout=5)
    assert response.status_code == 400
    async with session_maker() as db:
        stored_user = await db.get(UserAccount, analyst.id)
        stored_request = await db.get(AdminResetRequest, reset_request.id)
    assert stored_user is not None
    assert stored_user.password_hash == emergency_hash
    assert stored_request is not None
    assert stored_request.invalidated_at is not None
    assert stored_request.consumed_at is None


@pytest.mark.asyncio
async def test_reset_token_reactivates_a_temporarily_password_locked_account(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="temporary-lock-reset-admin")
    analyst = analyst_user_factory(username="temporary-lock-reset-target")
    analyst.status = UserStatus.LOCKED
    analyst.failed_login_attempts = 5
    analyst.lockout_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    new_password = "TemporaryLockResetPassword123!"

    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_cookie = admin_login.cookies.get("intercept_session")
    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst.id)},
        cookies={"intercept_session": admin_cookie},
    )
    assert reset_response.status_code == 201

    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_response.json()["resetToken"],
            "newPassword": new_password,
        },
    )
    assert consume_response.status_code == 204

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": new_password},
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_reset_token_cannot_reactivate_an_administratively_locked_account(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="locked-reset-admin")
    analyst = analyst_user_factory(username="locked-reset-target")
    new_password = "LockedAccountNewPassword123!"

    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_cookie = admin_login.cookies.get("intercept_session")
    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst.id)},
        cookies={"intercept_session": admin_cookie},
    )
    assert reset_response.status_code == 201

    lock_response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst.id}/status",
        json={"status": "LOCKED"},
        cookies={"intercept_session": admin_cookie},
    )
    assert lock_response.status_code == 204

    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_response.json()["resetToken"],
            "newPassword": new_password,
        },
    )
    assert consume_response.status_code == 204

    async with session_maker() as session:
        refreshed = await session.get(UserAccount, analyst.id)
        assert refreshed is not None
        assert refreshed.status == UserStatus.LOCKED
        assert refreshed.lockout_expires_at is None

    locked_login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": new_password},
    )
    assert locked_login.status_code == 401

    reactivate_response = await client.patch(
        f"/api/v1/admin/auth/users/{analyst.id}/status",
        json={"status": "ACTIVE"},
        cookies={"intercept_session": admin_cookie},
    )
    assert reactivate_response.status_code == 204

    active_login = await client.post(
        "/api/v1/auth/login",
        json={"username": analyst.username, "password": new_password},
    )
    assert active_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_token_issued_before_disable_stays_invalid_after_reenable(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="reset-lifecycle-admin")
    analyst = analyst_user_factory(username="reset-lifecycle-target")
    async with session_maker() as session:
        session.add_all([admin, analyst])
        await session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    admin_cookie = admin_login.cookies.get("intercept_session")
    reset_response = await client.post(
        "/api/v1/admin/auth/password-resets",
        json={"userId": str(analyst.id)},
        cookies={"intercept_session": admin_cookie},
    )
    assert reset_response.status_code == 201
    reset_token = reset_response.json()["resetToken"]

    for status_value in ("DISABLED", "ACTIVE"):
        response = await client.patch(
            f"/api/v1/admin/auth/users/{analyst.id}/status",
            json={"status": status_value},
            cookies={"intercept_session": admin_cookie},
        )
        assert response.status_code == 204, response.text

    consume_response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "newPassword": "MustRemainInvalidAfterDisable123!",
        },
    )

    assert consume_response.status_code == 400
    async with session_maker() as session:
        reset_request = (
            await session.execute(
                select(AdminResetRequest).where(
                    AdminResetRequest.target_user_id == analyst.id
                )
            )
        ).scalar_one()
        assert reset_request.invalidated_at is not None
        assert reset_request.consumed_at is None


@pytest.mark.asyncio
async def test_pre_cutoff_reset_committed_after_disable_is_rejected(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="reset-race-admin")
    analyst = analyst_user_factory(username="reset-race-target")
    cutoff = datetime.now(timezone.utc)
    analyst.credentials_invalidated_at = cutoff
    reset_token = "pre-cutoff-reset-committed-after-disable"
    original_password_hash = analyst.password_hash
    reset_request = AdminResetRequest(
        target_user_id=analyst.id,
        issued_by_admin_id=admin.id,
        token_hash=hashlib.sha256(reset_token.encode("utf-8")).hexdigest(),
        expires_at=cutoff + timedelta(minutes=5),
        created_at=cutoff - timedelta(seconds=1),
    )

    async with session_maker() as session:
        session.add_all([admin, analyst, reset_request])
        await session.commit()

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "newPassword": "MustNotEscapeCredentialCutoff123!",
        },
    )

    assert response.status_code == 400
    async with session_maker() as session:
        persisted_request = await session.get(AdminResetRequest, reset_request.id)
        persisted_user = await session.get(UserAccount, analyst.id)
        assert persisted_request is not None
        assert persisted_request.invalidated_at is not None
        assert persisted_request.consumed_at is None
        assert persisted_user is not None
        assert persisted_user.password_hash == original_password_hash


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
