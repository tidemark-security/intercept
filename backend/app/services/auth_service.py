from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import hashlib
import logging
import secrets
import time
from typing import Any, Optional, Tuple, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.enums import AccountType, SessionRevokedReason, UserRole, UserStatus
from app.models.models import AuthSession, UserAccount, PASSWORD_POLICY_REGEX
from app.services import AuditContext, AuthAuditService, PasswordHasher
from app.services.passkey_service import passkey_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes & error types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RequestMetadata:
    """Minimal request context forwarded into the service layer."""

    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_audit_context(self) -> AuditContext:
        return AuditContext(
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            correlation_id=self.correlation_id,
        )


@dataclass(slots=True)
class LoginResult:
    """Successful login payload returned from the service layer."""

    user: UserAccount
    session: AuthSession
    session_token: str


class InvalidCredentialsError(Exception):
    """Raised when username/password verification fails."""


class AccountLockedError(Exception):
    """Raised when an account is locked out due to repeated failures."""

    def __init__(self, *, lockout_expires_at: datetime) -> None:
        super().__init__("Account is locked")
        self.lockout_expires_at = lockout_expires_at


class AccountDisabledError(Exception):
    """Raised when a disabled account attempts to authenticate."""


class NHIPasswordLoginError(Exception):
    """Raised when a non-human identity account attempts password authentication."""


class SessionNotFoundError(Exception):
    """Raised when a session token cannot be resolved to an active session."""


class PasswordPolicyViolation(Exception):
    """Raised when a password update request fails validation."""


class PasswordLoginDisabledError(Exception):
    """Raised when password login is disabled because the user has active passkeys."""


# ---------------------------------------------------------------------------
# Sliding window rate limiter (per username/IP)
# ---------------------------------------------------------------------------


class SlidingWindowRateLimiter:
    """Naive in-memory sliding window limiter suitable for single-node dev use."""

    def __init__(self, *, capacity: int, window_seconds: int) -> None:
        self._capacity = capacity
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> Tuple[bool, Optional[int]]:
        """Return (allowed, retry_after_seconds)."""

        now = time.monotonic()
        async with self._lock:
            queue = self._hits.setdefault(key, deque())
            window_start = now - self._window

            while queue and queue[0] < window_start:
                queue.popleft()

            if len(queue) >= self._capacity:
                retry_after = max(1, int(self._window - (now - queue[0])))
                return False, retry_after

            queue.append(now)
            if len(queue) == 1:
                # Opportunistic pruning of stale keys
                self._prune(now)
            return True, None

    def _prune(self, now: float) -> None:
        stale_cutoff = now - (self._window * 2)
        stale_keys = [key for key, records in self._hits.items() if records and records[-1] < stale_cutoff]
        for key in stale_keys:
            self._hits.pop(key, None)


# ---------------------------------------------------------------------------
# Core authentication service
# ---------------------------------------------------------------------------


