from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Optional, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.account_authentication import non_password_authentication_allowed
from app.core.settings_registry import get_local
from app.core.security import hash_opaque_token
from app.core.authorization_lock import (
    AuthorizationConcurrencyError as AuthenticationConcurrencyError,
    acquire_authorization_lock,
)
from app.core.authentication_activity import defer_session_activity
from app.core.password_policy import PasswordPolicyViolation, validate_password_policy
from app.models.enums import AccountType, SessionRevokedReason, UserRole, UserStatus
from app.models.models import AuthSession, PasswordLoginAttempt, UserAccount
from app.services import AuditContext, PasswordHasher, get_audit_service
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.oidc_local_credential_policy import oidc_local_credential_policy
from app.services.passkey_service import passkey_service
from app.services.password_hash_work_service import password_hash_work_service
from app.services.password_login_request_service import (
    PasswordLoginRequestLimitError,
    PasswordLoginRequestPolicy,
    password_login_request_service,
    password_login_source_fingerprint,
    password_version_fingerprint,
)
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
    """Raised when local password use is disabled for the account."""


class PasswordChangeRequiredError(Exception):
    """Raised when a forced password change gates ordinary authenticated access."""


# ---------------------------------------------------------------------------
# Core authentication service
# ---------------------------------------------------------------------------


