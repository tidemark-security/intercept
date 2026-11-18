from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import threading

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AccountType, SettingType, UserRole, UserStatus
from app.models.models import (
    ApiKey,
    AppSetting,
    AppSettingUpdate,
    AuthSession,
    PasskeyCredential,
    UserAccount,
)
from app.services.audit_service import AuditContext
from app.services.auth_service import InvalidCredentialsError, auth_service
from app.services.oidc_local_credential_policy import (
    oidc_local_credential_policy,
)
from app.services.settings_service import SettingsService
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_nhi_local_credential_capabilities_only_allow_api_keys(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user = UserAccount(
        username="automation-reader",
        account_type=AccountType.NHI,
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )

    async with session_maker() as db:
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )

    assert capabilities.password_login_allowed is False
    assert capabilities.passkey_allowed is False
    assert capabilities.api_key_allowed is True


@pytest.mark.asyncio
async def test_oidc_linked_analyst_cannot_create_or_use_local_credentials(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user = UserAccount(
        username="sso.analyst@example.com",
        email="sso.analyst@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="subject-analyst",
    )

    async with session_maker() as db:
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )

    assert capabilities.password_login_allowed is False
    assert capabilities.passkey_allowed is False
    assert capabilities.api_key_allowed is False


@pytest.mark.asyncio
async def test_oidc_linked_administrator_always_retains_break_glass_credentials(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user = UserAccount(
        username="sso.admin@example.com",
        email="sso.admin@example.com",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="subject-admin",
    )

    async with session_maker() as db:
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )

    assert capabilities.password_login_allowed is True
    assert capabilities.passkey_allowed is True
    assert capabilities.api_key_allowed is True


@pytest.mark.asyncio
async def test_configured_oidc_bypass_user_retains_local_credentials(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user = UserAccount(
        username="break.glass@example.com",
        email="break.glass@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        oidc_issuer="https://issuer.example",
        oidc_subject="subject-break-glass",
    )

    async with session_maker() as db:
        db.add(
            AppSetting(
                key="oidc.sso_bypass_users",
                value='["break.glass@example.com"]',
                value_type=SettingType.JSON,
                is_secret=False,
                category="oidc",
            )
        )
        await db.flush()

        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )

    assert capabilities.password_login_allowed is True
    assert capabilities.passkey_allowed is True
    assert capabilities.api_key_allowed is True