class AuthService:
    """Business logic for username/password authentication and sessions."""

    def __init__(
        self,
        *,
        password_hasher: Optional[PasswordHasher] = None,
        audit_service: Optional[AuthAuditService] = None,
    ) -> None:
        self._password_hasher = password_hasher or PasswordHasher(settings.build_argon2_parameters())
        self._audit = audit_service or AuthAuditService()
        self._lockout_threshold = settings.login_lockout_threshold
        self._lockout_duration = settings.login_lockout_duration
        self._idle_timeout = settings.session_idle_timeout
        self._absolute_timeout = settings.session_absolute_timeout
        self._rate_limiter = SlidingWindowRateLimiter(
            capacity=settings.login_rate_limit_attempts,
            window_seconds=settings.login_rate_limit_window_seconds,
        )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def check_rate_limit(self, key: str) -> Tuple[bool, Optional[int]]:
        allowed, retry_after = await self._rate_limiter.check(key)
        if not allowed:
            logger.warning("Login rate limit exceeded", extra={"auth": {"key": key, "retry_after": retry_after}})
        return allowed, retry_after

    # ------------------------------------------------------------------
    # Authentication flows
    # ------------------------------------------------------------------

    async def login(
        self,
        db: AsyncSession,
        *,
        username: str,
        password: str,
        metadata: RequestMetadata,
    ) -> LoginResult:
        normalized_username = username.strip().lower()
        now = datetime.now(timezone.utc)

        username_match = cast(Any, UserAccount.username == normalized_username)
        result = await db.execute(select(UserAccount).where(username_match))
        user = result.scalar_one_or_none()

        if user is None:
            self._audit.login_failure(
                username=normalized_username,
                role=None,
                reason="invalid_credentials",
                attempts_remaining=None,
                context=metadata.to_audit_context(),
            )
            raise InvalidCredentialsError()

        # Block NHI accounts from password authentication
        if user.account_type == AccountType.NHI:
            self._audit.login_failure(
                username=normalized_username,
                role=user.role,
                reason="nhi_password_login_blocked",
                attempts_remaining=None,
                context=metadata.to_audit_context(),
            )
            raise NHIPasswordLoginError()

        # Reset lockout if expired
        if user.lockout_expires_at and user.lockout_expires_at <= now:
            user.lockout_expires_at = None
            user.failed_login_attempts = 0
            user.status = UserStatus.ACTIVE

        if user.status == UserStatus.DISABLED:
            self._audit.login_failure(
                username=normalized_username,
                role=user.role,
                reason="account_disabled",
                attempts_remaining=None,
                context=metadata.to_audit_context(),
            )
            raise AccountDisabledError()

        if user.lockout_expires_at and user.lockout_expires_at > now:
            self._audit.login_failure(
                username=normalized_username,
                role=user.role,
                reason="lockout_active",
                attempts_remaining=0,
                context=metadata.to_audit_context(),
            )
            raise AccountLockedError(lockout_expires_at=user.lockout_expires_at)

        has_active_passkeys = await passkey_service.user_has_active_passkeys(db, user_id=user.id)
        if has_active_passkeys:
            self._audit.login_failure(
                username=normalized_username,
                role=user.role,
                reason="password_login_disabled_passkey_registered",
                attempts_remaining=None,
                context=metadata.to_audit_context(),
            )
            raise PasswordLoginDisabledError()

        if not self._password_hasher.verify(user.password_hash, password):
            user.failed_login_attempts += 1
            user.updated_at = now

            attempts_remaining = max(0, self._lockout_threshold - user.failed_login_attempts)
            if user.failed_login_attempts >= self._lockout_threshold:
                user.status = UserStatus.LOCKED
                user.lockout_expires_at = now + self._lockout_duration
                self._audit.account_locked(
                    user_id=user.id,
                    username=user.username,
                    role=user.role,
                    lockout_expires_at=user.lockout_expires_at,
                    context=metadata.to_audit_context(),
                )
                self._audit.login_failure(
                    username=normalized_username,
                    role=user.role,
                    reason="lockout",
                    attempts_remaining=0,
                    context=metadata.to_audit_context(),
                )
                raise AccountLockedError(lockout_expires_at=user.lockout_expires_at)

            self._audit.login_failure(
                username=normalized_username,
                role=user.role,
                reason="invalid_credentials",
                attempts_remaining=attempts_remaining,
                context=metadata.to_audit_context(),
            )
            raise InvalidCredentialsError()

        # Successful authentication
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.status = UserStatus.ACTIVE
        user.last_login_at = now
        user.updated_at = now

        return await self.create_session_for_user(db, user=user, metadata=metadata)

    async def create_session_for_user(
        self,
        db: AsyncSession,
        *,
        user: UserAccount,
        metadata: RequestMetadata,
    ) -> LoginResult:
        now = datetime.now(timezone.utc)
        session_token = secrets.token_urlsafe(48)
        session_token_hash = self._hash_session_token(session_token)
        session_id = uuid4()

        expires_at = min(now + self._absolute_timeout, now + self._idle_timeout)

        session = AuthSession(
            id=session_id,
            session_token_hash=session_token_hash,
            user_id=user.id,
            issued_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            ip_address=metadata.ip_address,
            user_agent=metadata.user_agent,
            correlation_id=metadata.correlation_id,
        )
        db.add(session)
        await db.flush()

        self._audit.login_success(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_id=session.id,
            issued_at=now,
            expires_at=session.expires_at,
            context=metadata.to_audit_context(),
        )

        return LoginResult(user=user, session=session, session_token=session_token)

    async def logout(
        self,
        db: AsyncSession,
        *,
        session_token: str,
        metadata: RequestMetadata,
        reason: SessionRevokedReason = SessionRevokedReason.USER_LOGOUT,
    ) -> AuthSession:
        session = await self._resolve_active_session(db, session_token)
        now = datetime.now(timezone.utc)

        session.revoked_at = now
        session.revoked_reason = reason
        session.last_seen_at = now

        if session.user is None:
            session.user = await db.get(UserAccount, session.user_id)

        if session.user is not None:
            self._audit.logout(
                user_id=session.user.id,
                session_id=session.id,
                reason=reason,
                context=metadata.to_audit_context(),
            )

        return session

    async def validate_session(
        self,
        db: AsyncSession,
        *,
        session_token: str,
    ) -> LoginResult:
        """
        Validate an existing session token and return user/session details.
        
        This is used to check if a session is still active and refresh
        the session data on app load or page refresh.
        
        Raises:
            SessionNotFoundError: If the session is invalid, expired, or revoked.
        """
        session = await self._resolve_active_session(db, session_token)
        
        # Update last seen timestamp
        now = datetime.now(timezone.utc)
        session.last_seen_at = now
        
        # Load user if not already loaded
        user = session.user
        if user is None:
            user = await db.get(UserAccount, session.user_id)
        if user is None:
            raise SessionNotFoundError()
        
        return LoginResult(user=user, session=session, session_token=session_token)

    async def change_password(
        self,
        db: AsyncSession,
        *,
        session_token: str,
        current_password: str,
        new_password: str,
        metadata: RequestMetadata,
    ) -> None:
        session = await self._resolve_active_session(db, session_token)
        user = session.user
        if user is None:
            user = await db.get(UserAccount, session.user_id)
        if user is None:
            raise SessionNotFoundError()

        if not self._password_hasher.verify(user.password_hash, current_password):
            raise InvalidCredentialsError()

        candidate = new_password.strip()
        if not candidate or len(candidate) < 12:
            raise PasswordPolicyViolation("Password does not meet minimum length requirements")
        if not PASSWORD_POLICY_REGEX.match(candidate):
            raise PasswordPolicyViolation(
                "Password must include upper, lower, number, and special character"
            )

        hashed = self._password_hasher.hash(candidate)
        now = datetime.now(timezone.utc)

        was_forced = user.must_change_password

        user.password_hash = hashed
        user.password_updated_at = now
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.updated_at = now

        session.last_seen_at = now

        # Revoke all other active sessions for this user except current one
        user_match = cast(Any, AuthSession.user_id == user.id)
        not_current = cast(Any, AuthSession.id != session.id)
        result = await db.execute(select(AuthSession).where(user_match, not_current))
        other_sessions = result.scalars().all()
        for other in other_sessions:
            if other.revoked_at is None:
                other.revoked_at = now
                other.revoked_reason = SessionRevokedReason.RESET_REQUIRED

        await db.commit()

        # Audit log and metrics
        self._audit.password_changed(
            user_id=user.id,
            username=user.username,
            was_forced=was_forced,
            context=metadata.to_audit_context(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_active_session(self, db: AsyncSession, session_token: str) -> AuthSession:
        hashed = self._hash_session_token(session_token)

        token_match = cast(Any, AuthSession.session_token_hash == hashed)
        # Eagerly load the user relationship to avoid lazy loading in async context
        result = await db.execute(
            select(AuthSession)
            .options(selectinload(AuthSession.user))  # type: ignore[arg-type]
            .where(token_match)
        )
        session = result.scalar_one_or_none()

        if session is None:
            raise SessionNotFoundError()

        now = datetime.now(timezone.utc)

        if session.revoked_at is not None:
            raise SessionNotFoundError()
        if session.expires_at <= now:
            session.revoked_at = now
            session.revoked_reason = SessionRevokedReason.SESSION_TIMEOUT
            raise SessionNotFoundError()

        # User should be loaded via selectinload above
        if session.user is None or session.user.status != UserStatus.ACTIVE:
            raise SessionNotFoundError()

        session.last_seen_at = now
        return session

    @staticmethod
    def _hash_session_token(token: str) -> str:
        return hashlib.blake2b(token.encode("utf-8"), digest_size=32).hexdigest()


auth_service = AuthService()

__all__ = [
    "AuthService",
    "LoginResult",
    "RequestMetadata",
    "InvalidCredentialsError",
    "AccountLockedError",
    "AccountDisabledError",
    "NHIPasswordLoginError",
    "SessionNotFoundError",
    "PasswordPolicyViolation",
    "PasswordLoginDisabledError",
    "auth_service",
]