class AuthService:
    """Business logic for username/password authentication and sessions."""

    def __init__(
        self,
        *,
        password_hasher: Optional[PasswordHasher] = None,
        login_request_policy: PasswordLoginRequestPolicy | None = None,
    ) -> None:
        # Argon2 params are local_only (changing breaks existing hashes).
        self._password_hasher = password_hasher or PasswordHasher.from_local_settings()
        self._dummy_password_hash = self._password_hasher.hash("InvalidCredentialsDummyPassword123!")
        # Session timeouts are local_only (read per-request from frozen values)
        self._idle_timeout = timedelta(hours=get_local("auth.session.idle_timeout_hours"))
        self._absolute_timeout = timedelta(hours=get_local("auth.session.absolute_timeout_hours"))
        self._login_request_policy = login_request_policy or PasswordLoginRequestPolicy()
        self._login_request_service = password_login_request_service

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def check_rate_limit(
        self,
        db: AsyncSession,
        source_address: str | None,
    ) -> tuple[bool, Optional[int]]:
        capacity, window_seconds = await self._get_rate_limit_settings(db)
        source_fingerprint = password_login_source_fingerprint(source_address)
        attempt = PasswordLoginAttempt(source_fingerprint=source_fingerprint)
        try:
            await self._login_request_service.reserve(
                db,
                attempt=attempt,
                policy=self._login_request_policy,
                per_source_rate_quota=capacity,
                per_source_rate_window_seconds=window_seconds,
            )
        except PasswordLoginRequestLimitError as exc:
            # Persist bounded-history cleanup and release the global advisory
            # lock before returning the rejection.
            await db.commit()
            logger.warning(
                "Password login rate limit exceeded",
                extra={
                    "auth": {
                        "source_fingerprint": source_fingerprint[:16],
                        "retry_after": exc.retry_after_seconds,
                    }
                },
            )
            return False, exc.retry_after_seconds

        # Commit admission before the expensive password verification so the
        # reservation is cross-worker durable without serializing Argon2 work.
        await db.commit()
        return True, None

    async def _get_rate_limit_settings(self, db: AsyncSession) -> tuple[int, int]:
        svc = SettingsService(db)  # type: ignore[arg-type]
        capacity = await svc.get("auth.login.rate_limit_attempts", default=10)
        window_seconds = await svc.get("auth.login.rate_limit_window_seconds", default=60)
        return max(1, int(capacity)), max(1, int(window_seconds))

    async def _get_login_settings(self, db: AsyncSession) -> tuple[int, timedelta]:
        """Read hot-swappable login protection settings from DB.

        Returns ``(lockout_threshold, lockout_duration)``.
        """
        svc = SettingsService(db)  # type: ignore[arg-type]
        threshold = await svc.get("auth.login.lockout_threshold", default=5)
        duration_minutes = await svc.get("auth.login.lockout_duration_minutes", default=15)
        return int(threshold), timedelta(minutes=int(duration_minutes))

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

        username_match = cast(Any, UserAccount.username == normalized_username)
        candidate_result = await db.execute(
            select(UserAccount.id, UserAccount.password_hash).where(username_match)
        )
        candidate = candidate_result.one_or_none()
        candidate_user_id = candidate[0] if candidate is not None else None
        candidate_password_hash = candidate[1] if candidate is not None else None

        # End the read-only snapshot before Argon2 work. Holding either a
        # connection, the account authorization gate, or a row lock while a
        # caller-controlled password is verified lets hostile guesses queue a
        # legitimate login for the same account and exposes account existence
        # through concurrency behavior.
        # Application sessions use expire_on_commit=False, so committing this
        # read-only boundary releases the connection without expiring unrelated
        # already-persisted objects a direct service caller may still hold.
        await db.commit()

        # Spend one password-verification cost for every admitted request
        # before any account-posture rejection. Otherwise NHI, disabled,
        # locked, OIDC-only, and passkey-protected usernames are distinguishable
        # from unknown or ordinary password accounts by response timing.
        encoded_candidate = candidate_password_hash or self._dummy_password_hash
        password_valid = await password_hash_work_service.reserve_commit_and_run(
            db,
            work_kind="login_verify",
            operation=lambda: self._password_hasher.verify(
                encoded_candidate,
                password,
            ),
        )

        candidate_password_fingerprint = (
            password_version_fingerprint(candidate_password_hash)
            if candidate_user_id is not None and candidate_password_hash
            else None
        )
        if not password_valid and candidate_password_fingerprint is not None:
            await self._login_request_service.record_failure(
                db,
                failed_user_id=candidate_user_id,
                password_fingerprint=candidate_password_fingerprint,
            )

        # Re-enter the protected authorization transaction only after the
        # expensive verifier completes, then reload every mutable posture bit.
        # A password rotation between snapshot and lock acquisition invalidates
        # this attempt rather than authorizing a credential that is no longer
        # current. Invalid guesses durably enqueue their failure before taking
        # the exclusive account gate only opportunistically. A later invalid or
        # valid login materializes every pending failure, so callers do not
        # queue behind an administrative writer without losing lockout state.
        user = None
        if candidate_user_id is not None:
            authorization_acquired = await acquire_authorization_lock(
                db,
                user_id=candidate_user_id,
                shared=False,
                wait=password_valid,
            )
            if not authorization_acquired:
                await self._audit_login_failure(
                    db,
                    username=normalized_username,
                    user=None,
                    reason="invalid_credentials",
                    attempts_remaining=None,
                    metadata=metadata,
                )
                raise InvalidCredentialsError()

            result = await db.execute(
                select(UserAccount)
                .where(
                    cast(Any, UserAccount.id == candidate_user_id),
                    username_match,
                )
                .execution_options(populate_existing=True)
                .with_for_update(skip_locked=not password_valid)
            )
            user = result.scalar_one_or_none()
            if user is None or user.password_hash != candidate_password_hash:
                password_valid = False

        now = datetime.now(timezone.utc)

        if user is None:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=None,
                reason="invalid_credentials",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise InvalidCredentialsError()

        password_version_unchanged = (
            bool(candidate_password_fingerprint)
            and user.password_hash == candidate_password_hash
        )
        pending_failures = 0
        if candidate_password_fingerprint is not None:
            consumed_failures = (
                await self._login_request_service.consume_pending_failures(
                    db,
                    user_id=user.id,
                    password_fingerprint=candidate_password_fingerprint,
                )
            )
            if password_version_unchanged:
                pending_failures = consumed_failures

        # A posture-rejected password attempt must not pre-seed a hidden delta
        # that locks the account immediately after an administrator or policy
        # restores password access. Temporary lockouts likewise consume and drop
        # failures received while the lock is already in force.
        if user.lockout_expires_at is not None:
            pending_failures = 0

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

        # Temporary password lockouts are not an account-wide control for
        # administrators: they would let any unauthenticated caller disable the
        # documented break-glass path. Explicit administrative locks above are
        # still authoritative; source/global admission limits bound guesses.
        if user.role == UserRole.ADMIN and user.lockout_expires_at is not None:
            user.lockout_expires_at = None
            user.failed_login_attempts = 0
            if user.status == UserStatus.LOCKED:
                user.status = UserStatus.ACTIVE

        # Reset lockout if expired
        if user.lockout_expires_at and user.lockout_expires_at <= now:
            user.lockout_expires_at = None
            user.failed_login_attempts = 0
            if user.status == UserStatus.LOCKED:
                user.status = UserStatus.ACTIVE

        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )
        if not capabilities.password_login_allowed:
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
        # Administrators retain the explicit break-glass password path even if
        # they also use passkeys during normal operation. Other accounts keep
        # the single-local-authenticator policy once a passkey is registered.
        if has_active_passkeys and user.role != UserRole.ADMIN:
            await self._audit_login_failure(
                db,
                username=normalized_username,
                user=user,
                reason="password_login_disabled_passkey_registered",
                attempts_remaining=None,
                metadata=metadata,
            )
            raise PasswordLoginDisabledError()

        password_is_current = bool(user.password_hash) and credential_was_issued_after_cutoff(
            user,
            issued_at=user.password_updated_at,
        )

        # Requests arriving during an already-active temporary lock do not
        # extend it. Consuming their pending deltas keeps the durable counter
        # from re-locking the account immediately after the timer expires.
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

        user.failed_login_attempts += pending_failures
        if password_valid and not password_is_current and password_version_unchanged:
            # A credential invalidated by an administrative cutoff is still a
            # failed password attempt even though its Argon2 hash matched.
            user.failed_login_attempts += 1

        lockout_threshold, lockout_duration = await self._get_login_settings(db)
        if user.role == UserRole.ADMIN:
            user.failed_login_attempts = min(
                user.failed_login_attempts,
                lockout_threshold,
            )
        elif user.failed_login_attempts >= lockout_threshold:
            user.status = UserStatus.LOCKED
            user.lockout_expires_at = now + lockout_duration
            user.updated_at = now
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

        if not password_valid or not password_is_current:
            user.updated_at = now
            attempts_remaining = max(0, lockout_threshold - user.failed_login_attempts)
            if user.role == UserRole.ADMIN:
                await self._audit_login_failure(
                    db,
                    username=normalized_username,
                    user=user,
                    reason="invalid_credentials",
                    attempts_remaining=None,
                    metadata=metadata,
                )
                raise InvalidCredentialsError()
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
        if not non_password_authentication_allowed(user):
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
        shared_lock: bool = False,
        shared_authorization: bool = True,
    ) -> LoginResult:
        """
        Validate an existing session token and return user/session details.
        
        This is used to check if a session is still active and refresh
        the session data on app load or page refresh.
        
        Raises:
            SessionNotFoundError: If the session is invalid, expired, or revoked.
        """
        session = await self._resolve_active_session(
            db,
            session_token,
            shared_lock=shared_lock,
            shared_authorization=shared_authorization,
        )

        user = session.user
        if user is None:
            raise SessionNotFoundError()
        if user.must_change_password and not allow_password_change_required:
            raise PasswordChangeRequiredError()
        
        return LoginResult(user=user, session=session, session_token=session_token)

    async def validate_session_for_realtime(
        self,
        db: AsyncSession,
        *,
        session_token: str,
    ) -> LoginResult:
        """Validate a realtime session against locked, current credential state.

        Administrative credential changes lock the user before revoking that
        user's sessions. Realtime authorization follows the same order so a
        validation that crosses a committed revocation cannot authorize from
        the older session snapshot.
        """
        session = await self._resolve_active_session(
            db,
            session_token,
            shared_lock=True,
        )
        user = session.user
        if user is None:
            raise SessionNotFoundError()
        if user.must_change_password:
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
        candidate = validate_password_policy(new_password)
        snapshot_session = await self._resolve_active_session(
            db,
            session_token,
            touch=False,
            shared_authorization=False,
        )
        snapshot_user = snapshot_session.user
        if snapshot_user is None:
            raise SessionNotFoundError()
        snapshot_capabilities = (
            await oidc_local_credential_policy.capabilities_for(
                db,
                user=snapshot_user,
            )
        )
        if not snapshot_capabilities.password_login_allowed:
            raise PasswordLoginDisabledError()
        if not snapshot_user.password_hash:
            raise InvalidCredentialsError()

        snapshot_user_id = snapshot_user.id
        snapshot_session_id = snapshot_session.id
        snapshot_session_token_hash = snapshot_session.session_token_hash
        snapshot_password_hash = snapshot_user.password_hash
        snapshot_password_updated_at = snapshot_user.password_updated_at

        # Release the account gate, both row locks, and the database connection
        # before caller-controlled Argon2 work begins.
        await db.commit()

        def verify_and_hash_candidate() -> tuple[bool, str | None]:
            current_valid = self._password_hasher.verify(
                snapshot_password_hash,
                current_password,
            )
            if not current_valid:
                return False, None
            return True, self._password_hasher.hash(candidate)

        current_valid, hashed = await password_hash_work_service.reserve_commit_and_run(
            db,
            work_kind="password_change",
            operation=verify_and_hash_candidate,
        )
        if not current_valid or hashed is None:
            raise InvalidCredentialsError()

        await acquire_authorization_lock(
            db,
            user_id=snapshot_user_id,
            shared=False,
        )
        user = await db.get(
            UserAccount,
            snapshot_user_id,
            populate_existing=True,
            with_for_update=True,
        )
        locked_session = await db.get(
            AuthSession,
            snapshot_session_id,
            populate_existing=True,
            with_for_update=True,
        )
        now = datetime.now(timezone.utc)
        if (
            user is None
            or not non_password_authentication_allowed(user)
            or locked_session is None
            or locked_session.user_id != snapshot_user_id
            or locked_session.session_token_hash != snapshot_session_token_hash
            or locked_session.revoked_at is not None
            or locked_session.expires_at <= now
            or locked_session.last_seen_at + self._idle_timeout <= now
            or not credential_was_issued_after_cutoff(
                user,
                issued_at=locked_session.issued_at,
            )
            or user.password_hash != snapshot_password_hash
            or user.password_updated_at != snapshot_password_updated_at
        ):
            raise SessionNotFoundError()
        session = locked_session
        session.last_seen_at = now
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )
        if not capabilities.password_login_allowed:
            raise PasswordLoginDisabledError()
        if not user.password_hash:
            raise InvalidCredentialsError()
        was_forced = user.must_change_password
        was_temporarily_password_locked = (
            user.status is UserStatus.LOCKED
            and user.lockout_expires_at is not None
        )

        await self._login_request_service.clear_pending_failures(
            db,
            user_id=user.id,
        )

        user.password_hash = hashed
        user.password_updated_at = now
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        if was_temporarily_password_locked:
            user.status = UserStatus.ACTIVE
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

    async def _resolve_active_session(
        self,
        db: AsyncSession,
        session_token: str,
        *,
        touch: bool = True,
        shared_lock: bool = False,
        shared_authorization: bool = True,
    ) -> AuthSession:
        hashed = hash_opaque_token(session_token)

        token_match = cast(Any, AuthSession.session_token_hash == hashed)
        candidate_result = await db.execute(
            select(AuthSession.id, AuthSession.user_id).where(token_match)
        )
        candidate = candidate_result.one_or_none()
        if candidate is None:
            raise SessionNotFoundError()

        session_id, user_id = candidate
        authorization_acquired = await acquire_authorization_lock(
            db,
            user_id=user_id,
            shared=shared_authorization,
            wait=not shared_authorization,
        )
        if not authorization_acquired:
            raise AuthenticationConcurrencyError()
        lock_options = {
            "read": shared_lock,
            "skip_locked": True,
        }

        # Administrative role/status changes lock the user before touching its
        # credentials. Authenticate in the same order and refresh both rows so
        # an authorization request cannot cross a committed downgrade while
        # retaining an older ACTIVE/ADMIN MVCC snapshot.
        user = await db.get(
            UserAccount,
            user_id,
            populate_existing=True,
            with_for_update=lock_options,
        )
        if user is None:
            raise AuthenticationConcurrencyError()

        session = await db.get(
            AuthSession,
            session_id,
            populate_existing=True,
            with_for_update=lock_options,
        )
        if session is None:
            raise AuthenticationConcurrencyError()
        if session.user_id != user.id or session.session_token_hash != hashed:
            raise SessionNotFoundError()

        now = datetime.now(timezone.utc)

        if session.revoked_at is not None:
            raise SessionNotFoundError()
        idle_expires_at = session.last_seen_at + self._idle_timeout
        if session.expires_at <= now or idle_expires_at <= now:
            # Shared authentication protects read requests from crossing a
            # committed credential change. Do not upgrade that shared row lock
            # by persisting timeout bookkeeping in the same transaction.
            if not shared_lock:
                session.revoked_at = now
                session.revoked_reason = SessionRevokedReason.SESSION_TIMEOUT
            raise SessionNotFoundError()

        if not non_password_authentication_allowed(user):
            raise SessionNotFoundError()
        if not credential_was_issued_after_cutoff(
            user,
            issued_at=session.issued_at,
        ):
            if not shared_lock:
                session.revoked_at = now
                session.revoked_reason = SessionRevokedReason.ADMIN_FORCE
            raise SessionNotFoundError()

        # Compatible shared locks let parallel read requests proceed. Touching
        # the row here would make both transactions attempt a lock upgrade at
        # commit and can deadlock, so shared validation is deliberately
        # read-only. Mutating/default validation still refreshes idle activity.
        if touch:
            if shared_lock:
                defer_session_activity(
                    db,
                    session_id=session.id,
                    observed_at=now,
                )
            else:
                session.last_seen_at = now
        session.user = user
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
    "AuthenticationConcurrencyError",
    "auth_service",
]
