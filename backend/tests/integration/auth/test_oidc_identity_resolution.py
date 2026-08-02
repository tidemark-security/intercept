from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import UserRole, UserStatus
from app.models.models import AuditLog, UserAccount
from app.services.oidc_service import (
    OIDCAuthenticationError,
    OIDCIdentityPolicy,
    OIDCService,
)


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
        "trusted_auto_link_issuers": ("https://issuer.example",),
    }
    values.update(updates)
    return OIDCIdentityPolicy(**values)  # type: ignore[arg-type]


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
                identity_policy=_identity_policy(
                    trusted_auto_link_issuers=("https://issuer.example/Tenant",),
                ),
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
