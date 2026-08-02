from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import logging
import secrets
import time
from typing import Any, Optional, Tuple, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings_registry import get_local
from app.core.security import hash_opaque_token
from app.core.password_policy import PasswordPolicyViolation, validate_password_policy
from app.models.enums import AccountType, SessionRevokedReason, UserStatus
from app.models.models import AuthSession, UserAccount
from app.services import AuditContext, PasswordHasher, get_audit_service
from app.services.passkey_service import passkey_service
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes & error types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LoginResult:
    """Successful login payload returned from the service layer."""

    user: UserAccount
    session: AuthSession
    session_token: str


class InvalidCredentialsError(Exception):
    """Raised when username/password verification fails."""


class AccountLockedError(Exception):
    """Raised when an account is administratively or temporarily locked."""

    def __init__(self, *, lockout_expires_at: datetime | None) -> None:
        super().__init__("Account is locked")
        self.lockout_expires_at = lockout_expires_at


class AccountDisabledError(Exception):
    """Raised when a disabled account attempts to authenticate."""


class NHIPasswordLoginError(Exception):
    """Raised when a non-human identity account attempts password authentication."""


class SessionNotFoundError(Exception):
    """Raised when a session token cannot be resolved to an active session."""


class PasswordLoginDisabledError(Exception):
    """Raised when password login is disabled because the user has active passkeys."""


