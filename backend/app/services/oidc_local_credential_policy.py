"""Server-side local-credential policy for human and non-human accounts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.account_authentication import non_password_authentication_allowed
from app.core.api_key_scopes import allowed_api_key_scopes, normalize_api_key_scopes
from app.core.authorization_lock import acquire_authorization_lock
from app.models.enums import AccountType, SessionRevokedReason, UserRole
from app.models.models import (
    ApiKey,
    AuthSession,
    PasskeyCredential,
    UserAccount,
    WebAuthnChallenge,
)
from app.services.settings_service import SettingsService


@dataclass(frozen=True, slots=True)
class LocalCredentialCapabilities:
    """Local credential operations currently available to a user."""

    password_login_allowed: bool
    passkey_allowed: bool
    api_key_allowed: bool


class OIDCLocalCredentialPolicy:
    """Resolve local credentials from account, OIDC, and break-glass policy."""

    async def capabilities_for(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
    ) -> LocalCredentialCapabilities:
        if user.account_type == AccountType.NHI:
            return LocalCredentialCapabilities(False, False, True)

        bypass_allowed = user.role == UserRole.ADMIN
        settings = SettingsService(db)
        oidc_enabled = bool(await settings.get("oidc.enabled", default=False))
        linked_to_oidc = bool(user.oidc_issuer or user.oidc_subject)
        if not oidc_enabled and not linked_to_oidc:
            return LocalCredentialCapabilities(True, True, True)

        if not bypass_allowed:
            raw_bypass_users = await settings.get("oidc.sso_bypass_users", default=[])
            if isinstance(raw_bypass_users, str):
                raw_bypass_users = [raw_bypass_users]
            bypass_allowed = user.username in {
                str(item).strip().lower()
                for item in raw_bypass_users or []
                if str(item).strip()
            }

        return LocalCredentialCapabilities(
            password_login_allowed=bypass_allowed,
            passkey_allowed=bypass_allowed,
            api_key_allowed=bypass_allowed,
        )

    async def revoke_all_local_credentials(
        self,
        db: AsyncSession,
        *,
        user_id: Any,
    ) -> None:
        """Permanently revoke active passkeys and API keys for one account."""
        now = datetime.now(timezone.utc)
        await db.execute(
            update(ApiKey)
            .where(
                cast(Any, ApiKey.user_id == user_id),
                cast(Any, ApiKey.revoked_at == None),  # noqa: E711
            )
            .values(revoked_at=now)
        )
        await db.execute(
            update(PasskeyCredential)
            .where(
                cast(Any, PasskeyCredential.user_id == user_id),
                cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
            )
            .values(revoked_at=now, updated_at=now)
        )

    async def revoke_impermissible_credentials(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
    ) -> LocalCredentialCapabilities:
        """Revoke local credentials that current OIDC policy no longer permits."""
        capabilities = await self.capabilities_for(db, user=user)
        if not non_password_authentication_allowed(user):
            await self.revoke_all_local_credentials(db, user_id=user.id)
            return capabilities

        # Role changes are authoritative for existing key scopes too. Revoke,
        # rather than narrow, so a later role upgrade cannot resurrect authority
        # the credential once held.
        role_ceiling = allowed_api_key_scopes(user.role)
        active_keys = (
            await db.execute(
                select(ApiKey)
                .where(
                    cast(Any, ApiKey.user_id == user.id),
                    cast(Any, ApiKey.revoked_at == None),  # noqa: E711
                )
                .with_for_update()
            )
        ).scalars().all()
        now = datetime.now(timezone.utc)
        for api_key in active_keys:
            if normalize_api_key_scopes(api_key.scopes or []) - role_ceiling:
                api_key.revoked_at = now

        if capabilities.passkey_allowed and capabilities.api_key_allowed:
            return capabilities

        if not capabilities.api_key_allowed:
            await db.execute(
                update(ApiKey)
                .where(
                    cast(Any, ApiKey.user_id == user.id),
                    cast(Any, ApiKey.revoked_at == None),  # noqa: E711
                )
                .values(revoked_at=now)
            )
        if not capabilities.passkey_allowed:
            await db.execute(
                update(PasskeyCredential)
                .where(
                    cast(Any, PasskeyCredential.user_id == user.id),
                    cast(Any, PasskeyCredential.revoked_at == None),  # noqa: E711
                )
                .values(revoked_at=now, updated_at=now)
            )
        return capabilities

    async def reconcile_linked_users(self, db: AsyncSession) -> None:
        """Reconcile HUMAN accounts under their authorization transaction gate."""
        result = await db.execute(
            select(UserAccount).where(
                cast(Any, UserAccount.account_type == AccountType.HUMAN),
            )
        )
        candidates = sorted(
            result.scalars().all(),
            key=lambda candidate: candidate.id.int,
        )
        for candidate in candidates:
            initial_capabilities = await self.capabilities_for(db, user=candidate)
            if (
                initial_capabilities.password_login_allowed
                and initial_capabilities.passkey_allowed
                and initial_capabilities.api_key_allowed
            ):
                continue

            await acquire_authorization_lock(
                db,
                user_id=candidate.id,
                shared=False,
            )
            user = await db.get(
                UserAccount,
                candidate.id,
                populate_existing=True,
                with_for_update=True,
            )
            if user is None:
                continue

            capabilities = await self.revoke_impermissible_credentials(
                db,
                user=user,
            )
            local_access_denied = not (
                capabilities.password_login_allowed
                and capabilities.passkey_allowed
                and capabilities.api_key_allowed
            )
            if not local_access_denied:
                continue

            invalidated_at = datetime.now(timezone.utc)
            user.credentials_invalidated_at = invalidated_at
            user.updated_at = invalidated_at
            await db.execute(
                update(AuthSession)
                .where(
                    cast(Any, AuthSession.user_id == user.id),
                    cast(Any, AuthSession.revoked_at == None),  # noqa: E711
                )
                .values(
                    revoked_at=invalidated_at,
                    revoked_reason=SessionRevokedReason.ADMIN_FORCE,
                )
            )
            await db.execute(
                update(WebAuthnChallenge)
                .where(
                    cast(Any, WebAuthnChallenge.user_id == user.id),
                    cast(Any, WebAuthnChallenge.consumed_at == None),  # noqa: E711
                )
                .values(consumed_at=invalidated_at)
            )

            # Import lazily: the MCP service reads settings and therefore
            # intentionally depends on SettingsService in the opposite direction.
            from app.services.mcp_oauth_service import mcp_oauth_service

            await mcp_oauth_service.invalidate_user_grants(
                db,
                user_id=user.id,
                invalidated_at=invalidated_at,
            )


oidc_local_credential_policy = OIDCLocalCredentialPolicy()


__all__ = [
    "LocalCredentialCapabilities",
    "OIDCLocalCredentialPolicy",
    "oidc_local_credential_policy",
]
