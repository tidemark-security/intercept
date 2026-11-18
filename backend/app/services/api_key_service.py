"""
API Key service for programmatic authentication.

API keys are tied to user accounts (both human and NHI) and inherit
the permissions of that user. Keys are hashed using BLAKE2b before storage.
"""
from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.account_authentication import non_password_authentication_allowed
from app.core.api_key_scopes import (
    ALL_API_KEY_SCOPES,
    allowed_api_key_scopes,
    normalize_api_key_scopes,
)
from app.core.authorization_lock import (
    AuthorizationConcurrencyError,
    acquire_authorization_lock,
)
from app.core.authentication_activity import defer_api_key_activity
from app.core.security import hash_opaque_token
from app.core.settings_registry import get_local
from app.models.models import ApiKey, UserAccount
from app.services.audit_service import (
    AuditContext,
    AuditSessionFactory,
    get_audit_service,
)
from app.services.api_key_failure_sampling_service import (
    persist_sampled_api_key_auth_failure,
)
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.oidc_local_credential_policy import oidc_local_credential_policy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "tmi_"  # Tidemark Intercept
API_KEY_RANDOM_BYTES = 48  # 48 bytes = 64 chars in URL-safe base64
API_KEY_DISPLAY_PREFIX_LENGTH = 12  # "tmi_XXXXXXXX" for display
API_KEY_MAX_LENGTH = 256


# ---------------------------------------------------------------------------
# Data classes & error types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ApiKeyResult:
    """Result of API key validation."""
    user: UserAccount
    api_key: ApiKey


class ApiKeyNotFoundError(Exception):
    """Raised when an API key cannot be found or is invalid."""


class ApiKeyExpiredError(Exception):
    """Raised when an API key has expired."""


class ApiKeyExpirationError(ValueError):
    """Raised when a new API key expiration is not in the future."""


class ApiKeyUserNotFoundError(ValueError):
    """Raised when an API key is requested for a missing user."""


class ApiKeyRevokedError(Exception):
    """Raised when an API key has been revoked."""


class ApiKeyScopeValidationError(ValueError):
    """Raised when requested scopes are invalid for the owner account."""


class ApiKeyScopeError(Exception):
    """Raised when a valid API key lacks a scope required by the request."""

    def __init__(self, missing_scopes: Iterable[str]) -> None:
        self.missing_scopes = frozenset(missing_scopes)
        super().__init__(
            "API key lacks required scope(s): "
            + ", ".join(sorted(self.missing_scopes))
        )


class ApiKeyPolicyError(Exception):
    """Raised when OIDC policy forbids local API keys for the owner."""


class UserInactiveError(Exception):
    """Raised when the user associated with an API key is not active."""


# ---------------------------------------------------------------------------
# API Key Service
# ---------------------------------------------------------------------------