@pytest.mark.asyncio
async def test_enabling_oidc_immediately_revokes_unbypassed_human_credentials(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="enable-oidc-policy-admin")
    user = analyst_user_factory(username="unlinked-sso-user")
    api_key = ApiKey(
        user_id=user.id,
        name="pre-SSO API key",
        prefix="tmi_presso01",
        key_hash="pre-sso-api-key-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scopes=["api:read"],
    )
    passkey = PasskeyCredential(
        user_id=user.id,
        name="pre-SSO passkey",
        credential_id="pre-sso-credential-id",
        credential_public_key="pre-sso-public-key",
    )

    async with session_maker() as db:
        db.add_all(
            [
                admin,
                user,
                api_key,
                passkey,
                AppSetting(
                    key="oidc.enabled",
                    value="false",
                    value_type=SettingType.BOOLEAN,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")

    update_response = await client.put(
        "/api/v1/admin/settings/oidc.enabled",
        json={"value": "true"},
        cookies={"intercept_session": session_cookie},
    )
    assert update_response.status_code == 200

    api_keys_response = await client.get(
        "/api/v1/api-keys",
        params={"user_id": str(user.id), "include_revoked": "true"},
        cookies={"intercept_session": session_cookie},
    )
    passkeys_response = await client.get(
        f"/api/v1/admin/auth/users/{user.id}/passkeys",
        cookies={"intercept_session": session_cookie},
    )

    assert api_keys_response.status_code == 200
    assert api_keys_response.json()[0]["revoked_at"] is not None
    assert passkeys_response.status_code == 200
    assert passkeys_response.json()[0]["revokedAt"] is not None


@pytest.mark.asyncio
async def test_oidc_policy_change_during_verification_prevents_stale_login(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A policy commit during Argon2 work must prevent stale local login."""
    user = analyst_user_factory(username="policy-login-race")
    async with session_maker() as setup_db:
        setup_db.add_all(
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
        await setup_db.commit()

    password_verification_started = threading.Event()
    continue_password_verification = threading.Event()

    def _held_password_verification(_encoded: str, _candidate: str) -> bool:
        password_verification_started.set()
        assert continue_password_verification.wait(timeout=3)
        return True

    monkeypatch.setattr(
        auth_service._password_hasher,
        "verify",
        _held_password_verification,
    )

    async def _login() -> AuthSession:
        async with session_maker() as login_db:
            result = await auth_service.login(
                login_db,
                username=user.username,
                password=DEFAULT_TEST_PASSWORD,
                metadata=AuditContext(),
            )
            await login_db.commit()
            return result.session

    async def _enable_oidc() -> None:
        async with session_maker() as settings_db:
            await SettingsService(settings_db).update_setting(
                "oidc.enabled",
                AppSettingUpdate(value="true"),
                performed_by="policy-race-admin",
            )

    login_task = asyncio.create_task(_login())
    assert await asyncio.to_thread(password_verification_started.wait, 3)
    policy_task = asyncio.create_task(_enable_oidc())

    try:
        completed, _pending = await asyncio.wait({policy_task}, timeout=1)
        policy_completed_during_verification = policy_task in completed
    finally:
        continue_password_verification.set()

    await asyncio.wait_for(policy_task, timeout=3)
    with pytest.raises(InvalidCredentialsError):
        await asyncio.wait_for(login_task, timeout=3)

    assert policy_completed_during_verification is True

    async with session_maker() as read_db:
        persisted_user = await read_db.get(UserAccount, user.id)
        session_result = await read_db.execute(
            select(AuthSession).where(AuthSession.user_id == user.id)
        )
        persisted_sessions = list(session_result.scalars())
        assert persisted_user is not None
        assert persisted_user.credentials_invalidated_at is not None
        assert persisted_sessions == []


@pytest.mark.asyncio
async def test_removing_oidc_bypass_user_immediately_revokes_local_credentials(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="credential-policy-admin")
    user = analyst_user_factory(username="former-break-glass-user")
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "former-break-glass-subject"
    api_key = ApiKey(
        user_id=user.id,
        name="break-glass API key",
        prefix="tmi_breakgla",
        key_hash="former-break-glass-api-key-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scopes=["api:read"],
    )
    passkey = PasskeyCredential(
        user_id=user.id,
        name="break-glass passkey",
        credential_id="former-break-glass-credential-id",
        credential_public_key="former-break-glass-public-key",
    )

    async with session_maker() as db:
        db.add_all(
            [
                admin,
                user,
                api_key,
                passkey,
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value='["former-break-glass-user"]',
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")

    update_response = await client.put(
        "/api/v1/admin/settings/oidc.sso_bypass_users",
        json={"value": "[]"},
        cookies={"intercept_session": session_cookie},
    )
    assert update_response.status_code == 200

    api_keys_response = await client.get(
        "/api/v1/api-keys",
        params={"user_id": str(user.id), "include_revoked": "true"},
        cookies={"intercept_session": session_cookie},
    )
    passkeys_response = await client.get(
        f"/api/v1/admin/auth/users/{user.id}/passkeys",
        cookies={"intercept_session": session_cookie},
    )

    assert api_keys_response.status_code == 200
    assert api_keys_response.json()[0]["revoked_at"] is not None
    assert passkeys_response.status_code == 200
    assert passkeys_response.json()[0]["revokedAt"] is not None


@pytest.mark.asyncio
async def test_deleting_oidc_bypass_setting_immediately_revokes_local_credentials(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory(username="delete-policy-admin")
    user = analyst_user_factory(username="deleted-break-glass-user")
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "deleted-break-glass-subject"
    api_key = ApiKey(
        user_id=user.id,
        name="deleted bypass API key",
        prefix="tmi_delbypas",
        key_hash="deleted-break-glass-api-key-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scopes=["api:read"],
    )
    passkey = PasskeyCredential(
        user_id=user.id,
        name="deleted bypass passkey",
        credential_id="deleted-break-glass-credential-id",
        credential_public_key="deleted-break-glass-public-key",
    )

    async with session_maker() as db:
        db.add_all(
            [
                admin,
                user,
                api_key,
                passkey,
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value='["deleted-break-glass-user"]',
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")

    delete_response = await client.delete(
        "/api/v1/admin/settings/oidc.sso_bypass_users",
        cookies={"intercept_session": session_cookie},
    )
    assert delete_response.status_code == 204

    api_keys_response = await client.get(
        "/api/v1/api-keys",
        params={"user_id": str(user.id), "include_revoked": "true"},
        cookies={"intercept_session": session_cookie},
    )
    passkeys_response = await client.get(
        f"/api/v1/admin/auth/users/{user.id}/passkeys",
        cookies={"intercept_session": session_cookie},
    )

    assert api_keys_response.status_code == 200
    assert api_keys_response.json()[0]["revoked_at"] is not None
    assert passkeys_response.status_code == 200
    assert passkeys_response.json()[0]["revokedAt"] is not None
