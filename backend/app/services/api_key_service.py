"""
API Key service for programmatic authentication.

API keys are tied to user accounts (both human and NHI) and inherit
the permissions of that user. Keys are hashed using BLAKE2b before storage.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_opaque_token
from app.models.enums import UserStatus
from app.models.models import ApiKey, UserAccount
from app.services.audit_service import (
    AuditContext,
    AuditSessionFactory,
    get_audit_service,
    persist_api_key_auth_failure,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "tmi_"  # Tidemark Intercept
API_KEY_RANDOM_BYTES = 48  # 48 bytes = 64 chars in URL-safe base64
API_KEY_DISPLAY_PREFIX_LENGTH = 12  # "tmi_XXXXXXXX" for display


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


class UserInactiveError(Exception):
    """Raised when the user associated with an API key is not active."""


# ---------------------------------------------------------------------------
# API Key Service
# ---------------------------------------------------------------------------


class ApiKeyService:
    """Business logic for API key management and authentication."""

    def __init__(self, *, audit_session_factory: Optional[AuditSessionFactory] = None) -> None:
        self._audit_session_factory = audit_session_factory

    async def _persist_auth_failure(
        self,
        db: AsyncSession,
        *,
        reason: str,
        api_key_prefix: Optional[str],
        context: Optional[AuditContext],
    ) -> None:
        await persist_api_key_auth_failure(
            db,
            reason=reason,
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
        expires_at = self._require_future_expiration(expires_at)

        # Verify user exists and is active
        user = await db.get(UserAccount, user_id)
        if not user:
            raise ApiKeyUserNotFoundError(f"User {user_id} not found")

        # Generate key
        full_key, prefix, key_hash = self.generate_api_key()

        # Create API key record
        api_key = ApiKey(
            user_id=user_id,
            name=name,
            prefix=prefix,
            key_hash=key_hash,
            expires_at=expires_at,
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
        context: Optional[AuditContext] = None,
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
        # Extract prefix for logging
        prefix = raw_key[:API_KEY_DISPLAY_PREFIX_LENGTH] if len(raw_key) >= API_KEY_DISPLAY_PREFIX_LENGTH else raw_key

        # Hash the key
        key_hash = hash_opaque_token(raw_key)

        # Look up the key
        result = await db.execute(
            select(ApiKey)
            .options(selectinload(ApiKey.user))
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

        now = datetime.now(timezone.utc)

        # Check if revoked
        if api_key.revoked_at is not None:
            await self._persist_auth_failure(
                db,
                reason="key_revoked",
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise ApiKeyRevokedError()

        # Check if expired
        api_key.expires_at = self._normalize_expiration(api_key.expires_at)
        if api_key.expires_at <= now:
            await self._persist_auth_failure(
                db,
                reason="key_expired",
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise ApiKeyExpiredError()

        # Check user status
        if api_key.user is None or api_key.user.status != UserStatus.ACTIVE:
            await self._persist_auth_failure(
                db,
                reason="user_inactive",
                api_key_prefix=api_key.prefix,
                context=context,
            )
            raise UserInactiveError()

        # Update last_used_at
        api_key.last_used_at = now

        # Audit success
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
    "ApiKeyRevokedError",
    "UserInactiveError",
    "api_key_service",
    "API_KEY_PREFIX",
]