class ApiKeyService:
    """Business logic for API key management and authentication."""

    def __init__(
        self,
        *,
        audit_session_factory: Optional[AuditSessionFactory] = None,
        revocation_session_factory: Optional[AuditSessionFactory] = None,
        max_lifetime_days: Optional[int] = None,
    ) -> None:
        self._audit_session_factory = audit_session_factory
        self._revocation_session_factory = revocation_session_factory
        configured_max = (
            max_lifetime_days
            if max_lifetime_days is not None
            else int(get_local("auth.api_keys.max_lifetime_days"))
        )
        if configured_max <= 0:
            raise ValueError("API key maximum lifetime must be greater than zero")
        self._max_lifetime_days = configured_max

    async def _persist_auth_failure(
        self,
        db: AsyncSession,
        *,
        reason: str,
        api_key_id: Optional[UUID] = None,
        api_key_prefix: Optional[str],
        context: Optional[AuditContext],
    ) -> None:
        await persist_sampled_api_key_auth_failure(
            db,
            reason=reason,
            api_key_id=api_key_id,
            api_key_prefix=api_key_prefix,
            context=context,
            session_factory=self._audit_session_factory,
        )

    @staticmethod
    def _normalize_expiration(expires_at: datetime) -> datetime:
        """Return an expiration timestamp as an aware UTC datetime."""
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            return expires_at.replace(tzinfo=timezone.utc)
        return expires_at.astimezone(timezone.utc)

    @classmethod
    def _require_future_expiration(cls, expires_at: datetime) -> datetime:
        """Normalize an expiration timestamp and require it to be future-dated."""
        normalized = cls._normalize_expiration(expires_at)
        if normalized <= datetime.now(timezone.utc):
            raise ApiKeyExpirationError("Expiration date must be in the future")
        return normalized

    def _require_bounded_expiration(self, expires_at: datetime) -> datetime:
        normalized = self._require_future_expiration(expires_at)
        latest_allowed = datetime.now(timezone.utc) + timedelta(
            days=self._max_lifetime_days
        )
        if normalized > latest_allowed:
            raise ApiKeyExpirationError(
                f"Expiration date cannot exceed {self._max_lifetime_days} days"
            )
        return normalized

    @staticmethod
    def _resolve_scopes(
        *,
        user: UserAccount,
        scopes: Optional[Iterable[str]],
    ) -> list[str]:
        role_ceiling = allowed_api_key_scopes(user.role)
        normalized = role_ceiling if scopes is None else normalize_api_key_scopes(scopes)
        if not normalized:
            raise ApiKeyScopeValidationError("At least one API key scope is required")

        unknown = normalized - ALL_API_KEY_SCOPES
        if unknown:
            raise ApiKeyScopeValidationError(
                "Unknown API key scope(s): " + ", ".join(sorted(unknown))
            )

        disallowed = normalized - role_ceiling
        if disallowed:
            raise ApiKeyScopeValidationError(
                "Scope(s) not permitted for the target account role: "
                + ", ".join(sorted(disallowed))
            )
        return sorted(normalized)

    async def _persist_policy_revocation(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
    ) -> None:
        """Persist policy revocation independently of request rollback."""
        session_factory = self._revocation_session_factory
        if session_factory is None:
            bind = getattr(db, "bind", None)
            if bind is None:
                return
            session_factory = async_sessionmaker(
                bind=bind,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        async with session_factory() as revocation_db:
            await oidc_local_credential_policy.revoke_all_local_credentials(
                revocation_db,
                user_id=user_id,
            )
            await revocation_db.commit()

    async def _persist_api_key_revocation(
        self,
        db: AsyncSession,
        *,
        api_key_id: UUID,
    ) -> None:
        """Permanently revoke one key independently of request rollback."""
        session_factory = self._revocation_session_factory
        if session_factory is None:
            bind = getattr(db, "bind", None)
            if bind is None:
                return
            session_factory = async_sessionmaker(
                bind=bind,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        async with session_factory() as revocation_db:
            await revocation_db.execute(
                update(ApiKey)
                .where(
                    cast(Any, ApiKey.id == api_key_id),
                    cast(Any, ApiKey.revoked_at == None),  # noqa: E711
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await revocation_db.commit()

    # ------------------------------------------------------------------
    # Key generation and hashing
    # ------------------------------------------------------------------

    @staticmethod
    def generate_api_key() -> tuple[str, str, str]:
        """
        Generate a new API key.
        
        Returns:
            Tuple of (full_key, prefix, key_hash)
        """
        random_part = secrets.token_urlsafe(API_KEY_RANDOM_BYTES)
        full_key = f"{API_KEY_PREFIX}{random_part}"
        prefix = full_key[:API_KEY_DISPLAY_PREFIX_LENGTH]
        key_hash = hash_opaque_token(full_key)
        return full_key, prefix, key_hash

    # ------------------------------------------------------------------
    # API Key CRUD operations
    # ------------------------------------------------------------------

    async def create_api_key(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        name: str,
        expires_at: datetime,
        scopes: Optional[Iterable[str]] = None,
        created_by_user_id: Optional[UUID] = None,
        context: Optional[AuditContext] = None,
    ) -> tuple[ApiKey, str]:
        """
        Create a new API key for a user.
        
        Args:
            db: Database session
            user_id: ID of the user who will own this key
            name: User-defined name for the key
            expires_at: Expiration datetime (required)
            created_by_user_id: ID of admin creating this key (for NHI accounts)
            context: Audit context
            
        Returns:
            Tuple of (ApiKey object, raw_key) - raw_key is only returned once
        """
        expires_at = self._require_bounded_expiration(expires_at)

        # Verify user exists and is active
        user = await db.get(
            UserAccount,
            user_id,
            populate_existing=True,
            with_for_update=True,
        )
        if not user:
            raise ApiKeyUserNotFoundError(f"User {user_id} not found")
        if not non_password_authentication_allowed(user):
            raise ApiKeyPolicyError(
                "API keys can only be created for an active account"
            )

        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )
        if not capabilities.api_key_allowed:
            raise ApiKeyPolicyError(
                "Local API keys are disabled for this OIDC-linked account"
            )

        resolved_scopes = self._resolve_scopes(user=user, scopes=scopes)

        # Generate key
        full_key, prefix, key_hash = self.generate_api_key()

        # Create API key record
        api_key = ApiKey(
            user_id=user_id,
            name=name,
            prefix=prefix,
            key_hash=key_hash,
            expires_at=expires_at,
            scopes=resolved_scopes,
        )
        db.add(api_key)
        await db.flush()

        # Audit log
        await get_audit_service(db).api_key_created(
            user_id=user_id,
            username=user.username,
            api_key_id=api_key.id,
            api_key_name=name,
            api_key_prefix=prefix,
            expires_at=expires_at,
            created_by_user_id=created_by_user_id,
            context=context,
        )

        return api_key, full_key

    async def revoke_api_key(
        self,
        db: AsyncSession,
        *,
        api_key_id: UUID,
        revoked_by_user_id: Optional[UUID] = None,
        context: Optional[AuditContext] = None,
    ) -> ApiKey:
        """
        Revoke an API key.
        
        Args:
            db: Database session
            api_key_id: ID of the API key to revoke
            revoked_by_user_id: ID of user performing the revocation
            context: Audit context
            
        Returns:
            The revoked ApiKey object
        """
        result = await db.execute(
            select(ApiKey)
            .options(selectinload(ApiKey.user))
            .where(cast(Any, ApiKey.id == api_key_id))
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise ApiKeyNotFoundError()

        if api_key.revoked_at is not None:
            raise ApiKeyRevokedError()

        now = datetime.now(timezone.utc)
        api_key.revoked_at = now

        # Audit log
        if api_key.user:
            await get_audit_service(db).api_key_revoked(
                user_id=api_key.user_id,
                username=api_key.user.username,
                api_key_id=api_key.id,
                api_key_name=api_key.name,
                api_key_prefix=api_key.prefix,
                revoked_by_user_id=revoked_by_user_id,
                context=context,
            )

        return api_key

    async def list_user_api_keys(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        include_revoked: bool = False,
    ) -> list[ApiKey]:
        """
        List API keys for a user.
        
        Args:
            db: Database session
            user_id: ID of the user
            include_revoked: Whether to include revoked keys
            
        Returns:
            List of ApiKey objects (never includes the actual key value)
        """
        query = select(ApiKey).where(cast(Any, ApiKey.user_id == user_id))
        
        if not include_revoked:
            query = query.where(cast(Any, ApiKey.revoked_at == None))  # noqa: E711
        
        query = query.order_by(cast(Any, ApiKey.created_at).desc())
        
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_api_key(
        self,
        db: AsyncSession,
        *,
        api_key_id: UUID,
    ) -> Optional[ApiKey]:
        """
        Get an API key by ID.
        
        Args:
            db: Database session
            api_key_id: ID of the API key
            
        Returns:
            ApiKey object or None if not found
        """
        result = await db.execute(
            select(ApiKey)
            .options(selectinload(ApiKey.user))
            .where(cast(Any, ApiKey.id == api_key_id))
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # API Key Authentication
    # ------------------------------------------------------------------

    async def validate_api_key(
        self,
        db: AsyncSession,
        *,
        raw_key: str,
        required_scopes: Optional[Iterable[str]] = None,
        context: Optional[AuditContext] = None,
        audit_success: bool = True,
        skip_locked: bool = False,
        shared_lock: bool = False,
    ) -> ApiKeyResult:
        """
        Validate an API key and return the associated user.
        
        Args:
            db: Database session
            raw_key: The full API key to validate
            context: Audit context
            
        Returns:
            ApiKeyResult with user and api_key
            
        Raises:
            ApiKeyNotFoundError: Key not found
            ApiKeyExpiredError: Key has expired
            ApiKeyRevokedError: Key has been revoked
            UserInactiveError: Associated user is not active
        """
        # Reject attacker-sized material before hashing or querying. Generated
        # Intercept API keys are currently 68 characters; the larger ceiling
        # leaves room for compatible legacy formats without unbounded work.
        if len(raw_key) > API_KEY_MAX_LENGTH:
            await self._persist_auth_failure(
                db,
                reason="key_not_found",
                api_key_prefix=None,
                context=context,
            )
            raise ApiKeyNotFoundError()

        # Extract prefix for logging
        prefix = raw_key[:API_KEY_DISPLAY_PREFIX_LENGTH] if len(raw_key) >= API_KEY_DISPLAY_PREFIX_LENGTH else raw_key

        # Hash the key
        key_hash = hash_opaque_token(raw_key)

        # Look up the key
        result = await db.execute(
            select(ApiKey)
            .where(cast(Any, ApiKey.key_hash == key_hash))
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            await self._persist_auth_failure(
                db,
                reason="key_not_found",
                api_key_prefix=prefix,
                context=context,
            )
            raise ApiKeyNotFoundError()

        api_key_id = api_key.id
        api_key_user_id = api_key.user_id
        api_key_prefix = api_key.prefix

        authorization_acquired = await acquire_authorization_lock(
            db,
            user_id=api_key_user_id,
            shared=True,
            wait=not skip_locked,
        )
        if not authorization_acquired:
            raise AuthorizationConcurrencyError()

        # Serialize successful authentication with status/role/cutoff changes
        # and explicit key revocation. Re-read the key while locked after the
        # user lock so a pre-lock ORM snapshot can never authorize a request.
        # Credential issuance and administrative/OIDC reconciliation use the
        # same user-first lock order, so no request can authenticate from a
        # stale role after a downgrade transaction completes.
        user = await db.get(
            UserAccount,
            api_key_user_id,
            populate_existing=True,
            with_for_update={
                "read": shared_lock,
                "skip_locked": skip_locked,
            },
        )
        locked_key_result = await db.execute(
            select(ApiKey)
            .where(cast(Any, ApiKey.id == api_key_id))
            .with_for_update(
                read=shared_lock,
                skip_locked=skip_locked,
            )
            .execution_options(populate_existing=True)
        )
        api_key = locked_key_result.scalar_one_or_none()
        if api_key is None:
            await self._persist_auth_failure(
                db,
                reason="key_not_found",
                api_key_id=api_key_id,
                api_key_prefix=api_key_prefix,
                context=context,
            )
            raise ApiKeyNotFoundError()
        api_key.user = user

        now = datetime.now(timezone.utc)

        # Check the locked, freshly reloaded credential state.
        if api_key.revoked_at is not None:
            await self._persist_auth_failure(
                db,
                reason="key_revoked",
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise ApiKeyRevokedError()

        normalized_expires_at = self._normalize_expiration(api_key.expires_at)
        if not shared_lock:
            api_key.expires_at = normalized_expires_at
        created_at = self._normalize_expiration(api_key.created_at)
        effective_expires_at = min(
            normalized_expires_at,
            created_at + timedelta(days=self._max_lifetime_days),
        )
        if effective_expires_at <= now:
            await self._persist_auth_failure(
                db,
                reason="key_expired",
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise ApiKeyExpiredError()

        # Check user status
        if api_key.user is None or not non_password_authentication_allowed(
            api_key.user
        ):
            await self._persist_auth_failure(
                db,
                reason="user_inactive",
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise UserInactiveError()

        if not credential_was_issued_after_cutoff(
            api_key.user,
            issued_at=api_key.created_at,
        ):
            user_id = api_key.user.id
            await self._persist_auth_failure(
                db,
                reason="credential_invalidated",
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )
            if not shared_lock:
                await self._persist_policy_revocation(db, user_id=user_id)
            raise ApiKeyRevokedError()

        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=api_key.user,
        )
        if not capabilities.api_key_allowed:
            user_id = api_key.user.id
            api_key_prefix = api_key.prefix
            await self._persist_auth_failure(
                db,
                reason="local_credential_policy_denied",
                api_key_id=api_key.id,
                api_key_prefix=api_key_prefix,
                context=context,
            )
            if not shared_lock:
                await self._persist_policy_revocation(
                    db,
                    user_id=user_id,
                )
            raise ApiKeyPolicyError()

        stored_scopes = normalize_api_key_scopes(api_key.scopes or [])
        disallowed_scopes = stored_scopes - allowed_api_key_scopes(api_key.user.role)
        if disallowed_scopes:
            api_key_id = api_key.id
            await self._persist_auth_failure(
                db,
                reason="scope_exceeds_role_ceiling",
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )
            if not shared_lock:
                await self._persist_api_key_revocation(
                    db,
                    api_key_id=api_key_id,
                )
            raise ApiKeyRevokedError()

        required = normalize_api_key_scopes(required_scopes or ())
        missing_scopes = required - set(api_key.scopes or [])
        if missing_scopes:
            await self._persist_auth_failure(
                db,
                reason="insufficient_scope",
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise ApiKeyScopeError(missing_scopes)

        # Shared read authentication must not dirty the locked credential row:
        # concurrent lock upgrades at commit can deadlock one another. Success
        # audits still provide forensic usage telemetry for read-only calls.
        if shared_lock:
            defer_api_key_activity(
                db,
                api_key_id=api_key.id,
                observed_at=now,
            )
        else:
            api_key.last_used_at = now

        # MCP revalidates the same key at its tool execution boundary. The
        # outer verifier already records the authentication success, so that
        # lock-only revalidation suppresses a duplicate success event.
        if audit_success:
            await get_audit_service(db).api_key_auth_success(
                user_id=api_key.user.id,
                username=api_key.user.username,
                api_key_id=api_key.id,
                api_key_prefix=api_key.prefix,
                context=context,
            )

        return ApiKeyResult(user=api_key.user, api_key=api_key)


# Module-level singleton
api_key_service = ApiKeyService()


__all__ = [
    "ApiKeyService",
    "ApiKeyResult",
    "ApiKeyNotFoundError",
    "ApiKeyExpiredError",
    "ApiKeyExpirationError",
    "ApiKeyPolicyError",
    "ApiKeyRevokedError",
    "ApiKeyScopeError",
    "ApiKeyScopeValidationError",
    "ApiKeyUserNotFoundError",
    "UserInactiveError",
    "api_key_service",
    "API_KEY_PREFIX",
    "API_KEY_MAX_LENGTH",
]
