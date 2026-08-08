"""Role changes must permanently reconcile existing API-key scopes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.api_key_scopes import (
    API_ADMIN_SCOPE,
    API_READ_SCOPE,
    API_WRITE_SCOPE,
)
from app.models.enums import AccountType, SettingType, UserRole, UserStatus
from app.models.models import ApiKey, AppSetting, UserAccount
from app.services.admin_auth_service import admin_auth_service
from app.services.api_key_service import ApiKeyRevokedError, api_key_service
from app.services.audit_service import AuditContext
from app.services.oidc_service import OIDCIdentityPolicy, OIDCService


def _identity_policy() -> OIDCIdentityPolicy:
    return OIDCIdentityPolicy(
        jit_provisioning=False,
        default_role="ANALYST",
        role_claim_path="groups",
        role_mapping={
            "intercept-admins": "ADMIN",
            "intercept-analysts": "ANALYST",
        },
    )


def _over_scoped_key(*, user_id, prefix: str, key_hash: str) -> ApiKey:
    return ApiKey(
        user_id=user_id,
        name="pre-downgrade administrative key",
        prefix=prefix,
        key_hash=key_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        scopes=[API_READ_SCOPE, API_WRITE_SCOPE, API_ADMIN_SCOPE],
    )


@pytest.mark.asyncio
async def test_oidc_bypass_role_downgrade_permanently_revokes_over_scoped_key(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    user = admin_user_factory(username="oidc.scope.breakglass")
    user.oidc_issuer = "https://issuer.example"
    user.oidc_subject = "scope-breakglass-subject"
    api_key = _over_scoped_key(
        user_id=user.id,
        prefix="tmi_oidcscop",
        key_hash="oidc-scope-downgrade-hash",
    )

    async with session_maker() as db:
        db.add_all(
            [
                user,
                api_key,
                AppSetting(
                    key="oidc.sso_bypass_users",
                    value='["oidc.scope.breakglass"]',
                    value_type=SettingType.JSON,
                    is_secret=False,
                    category="oidc",
                ),
            ]
        )
        await db.commit()

    async with session_maker() as db:
        downgraded = await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "scope-breakglass-subject",
                "groups": ["intercept-analysts"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()
        assert downgraded.role is UserRole.ANALYST

    async with session_maker() as db:
        revoked = await db.get(ApiKey, api_key.id)
        assert revoked is not None
        assert revoked.revoked_at is not None
        revoked_at = revoked.revoked_at

    async with session_maker() as db:
        upgraded = await OIDCService().find_or_create_user(
            db,
            claims={
                "sub": "scope-breakglass-subject",
                "groups": ["intercept-admins"],
            },
            issuer="https://issuer.example",
            identity_policy=_identity_policy(),
        )
        await db.commit()
        assert upgraded.role is UserRole.ADMIN

    async with session_maker() as db:
        still_revoked = await db.get(ApiKey, api_key.id)
        assert still_revoked is not None
        assert still_revoked.revoked_at == revoked_at


@pytest.mark.asyncio
async def test_manual_nhi_role_downgrade_permanently_revokes_over_scoped_key(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    lifecycle_admin = admin_user_factory(username="scope.lifecycle.admin")
    service_user = UserAccount(
        username="scope.service.account",
        account_type=AccountType.NHI,
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    api_key = _over_scoped_key(
        user_id=service_user.id,
        prefix="tmi_nhiscope",
        key_hash="nhi-scope-downgrade-hash",
    )

    async with session_maker() as db:
        db.add_all([lifecycle_admin, service_user, api_key])
        await db.commit()

    async with session_maker() as db:
        await admin_auth_service.update_user(
            admin_user_id=lifecycle_admin.id,
            target_user_id=service_user.id,
            role=UserRole.AUDITOR,
            request_metadata=AuditContext(),
            db=db,
        )

    async with session_maker() as db:
        revoked = await db.get(ApiKey, api_key.id)
        assert revoked is not None
        assert revoked.revoked_at is not None
        revoked_at = revoked.revoked_at

        await admin_auth_service.update_user(
            admin_user_id=lifecycle_admin.id,
            target_user_id=service_user.id,
            role=UserRole.ADMIN,
            request_metadata=AuditContext(),
            db=db,
        )

    async with session_maker() as db:
        still_revoked = await db.get(ApiKey, api_key.id)
        assert still_revoked is not None
        assert still_revoked.revoked_at == revoked_at


@pytest.mark.asyncio
async def test_runtime_role_ceiling_check_revokes_drifted_key_before_reupgrade(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service_user = UserAccount(
        username="scope.runtime.drift",
        account_type=AccountType.NHI,
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    async with session_maker() as db:
        db.add(service_user)
        await db.flush()
        api_key, raw_key = await api_key_service.create_api_key(
            db,
            user_id=service_user.id,
            name="runtime ceiling defense",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE, API_ADMIN_SCOPE},
        )
        await db.commit()
        api_key_id = api_key.id

    # Simulate legacy or out-of-band role drift that skipped normal reconciliation.
    async with session_maker() as db:
        persisted_user = await db.get(UserAccount, service_user.id)
        assert persisted_user is not None
        persisted_user.role = UserRole.ANALYST
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(ApiKeyRevokedError):
            await api_key_service.validate_api_key(db, raw_key=raw_key)
        await db.rollback()

    async with session_maker() as db:
        revoked = await db.get(ApiKey, api_key_id)
        assert revoked is not None
        assert revoked.revoked_at is not None

        persisted_user = await db.get(UserAccount, service_user.id)
        assert persisted_user is not None
        persisted_user.role = UserRole.ADMIN
        await db.commit()

    async with session_maker() as db:
        with pytest.raises(ApiKeyRevokedError):
            await api_key_service.validate_api_key(db, raw_key=raw_key)


@pytest.mark.asyncio
async def test_explicit_revocation_crossing_api_key_validation_is_observed(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service_user = UserAccount(
        username="scope.explicit.revocation.race",
        account_type=AccountType.NHI,
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    async with session_maker() as db:
        db.add(service_user)
        await db.flush()
        api_key, raw_key = await api_key_service.create_api_key(
            db,
            user_id=service_user.id,
            name="crossing explicit revocation",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            scopes={API_READ_SCOPE},
        )
        await db.commit()
        user_id = service_user.id
        api_key_id = api_key.id

    initial_key_read = asyncio.Event()

    class _ObservedValidationSession:
        def __init__(self, delegate: AsyncSession) -> None:
            self._delegate = delegate

        async def execute(self, *args: object, **kwargs: object):
            result = await self._delegate.execute(*args, **kwargs)
            initial_key_read.set()
            return result

        def __getattr__(self, name: str):
            return getattr(self._delegate, name)

    async with (
        session_maker() as user_lock_db,
        session_maker() as validation_db,
    ):
        await user_lock_db.execute(
            select(UserAccount)
            .where(UserAccount.id == user_id)
            .with_for_update()
        )
        validation_task = asyncio.create_task(
            api_key_service.validate_api_key(
                _ObservedValidationSession(validation_db),  # type: ignore[arg-type]
                raw_key=raw_key,
            )
        )
        try:
            await asyncio.wait_for(initial_key_read.wait(), timeout=2)
            async with session_maker() as revocation_db:
                await api_key_service.revoke_api_key(
                    revocation_db,
                    api_key_id=api_key_id,
                )
                await revocation_db.commit()
            assert not validation_task.done()
        finally:
            await user_lock_db.rollback()

        with pytest.raises(ApiKeyRevokedError):
            await asyncio.wait_for(validation_task, timeout=5)