class PasswordChangeRequiredError(Exception):
    """Raised when a forced password change gates ordinary authenticated access."""


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
    ) -> None:
        # Argon2 params are local_only (changing breaks existing hashes).
        self._password_hasher = password_hasher or PasswordHasher.from_local_settings()
        self._dummy_password_hash = self._password_hasher.hash("InvalidCredentialsDummyPassword123!")
        # Session timeouts are local_only (read per-request from frozen values)
        self._idle_timeout = timedelta(hours=get_local("auth.session.idle_timeout_hours"))
        self._absolute_timeout = timedelta(hours=get_local("auth.session.absolute_timeout_hours"))
        # Login protection settings are hot-swappable — read per-call via
        # _get_login_settings().  We keep a default rate limiter that is
        # rebuilt when settings change.
        rate_limit_capacity = int(get_local("auth.login.rate_limit_attempts"))
        rate_limit_window = int(get_local("auth.login.rate_limit_window_seconds"))
        self._rate_limiter_config = (rate_limit_capacity, rate_limit_window)
        self._rate_limiter = SlidingWindowRateLimiter(
            capacity=rate_limit_capacity,
            window_seconds=rate_limit_window,
        )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def check_rate_limit(
        self,
        db: AsyncSession,
        key: str,
    ) -> Tuple[bool, Optional[int]]:
        config = await self._get_rate_limit_settings(db)
        if config != self._rate_limiter_config:
            self._rate_limiter_config = config
            self._rate_limiter = SlidingWindowRateLimiter(
                capacity=config[0],
                window_seconds=config[1],
            )

        allowed, retry_after = await self._rate_limiter.check(key)
        if not allowed:
            retry_after = retry_after or config[1]
            logger.warning("Login rate limit exceeded", extra={"auth": {"key": key, "retry_after": retry_after}})
        return allowed, retry_after

    async def _get_rate_limit_settings(self, db: AsyncSession) -> tuple[int, int]:
        svc = SettingsService(db)  # type: ignore[arg-type]
        capacity = await svc.get("auth.login.rate_limit_attempts", default=10)
        window_seconds = await svc.get("auth.login.rate_limit_window_seconds", default=60)
        return int(capacity), int(window_seconds)

    async def _get_login_settings(self, db: AsyncSession) -> tuple[int, timedelta]:
        """Read hot-swappable login protection settings from DB.

        Returns ``(lockout_threshold, lockout_duration)``.
        """
        svc = SettingsService(db)  # type: ignore[arg-type]
        threshold = await svc.get("auth.login.lockout_threshold", default=5)
        duration_minutes = await svc.get("auth.login.lockout_duration_minutes", default=15)
        return int(threshold), timedelta(minutes=int(duration_minutes))

    async def _is_oidc_password_login_enforced(self, db: AsyncSession) -> bool:
        svc = SettingsService(db)  # type: ignore[arg-type]
        return bool(await svc.get("oidc.enabled", default=False))

    async def _audit_login_failure(
        self,
        db: AsyncSession,
        *,
        username: str,
        user: UserAccount | None,
        reason: str,
        attempts_remaining: int | None,
        metadata: AuditContext,
    ) -> None:
        """Record one failed-login outcome through the shared audit shape."""
        await get_audit_service(db).login_failure(
            username=username,
            role=user.role if user is not None else None,
            reason=reason,
            attempts_remaining=attempts_remaining,
            context=metadata,
        )

    # ------------------------------------------------------------------
    # Authentication flows
    # ------------------------------------------------------------------

    async def login(
        self,
        db: AsyncSession,
        *,
        username: str,
        password: str,
        metadata: AuditContext,
    ) -> LoginResult:
        normalized_username = username.strip().lower()
        now = datetime.now(timezone.utc)

        username_match = cast(Any, UserAccount.username == normalized_username)
        result = await db.execute(select(UserAccount).where(username_match).with_for_update())
        user = result.scalar_one_or_none()

        if user is None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, self._password_hasher.verify, self._dummy_password_hash, password
            )
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=None,
                reason="invalid_credentials",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise InvalidCredentialsError()

        # Block NHI accounts from password authentication
        if user.account_type == AccountType.NHI:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="nhi_password_login_blocked",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise NHIPasswordLoginError()

        if user.status == UserStatus.DISABLED:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="account_disabled",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise AccountDisabledError()

        # An administrator-controlled lock has no expiry. Only temporary
        # brute-force locks carry a lockout_expires_at value and may clear
        # themselves after that timestamp passes.
        if user.status == UserStatus.LOCKED and user.lockout_expires_at is None:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="account_locked",
                attempts_remaining=0,
                metadata=metadata,
            )
            raise AccountLockedError(lockout_expires_at=None)

        # Reset lockout if expired
        if user.lockout_expires_at and user.lockout_expires_at <= now:
            user.lockout_expires_at = None
            user.failed_login_attempts = 0
            if user.status == UserStatus.LOCKED:
                user.status = UserStatus.ACTIVE

        if user.lockout_expires_at and user.lockout_expires_at > now:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="lockout_active",
                attempts_remaining=0,
                metadata=metadata,
            )
            raise AccountLockedError(lockout_expires_at=user.lockout_expires_at)

        if await self._is_oidc_password_login_enforced(db):
            from app.services.oidc_service import oidc_service

            if not await oidc_service.is_password_login_allowed(db, user=user):
                await self._audit_login_failure(
                    db,
                    username=normalized_username,
                    user=user,
                    reason="oidc_password_login_blocked",
                    attempts_remaining=None,
                    metadata=metadata,
                )
                raise InvalidCredentialsError()

        has_active_passkeys = await passkey_service.user_has_active_passkeys(db, user_id=user.id)
        if has_active_passkeys:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="password_login_disabled_passkey_registered",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise PasswordLoginDisabledError()

        if not user.password_hash:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="password_unavailable",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise InvalidCredentialsError()

        loop = asyncio.get_running_loop()
        password_valid = await loop.run_in_executor(
            None, self._password_hasher.verify, user.password_hash, password
        )
        if not password_valid:
            user.failed_login_attempts += 1
            user.updated_at = now

            lockout_threshold, lockout_duration = await self._get_login_settings(db)
            attempts_remaining = max(0, lockout_threshold - user.failed_login_attempts)
            if user.failed_login_attempts >= lockout_threshold:
                user.status = UserStatus.LOCKED
                user.lockout_expires_at = now + lockout_duration
                await get_audit_service(db).account_locked(
                    user_id=user.id,
                    username=user.username,
                    role=user.role,
                    lockout_expires_at=user.lockout_expires_at,
                    context=metadata,
                )
                await self._audit_login_failure(
                    db,
                    username=normalized_username,
                    user=user,
                    reason="lockout",
                    attempts_remaining=0,
                    metadata=metadata,
                )
                raise AccountLockedError(lockout_expires_at=user.lockout_expires_at)

            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="invalid_credentials",
                attempts_remaining=attempts_remaining,
                metadata=metadata,
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
        metadata: AuditContext,
    ) -> LoginResult:
        if user.status != UserStatus.ACTIVE:
            raise AccountDisabledError()

        now = datetime.now(timezone.utc)
        session_token = secrets.token_urlsafe(48)
        session_token_hash = hash_opaque_token(session_token)
        session_id = uuid4()

        expires_at = now + self._absolute_timeout

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

        await get_audit_service(db).login_success(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_id=session.id,
            issued_at=now,
            expires_at=session.expires_at,
            context=metadata,
        )

        return LoginResult(user=user, session=session, session_token=session_token)

    async def logout(
        self,
        db: AsyncSession,
        *,
        session_token: str,
        metadata: AuditContext,
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
            await get_audit_service(db).logout(
                user_id=session.user.id,
                session_id=session.id,
                reason=reason,
                context=metadata,
            )

        return session

    async def validate_session(
        self,
        db: AsyncSession,
        *,
        session_token: str,
        allow_password_change_required: bool = False,
    ) -> LoginResult:
        """
        Validate an existing session token and return user/session details.
        
        This is used to check if a session is still active and refresh
        the session data on app load or page refresh.
        
        Raises:
            SessionNotFoundError: If the session is invalid, expired, or revoked.
        """
        session = await self._resolve_active_session(db, session_token)

        # Load user if not already loaded
        user = session.user
        if user is None:
            user = await db.get(UserAccount, session.user_id)
        if user is None:
            raise SessionNotFoundError()
        if user.must_change_password and not allow_password_change_required:
            raise PasswordChangeRequiredError()
        
        return LoginResult(user=user, session=session, session_token=session_token)

    async def change_password(
        self,
        db: AsyncSession,
        *,
        session_token: str,
        current_password: str,
        new_password: str,
        metadata: AuditContext,
    ) -> LoginResult:
        session = await self._resolve_active_session(db, session_token)
        user = session.user
        if user is None:
            user = await db.get(UserAccount, session.user_id)
        if user is None:
            raise SessionNotFoundError()
        if not user.password_hash:
            raise InvalidCredentialsError()

        loop = asyncio.get_running_loop()
        current_valid = await loop.run_in_executor(
            None, self._password_hasher.verify, user.password_hash, current_password
        )
        if not current_valid:
            raise InvalidCredentialsError()

        candidate = validate_password_policy(new_password)

        hashed = await loop.run_in_executor(None, self._password_hasher.hash, candidate)
        now = datetime.now(timezone.utc)

        was_forced = user.must_change_password

        user.password_hash = hashed
        user.password_updated_at = now
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.updated_at = now

        old_session_id = session.id
        session.revoked_at = now
        session.revoked_reason = SessionRevokedReason.RESET_REQUIRED

        # Revoke all other active sessions for this user except current one
        user_match = cast(Any, AuthSession.user_id == user.id)
        not_current = cast(Any, AuthSession.id != old_session_id)
        result = await db.execute(select(AuthSession).where(user_match, not_current))
        other_sessions = result.scalars().all()
        for other in other_sessions:
            if other.revoked_at is None:
                other.revoked_at = now
                other.revoked_reason = SessionRevokedReason.RESET_REQUIRED

        new_login = await self.create_session_for_user(db, user=user, metadata=metadata)
        await get_audit_service(db).password_changed(
            user_id=user.id,
            username=user.username,
            was_forced=was_forced,
            context=metadata,
        )
        await db.commit()
        return new_login

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_active_session(self, db: AsyncSession, session_token: str) -> AuthSession:
        hashed = hash_opaque_token(session_token)

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
        idle_expires_at = session.last_seen_at + self._idle_timeout
        if session.expires_at <= now or idle_expires_at <= now:
            session.revoked_at = now
            session.revoked_reason = SessionRevokedReason.SESSION_TIMEOUT
            raise SessionNotFoundError()

        # User should be loaded via selectinload above
        if session.user is None or session.user.status != UserStatus.ACTIVE:
            raise SessionNotFoundError()

        session.last_seen_at = now
        return session

auth_service = AuthService()

__all__ = [
    "AuthService",
    "LoginResult",
    "InvalidCredentialsError",
    "AccountLockedError",
    "AccountDisabledError",
    "NHIPasswordLoginError",
    "SessionNotFoundError",
    "PasswordPolicyViolation",
    "PasswordLoginDisabledError",
    "PasswordChangeRequiredError",
    "auth_service",
]
