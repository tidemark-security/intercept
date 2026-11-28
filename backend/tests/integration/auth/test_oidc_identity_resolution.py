from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastmcp.server.auth import AccessToken
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.api_key_scopes import API_ADMIN_SCOPE, API_READ_SCOPE
from app.mcp.auth import MCP_ACCESS_SCOPE
from app.mcp.principal import require_mcp_principal
from app.models.enums import UserRole, UserStatus
from app.models.models import (
    ApiKey,
    AuditLog,
    AuthSession,
    PasskeyCredential,
    UserAccount,
)
from app.services.admin_auth_service import AdminAuthBusyError, admin_auth_service
from app.services.audit_service import AuditContext
from app.services.auth_service import auth_service
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCIdentityPolicy,
    OIDCService,
)
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _identity_policy(**updates: object) -> OIDCIdentityPolicy:
    values: dict[str, object] = {
        "jit_provisioning": False,
        "default_role": "ANALYST",
        "role_claim_path": "groups",
        "role_mapping": {
            "intercept-admins": "ADMIN",
            "intercept-analysts": "ANALYST",
            "intercept-auditors": "AUDITOR",
        },
    }
    values.update(updates)
    return OIDCIdentityPolicy(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_existing_oidc_user_lock_orders_session_before_admin_disable(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_admin = admin_user_factory(username="oidc.lock.admin")
    user = analyst_user_factory(username="oidc.lock.user")
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "row-locked-subject"
    async with session_maker() as db:
        db.add_all([lifecycle_admin, user])
        await db.commit()

    oidc_lock_acquired = asyncio.Event()
    allow_oidc_commit = asyncio.Event()
    disable_lock_requested = asyncio.Event()
    service = OIDCService()

    async def blocking_resolve_role(
        _db: AsyncSession,
        *,
        claims: dict[str, object],
        identity_policy: OIDCIdentityPolicy | None = None,
    ) -> UserRole:
        _ = claims, identity_policy
        oidc_lock_acquired.set()
        await allow_oidc_commit.wait()
        return UserRole.ANALYST

    monkeypatch.setattr(service, "resolve_role", blocking_resolve_role)

    class _ObservedAdminSession:
        def __init__(self, delegate: AsyncSession) -> None:
            self._delegate = delegate

        async def execute(self, *args: object, **kwargs: object):
            disable_lock_requested.set()
            return await self._delegate.execute(*args, **kwargs)

        def __getattr__(self, name: str):
            return getattr(self._delegate, name)

    async def finish_oidc_login() -> object:
        async with session_maker() as db:
            resolved = await service.find_or_create_user(
                db,
                claims={
                    "sub": "row-locked-subject",
                    "groups": ["intercept-analysts"],
                },
                issuer="https://issuer.example",
                identity_policy=_identity_policy(),
            )
            login = await auth_service.create_session_for_user(
                db,
                user=resolved,
                metadata=AuditContext(),
            )
            await db.commit()
            return login.session.id

    async def disable_user() -> None:
        async with session_maker() as db:
            await admin_auth_service.update_user_status(
                admin_user_id=lifecycle_admin.id,
                target_user_id=user.id,
                new_status=UserStatus.DISABLED,
                request_metadata=AuditContext(),
                db=_ObservedAdminSession(db),  # type: ignore[arg-type]
            )

    login_task = asyncio.create_task(finish_oidc_login())
    await oidc_lock_acquired.wait()
    disable_task = asyncio.create_task(disable_user())
    await disable_lock_requested.wait()
    with pytest.raises(AdminAuthBusyError):
        await asyncio.wait_for(disable_task, timeout=2)

    allow_oidc_commit.set()
    session_id = await login_task
    await disable_user()

    async with session_maker() as db:
        persisted_user = await db.get(UserAccount, user.id)
        persisted_session = await db.get(AuthSession, session_id)
    assert persisted_user is not None
    assert persisted_user.status is UserStatus.DISABLED
    assert persisted_user.credentials_invalidated_at is not None
    assert persisted_session is not None
    assert persisted_session.revoked_at is not None


@pytest.mark.asyncio
async def test_preprovisioned_oidc_identity_does_not_require_email_claim(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="preprovisioned.analyst",
        email="preprovisioned.analyst@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "Provider-Subject-123"

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        resolved = await OIDCService().find_or_create_user(
            db,
            claims={"sub": "Provider-Subject-123", "groups": ["intercept-analysts"]},
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )

        assert resolved.id == user.id
        assert resolved.role is UserRole.ANALYST


@pytest.mark.asyncio
async def test_temporary_password_lock_does_not_block_oidc_identity(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    lockout_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    user = admin_user_factory(
        username="temporarily.password.locked.admin",
        email="temporarily.password.locked.admin@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "temporarily-password-locked-subject"
    user.status = UserStatus.LOCKED
    user.failed_login_attempts = 5
    user.lockout_expires_at = lockout_expires_at

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        resolved = await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "temporarily-password-locked-subject",
                "groups": ["intercept-admins"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        login = await auth_service.create_session_for_user(
            db,
            user=resolved,
            metadata=AuditContext(),
        )
        await db.commit()

        assert resolved.id == user.id
        assert login.user.id == user.id
        assert login.session.user_id == user.id
        assert resolved.status is UserStatus.LOCKED
        assert resolved.failed_login_attempts == 5
        assert resolved.lockout_expires_at == lockout_expires_at


@pytest.mark.asyncio
async def test_oidc_login_persists_and_audits_role_downgrade(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    user = admin_user_factory(
        username="downgraded.admin",
        email="downgraded.admin@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "downgrade-subject"

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        resolved = await OIDCService().find_or_create_user(
            db,
            claims={"sub": "downgrade-subject", "groups": ["intercept-analysts"]},
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()

        assert resolved.role is UserRole.ANALYST

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        role_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "auth.oidc.role_changed",
                    AuditLog.entity_id == str(user.id),
                )
            )
        ).scalars().all()

        assert persisted is not None
        assert persisted.role is UserRole.ANALYST
        assert len(role_audits) == 1
        assert json.loads(role_audits[0].old_value or "null") == {"role": "ADMIN"}
        assert json.loads(role_audits[0].new_value or "null") == {"role": "ANALYST"}


@pytest.mark.asyncio
async def test_existing_session_loses_admin_authorization_after_oidc_role_downgrade(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    user = admin_user_factory(
        username="session.downgrade.admin",
        email="session.downgrade.admin@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "session-downgrade-subject"
    async with session_maker() as db:
        db.add(user)
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    cookies = {"intercept_session": session_cookie}

    allowed = await client.get("/api/v1/admin/auth/users", cookies=cookies)
    assert allowed.status_code == 200

    async with session_maker() as db:
        await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "session-downgrade-subject",
                "groups": ["intercept-analysts"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()

    denied = await client.get("/api/v1/admin/auth/users", cookies=cookies)
    assert denied.status_code == 403
    assert "admin" in denied.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_existing_api_key_loses_admin_authorization_after_oidc_role_downgrade(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    user = admin_user_factory(
        username="api.key.downgrade.admin",
        email="api.key.downgrade.admin@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "api-key-downgrade-subject"
    async with session_maker() as db:
        db.add(user)
        await db.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    create_response = await client.post(
        "/api/v1/api-keys",
        json={
            "name": "pre-downgrade admin key",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).isoformat(),
            "scopes": [API_READ_SCOPE, API_ADMIN_SCOPE],
        },
        cookies={"intercept_session": session_cookie},
    )
    assert create_response.status_code == 201, create_response.text
    raw_key = create_response.json()["key"]
    headers = {"Authorization": f"Bearer {raw_key}"}

    allowed = await client.get("/api/v1/admin/auth/users", headers=headers)
    assert allowed.status_code == 200

    async with session_maker() as db:
        await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "api-key-downgrade-subject",
                "groups": ["intercept-analysts"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()

    denied = await client.get("/api/v1/admin/auth/users", headers=headers)
    assert denied.status_code == 401
    assert "revoked" in denied.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_existing_mcp_token_loses_admin_role_after_oidc_role_downgrade(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    user = admin_user_factory(
        username="mcp.downgrade.admin",
        email="mcp.downgrade.admin@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "mcp-downgrade-subject"
    async with session_maker() as db:
        db.add(user)
        await db.commit()

    token = AccessToken(
        token="pre-downgrade-reference-token",
        client_id="pre-downgrade-client",
        scopes=[MCP_ACCESS_SCOPE],
        claims={
            "intercept_user_id": str(user.id),
            "auth_source": "oidc",
        },
    )
    before = await require_mcp_principal(
        access_token=token,
        session_factory=session_maker,
    )
    assert before.user.role is UserRole.ADMIN

    async with session_maker() as db:
        await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "mcp-downgrade-subject",
                "groups": ["intercept-analysts"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()

    after = await require_mcp_principal(
        access_token=token,
        session_factory=session_maker,
    )
    assert after.user.id == user.id
    assert after.user.role is UserRole.ANALYST


@pytest.mark.asyncio
async def test_oidc_role_downgrade_and_reenable_never_resurrect_local_credentials(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    lifecycle_admin = admin_user_factory(
        username="credential.lifecycle.admin",
        email="credential.lifecycle.admin@example.com",
    )
    user = admin_user_factory(
        username="credential.downgrade.admin",
        email="credential.downgrade.admin@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "credential-downgrade-subject"
    api_key = ApiKey(
        user_id=user.id,
        name="pre-downgrade key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scopes=["api:read"],
        prefix="tmi_oidcdown",
        key_hash="oidc-role-downgrade-key-hash",
    )
    passkey = PasskeyCredential(
        user_id=user.id,
        name="pre-downgrade passkey",
        credential_id="oidc-role-downgrade-credential-id",
        credential_public_key="oidc-role-downgrade-public-key",
    )

    async with session_maker() as db:
        db.add_all([lifecycle_admin, user, api_key, passkey])
        await db.commit()

    async with session_maker() as db:
        downgraded = await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "credential-downgrade-subject",
                "groups": ["intercept-analysts"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()
        assert downgraded.role is UserRole.ANALYST

    async with session_maker() as db:
        revoked_key = await db.get(ApiKey, api_key.id)
        revoked_passkey = await db.get(PasskeyCredential, passkey.id)
        assert revoked_key is not None
        assert revoked_passkey is not None
        assert revoked_key.revoked_at is not None
        assert revoked_passkey.revoked_at is not None
        key_revoked_at = revoked_key.revoked_at
        passkey_revoked_at = revoked_passkey.revoked_at

    async with session_maker() as db:
        upgraded = await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "credential-downgrade-subject",
                "groups": ["intercept-admins"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()
        assert upgraded.role is UserRole.ADMIN

    async with session_maker() as db:
        await admin_auth_service.update_user_status(
            admin_user_id=lifecycle_admin.id,
            target_user_id=user.id,
            new_status=UserStatus.DISABLED,
            request_metadata=AuditContext(),
            db=db,
        )
        await admin_auth_service.update_user_status(
            admin_user_id=lifecycle_admin.id,
            target_user_id=user.id,
            new_status=UserStatus.ACTIVE,
            request_metadata=AuditContext(),
            db=db,
        )

    async with session_maker() as db:
        persisted_key = await db.get(ApiKey, api_key.id)
        persisted_passkey = await db.get(PasskeyCredential, passkey.id)
        assert persisted_key is not None
        assert persisted_passkey is not None
        assert persisted_key.revoked_at == key_revoked_at
        assert persisted_passkey.revoked_at == passkey_revoked_at


@pytest.mark.asyncio
async def test_database_rejects_partial_oidc_identity_pairs(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="partial.oidc.identity",
        email="partial.oidc.identity@example.com",
    )
    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(IntegrityError):
            await db.execute(
                update(UserAccount)
                .where(UserAccount.id == user.id)
                .values(
                    oidc_issuer="https://issuer.example",
                    oidc_subject=None,
                )
            )
            await db.commit()
        await db.rollback()


@pytest.mark.asyncio
async def test_oidc_identity_match_is_case_sensitive_and_never_falls_back_to_email(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="case.sensitive.identity",
        email="case.sensitive.identity@example.com",
    )
    user.oidc_issuer = "https://Issuer.example/Tenant"
    user.oidc_subject = "Case-Sensitive-Subject"

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(
            OIDCAuthenticationError,
            match="not enabled for unprovisioned users",
        ):
            await OIDCService().find_or_create_user(
                db,
                claims={
                    "sub": "case-sensitive-subject",
                    "email": "case.sensitive.identity@example.com",
                },
                issuer="https://issuer.example/Tenant",
                identity_policy=_identity_policy(),
            )

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        assert persisted is not None
        assert persisted.oidc_issuer == "https://Issuer.example/Tenant"
        assert persisted.oidc_subject == "Case-Sensitive-Subject"


@pytest.mark.asyncio
async def test_preferred_username_neither_links_an_account_nor_replaces_email_claim(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="existing.local.user",
        email="existing.local.user@example.com",
    )

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(
            OIDCAuthenticationError,
            match="did not include an email address",
        ):
            await OIDCService().find_or_create_user(
                db,
                claims={
                    "sub": "new-provider-subject",
                    "preferred_username": "existing.local.user@example.com",
                },
                issuer="https://issuer.example",
                identity_policy=_identity_policy(jit_provisioning=True),
            )

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        assert persisted is not None
        assert persisted.oidc_issuer is None
        assert persisted.oidc_subject is None


@pytest.mark.asyncio
async def test_jit_email_collision_is_rejected_without_linking_existing_account(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="email.collision",
        email="email.collision@example.com",
    )

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(
            OIDCAuthenticationError,
            match="email collides with an existing account",
        ):
            await OIDCService().find_or_create_user(
                db,
                claims={
                    "sub": "jit-collision-subject",
                    "email": "email.collision@example.com",
                    "preferred_username": "different.jit.username",
                },
                issuer="https://issuer.example",
                identity_policy=_identity_policy(jit_provisioning=True),
            )

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        assert persisted is not None
        assert persisted.oidc_issuer is None
        assert persisted.oidc_subject is None


@pytest.mark.asyncio
async def test_oidc_subject_is_compared_without_whitespace_normalization(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="exact.subject",
        email="exact.subject@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "exact-subject"

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(
            OIDCAuthenticationError,
            match="not enabled for unprovisioned users",
        ):
            await OIDCService().find_or_create_user(
                db,
                claims={"sub": " exact-subject ", "email": "exact.subject@example.com"},
                issuer="https://issuer.example",
                identity_policy=_identity_policy(),
            )


@pytest.mark.asyncio
async def test_jit_creates_new_identity_from_actual_email_claim(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as db:
        provisioned = await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "new-jit-subject",
                "email": "contact.address@example.com",
                "preferred_username": "new.jit.username",
                "groups": ["intercept-auditors"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(jit_provisioning=True),
        )
        await db.commit()
        provisioned_id = provisioned.id

    async with session_maker() as db:
        persisted = await db.get(UserAccount, provisioned_id)
        provision_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "auth.oidc.account_provisioned",
                    AuditLog.entity_id == str(provisioned_id),
                )
            )
        ).scalars().all()

        assert persisted is not None
        assert persisted.username == "new.jit.username"
        assert str(persisted.email) == "contact.address@example.com"
        assert persisted.oidc_issuer == "https://issuer.example"
        assert persisted.oidc_subject == "new-jit-subject"
        assert persisted.role is UserRole.AUDITOR
        assert len(provision_audits) == 1


@pytest.mark.asyncio
async def test_oidc_login_persists_and_audits_role_upgrade(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="upgraded.analyst",
        email="upgraded.analyst@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "upgrade-subject"

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        resolved = await OIDCService().find_or_create_user(
            db,
            claims={"sub": "upgrade-subject", "groups": ["intercept-admins"]},
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()

        assert resolved.role is UserRole.ADMIN

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        role_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "auth.oidc.role_changed",
                    AuditLog.entity_id == str(user.id),
                )
            )
        ).scalars().all()

        assert persisted is not None
        assert persisted.role is UserRole.ADMIN
        assert len(role_audits) == 1
        assert json.loads(role_audits[0].old_value or "null") == {"role": "ANALYST"}
        assert json.loads(role_audits[0].new_value or "null") == {"role": "ADMIN"}


@pytest.mark.asyncio
async def test_inactive_oidc_identity_is_rejected_before_role_reconciliation(
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
) -> None:
    user = analyst_user_factory(
        username="disabled.oidc.user",
        email="disabled.oidc.user@example.com",
    )
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "disabled-subject"
    user.status = UserStatus.DISABLED

    async with session_maker() as db:
        db.add(user)
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(OIDCAuthenticationError, match="is not active"):
            await OIDCService().find_or_create_user(
                db,
                claims={"sub": "disabled-subject", "groups": ["intercept-admins"]},
                issuer="https://issuer.example",
                identity_policy=_identity_policy(),
            )

    async with session_maker() as db:
        persisted = await db.get(UserAccount, user.id)
        role_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.event_type == "auth.oidc.role_changed",
                    AuditLog.entity_id == str(user.id),
                )
            )
        ).scalars().all()

        assert persisted is not None
        assert persisted.role is UserRole.ANALYST
        assert role_audits == []
