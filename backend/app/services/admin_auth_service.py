"""Admin authentication service for user management operations."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Optional, cast
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.password_policy import validate_password_policy
from app.core.authorization_lock import acquire_authorization_lock
from app.models.enums import (
    AccountType,
    SessionRevokedReason,
    UserRole,
    UserStatus,
)
from app.models.models import (
    AdminResetRequest,
    AuthSession,
    UserAccount,
    WebAuthnChallenge,
)
from app.services import PasswordHasher, get_audit_service
from app.services.audit_service import AuditContext
from app.services.credential_invalidation import credential_was_issued_after_cutoff
from app.services.mcp_oauth_service import mcp_oauth_service
from app.services.oidc_local_credential_policy import oidc_local_credential_policy
from app.services.password_hash_work_service import password_hash_work_service
from app.services.password_login_request_service import password_login_request_service

logger = logging.getLogger(__name__)


def _utc_timestamp(value: datetime) -> datetime:
    """Normalize database timestamps before strict credential ordering checks."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Expected operation failures
# ---------------------------------------------------------------------------


class AdminAuthError(ValueError):
    """Base class for expected admin-auth operation rejections."""


class AdminAuthValidationError(AdminAuthError):
    """Raised when an admin-auth operation is invalid for the target account."""


class AdminAuthConflictError(AdminAuthError):
    """Raised when requested account data conflicts with an existing account."""


class AdminAuthNotFoundError(AdminAuthError):
    """Raised when an admin-auth operation targets a missing account."""


class AdminAuthPolicyError(AdminAuthError):
    """Raised when account policy forbids a local-credential operation."""


class AdminAuthBusyError(AdminAuthError):
    """Raised when a concurrent account mutation owns the target row lock."""


def validate_oidc_preprovisioning_issuer(value: str) -> str:
    """Validate an exact OIDC issuer without normalizing its identity value."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise AdminAuthValidationError(
            "OIDC issuer cannot be blank or contain surrounding whitespace"
        )
    if len(value) > 500 or any(character.isspace() for character in value):
        raise AdminAuthValidationError("OIDC issuer is invalid")

    parsed = urlparse(value)
    try:
        parsed.port
    except ValueError as exc:
        raise AdminAuthValidationError("OIDC issuer has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AdminAuthValidationError(
            "OIDC issuer must be an HTTPS URL without userinfo, query, or fragment"
        )
    return value


def validate_oidc_preprovisioning_subject(value: str) -> str:
    """Validate an exact OIDC subject without normalizing its identity value."""

    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 255
    ):
        raise AdminAuthValidationError(
            "OIDC subject cannot be blank or contain surrounding whitespace"
        )
    return value


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CreateUserResult:
    """Result of user creation operation."""

    user_id: UUID
    expires_at: datetime
    reset_token: str


@dataclass(slots=True)
class CreateOIDCUserResult:
    """Result of exact OIDC account pre-provisioning."""

    user_id: UUID


@dataclass(slots=True)
class PasswordResetResult:
    """Result of password reset issuance."""

    reset_request_id: UUID
    expires_at: datetime
    reset_token: str


# ---------------------------------------------------------------------------
# Admin Auth Service
# ---------------------------------------------------------------------------


class AdminAuthService:
    """Service layer for admin-initiated user management operations."""

    def __init__(
        self,
        *,
        password_hasher: Optional[PasswordHasher] = None,
    ) -> None:
        self._hasher = password_hasher or PasswordHasher.from_local_settings()

    async def create_user(
        self,
        *,
        admin_user_id: UUID,
        username: str,
        email: Optional[str],
        role: UserRole,
        description: Optional[str] = None,
        request_metadata: AuditContext,
        db: AsyncSession,
    ) -> CreateUserResult:
        """
        Create a new user account with a one-time password setup token.

        Args:
            admin_user_id: ID of the admin creating the user
            username: Username for the new account
            email: Optional email address for the new account
            role: Role to assign to the user
            description: Optional job title or role description
            request_metadata: Request context for audit logging
            db: Database session

        Returns:
            CreateUserResult with user ID and password setup token details

        Raises:
            AdminAuthConflictError: If username or email already exists
        """
        normalized_username = username.strip().lower()
        normalized_email = email.strip().lower() if email and email.strip() else None

        # Check for duplicate username
        result = await db.execute(
            select(UserAccount).where(UserAccount.username == normalized_username)
        )
        if result.scalar_one_or_none() is not None:
            raise AdminAuthConflictError(
                f"Username '{normalized_username}' already exists"
            )

        # Check for duplicate email
        if normalized_email:
            result = await db.execute(
                select(UserAccount).where(UserAccount.email == normalized_email)
            )
            if result.scalar_one_or_none() is not None:
                raise AdminAuthConflictError(
                    f"Email '{normalized_email}' already exists"
                )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=await self._get_reset_token_expiry_minutes(db))
        reset_token = self._generate_reset_token()
        user = UserAccount(
            username=normalized_username,
            email=normalized_email,
            role=role,
            description=description,
            status=UserStatus.ACTIVE,
            password_hash=None,
            password_updated_at=None,
            must_change_password=False,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
            created_by_admin_id=admin_user_id,
        )

        db.add(user)
        await db.flush()

        reset_request = AdminResetRequest(
            target_user_id=user.id,
            issued_by_admin_id=admin_user_id,
            token_hash=self._hash_reset_token(reset_token),
            expires_at=expires_at,
            created_at=now,
        )
        db.add(reset_request)

        await get_audit_service(db).user_created(
            admin_user_id=admin_user_id,
            target_user_id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            context=request_metadata,
        )
        response = CreateUserResult(
            user_id=user.id,
            expires_at=expires_at,
            reset_token=reset_token,
        )
        await db.commit()

        logger.info(
            f"Admin {admin_user_id} created user {user.id} ({normalized_username}) with role {role.value}"
        )

        return response

    async def create_oidc_user(
        self,
        *,
        admin_user_id: UUID,
        username: str,
        email: Optional[str],
        role: UserRole,
        oidc_issuer: str,
        oidc_subject: str,
        description: Optional[str] = None,
        request_metadata: AuditContext,
        db: AsyncSession,
    ) -> CreateOIDCUserResult:
        """Pre-provision one OIDC-only human account with an exact identity."""

        oidc_issuer = validate_oidc_preprovisioning_issuer(oidc_issuer)
        oidc_subject = validate_oidc_preprovisioning_subject(oidc_subject)
        normalized_username = username.strip().lower()
        normalized_email = email.strip().lower() if email and email.strip() else None
        normalized_description = description.strip() if description else None

        identity_result = await db.execute(
            select(UserAccount).where(
                UserAccount.oidc_issuer == oidc_issuer,
                UserAccount.oidc_subject == oidc_subject,
            )
        )
        if identity_result.scalar_one_or_none() is not None:
            raise AdminAuthConflictError("OIDC identity already exists")

        username_result = await db.execute(
            select(UserAccount).where(UserAccount.username == normalized_username)
        )
        if username_result.scalar_one_or_none() is not None:
            raise AdminAuthConflictError(
                f"Username '{normalized_username}' already exists"
            )

        if normalized_email is not None:
            email_result = await db.execute(
                select(UserAccount).where(UserAccount.email == normalized_email)
            )
            if email_result.scalar_one_or_none() is not None:
                raise AdminAuthConflictError(
                    f"Email '{normalized_email}' already exists"
                )

        now = datetime.now(timezone.utc)
        user = UserAccount(
            username=normalized_username,
            email=normalized_email,
            role=role,
            description=normalized_description or None,
            status=UserStatus.ACTIVE,
            account_type=AccountType.HUMAN,
            password_hash=None,
            password_updated_at=None,
            must_change_password=False,
            failed_login_attempts=0,
            oidc_issuer=oidc_issuer,
            oidc_subject=oidc_subject,
            created_at=now,
            updated_at=now,
            created_by_admin_id=admin_user_id,
        )
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise AdminAuthConflictError(
                "OIDC identity, username, or email already exists"
            ) from exc
        await get_audit_service(db).oidc_account_preprovisioned(
            admin_user_id=admin_user_id,
            user_id=user.id,
            username=user.username,
            email=str(user.email) if user.email is not None else None,
            role=user.role,
            oidc_issuer=oidc_issuer,
            oidc_subject=oidc_subject,
            context=request_metadata,
        )
        response = CreateOIDCUserResult(user_id=user.id)
        await db.commit()
        return response

    async def update_user_status(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        new_status: UserStatus,
        request_metadata: AuditContext,
        db: AsyncSession,
    ) -> None:
        """
        Update the status of a user account.

        Args:
            admin_user_id: ID of the admin performing the action
            target_user_id: ID of the user to update
            new_status: New status to set
            request_metadata: Request context for audit logging
            db: Database session

        Raises:
            AdminAuthNotFoundError: If the target user does not exist
            AdminAuthValidationError: If attempting self-modification
        """
        # Prevent self-modification
        if admin_user_id == target_user_id:
            raise AdminAuthValidationError("Cannot change your own account status")

        # Fail fast instead of waiting while the acting administrator's auth
        # transaction holds its own row lock. This prevents reciprocal A→B /
        # B→A administration requests from forming a database deadlock.
        result = await db.execute(
            select(UserAccount)
            .where(UserAccount.id == target_user_id)
            .options(selectinload(UserAccount.sessions))
            .execution_options(populate_existing=True)
            .with_for_update(skip_locked=True)
        )
        user = result.scalar_one_or_none()

        if user is None:
            exists_result = await db.execute(
                select(UserAccount.id).where(UserAccount.id == target_user_id)
            )
            if exists_result.scalar_one_or_none() is None:
                raise AdminAuthNotFoundError(
                    f"User with ID {target_user_id} not found"
                )
            raise AdminAuthBusyError(
                "User account is being modified; retry the request"
            )

        old_status = user.status

        # Status transitions are the administrative recovery boundary. Clear
        # both current and obsolete pending deltas while the account gate is
        # held so guesses made against a rejected posture cannot defeat it.
        await password_login_request_service.clear_pending_failures(
            db,
            user_id=user.id,
        )

        # Update status
        status_changed_at = datetime.now(timezone.utc)
        user.status = new_status
        user.updated_at = status_changed_at

        # Explicit administrative locks are indefinite. Clear any temporary
        # brute-force lock metadata so password login cannot later self-unlock.
        if new_status == UserStatus.LOCKED:
            user.lockout_expires_at = None
            user.failed_login_attempts = 0

        # If disabling, revoke all active sessions
        if new_status == UserStatus.DISABLED:
            user.credentials_invalidated_at = status_changed_at
            await self._revoke_user_sessions(
                user_id=target_user_id,
                reason=SessionRevokedReason.ADMIN_FORCE,
                db=db,
            )
            await self._invalidate_active_reset_requests(
                user_id=target_user_id,
                now=status_changed_at,
                db=db,
            )
            await db.execute(
                update(WebAuthnChallenge)
                .where(
                    WebAuthnChallenge.user_id == target_user_id,
                    cast(Any, WebAuthnChallenge.consumed_at).is_(None),
                )
                .values(consumed_at=status_changed_at)
            )
            await mcp_oauth_service.invalidate_user_grants(
                db,
                user_id=target_user_id,
                invalidated_at=status_changed_at,
            )
            await oidc_local_credential_policy.revoke_all_local_credentials(
                db,
                user_id=target_user_id,
            )

        # If re-enabling from locked, clear lockout
        if new_status == UserStatus.ACTIVE and old_status == UserStatus.LOCKED:
            user.lockout_expires_at = None
            user.failed_login_attempts = 0

        await get_audit_service(db).user_status_changed(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            old_status=old_status,
            new_status=new_status,
            context=request_metadata,
        )
        await db.commit()

        logger.info(
            f"Admin {admin_user_id} changed status of user {target_user_id} "
            f"from {old_status.value} to {new_status.value}"
        )

    async def update_user(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        username: Optional[str] = None,
        email: Optional[str] = None,
        email_provided: bool = False,
        role: Optional[UserRole] = None,
        assignable: Optional[bool] = None,
        override_timestamps: Optional[bool] = None,
        description: Optional[str] = None,
        request_metadata: AuditContext,
        db: AsyncSession,
    ) -> UserAccount:
        """Update editable fields on a user account."""
        if admin_user_id == target_user_id:
            raise AdminAuthValidationError(
                "Cannot edit your own account through the admin panel"
            )

        result = await db.execute(
            select(UserAccount)
            .where(UserAccount.id == target_user_id)
            .execution_options(populate_existing=True)
            .with_for_update(skip_locked=True)
        )
        user = result.scalar_one_or_none()

        if user is None:
            exists_result = await db.execute(
                select(UserAccount.id).where(UserAccount.id == target_user_id)
            )
            if exists_result.scalar_one_or_none() is None:
                raise AdminAuthNotFoundError(
                    f"User with ID {target_user_id} not found"
                )
            raise AdminAuthBusyError(
                "User account is being modified; retry the request"
            )

        old_values = {
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "assignable": user.assignable,
            "override_timestamps": user.override_timestamps,
            "description": user.description,
        }

        if username is not None or role is not None:
            # Username and role changes can alter password bypass/break-glass
            # posture. Make the transition linearizable with in-flight failures.
            await password_login_request_service.clear_pending_failures(
                db,
                user_id=user.id,
            )

        if username is not None:
            normalized_username = username.strip().lower()
            duplicate_username_result = await db.execute(
                select(UserAccount).where(
                    UserAccount.username == normalized_username,
                    UserAccount.id != target_user_id,
                )
            )
            if duplicate_username_result.scalar_one_or_none() is not None:
                raise AdminAuthConflictError(
                    f"Username '{normalized_username}' already exists"
                )
            user.username = normalized_username

        if email_provided:
            if user.account_type == AccountType.NHI:
                raise AdminAuthValidationError(
                    "NHI accounts cannot have an email address"
                )
            if email is None:
                user.email = None
            else:
                normalized_email = email.strip().lower()
                duplicate_email_result = await db.execute(
                    select(UserAccount).where(
                        UserAccount.email == normalized_email,
                        UserAccount.id != target_user_id,
                    )
                )
                if duplicate_email_result.scalar_one_or_none() is not None:
                    raise AdminAuthConflictError(
                        f"Email '{normalized_email}' already exists"
                    )
                user.email = normalized_email

        if role is not None:
            user.role = role

        if assignable is not None:
            if user.account_type != AccountType.NHI and assignable:
                raise AdminAuthValidationError(
                    "Only NHI accounts can be made assignable"
                )
            user.assignable = assignable

        if override_timestamps is not None:
            if user.account_type != AccountType.NHI and override_timestamps:
                raise AdminAuthValidationError(
                    "Only NHI accounts can override timestamps"
                )
            user.override_timestamps = override_timestamps

        if description is not None:
            normalized_description = description.strip()
            user.description = normalized_description or None

        user.updated_at = datetime.now(timezone.utc)

        await oidc_local_credential_policy.revoke_impermissible_credentials(
            db,
            user=user,
        )

        await get_audit_service(db).user_updated(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            old_value=old_values,
            new_value={
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "assignable": user.assignable,
                "override_timestamps": user.override_timestamps,
                "description": user.description,
            },
            context=request_metadata,
        )
        await db.commit()

        logger.info(
            f"Admin {admin_user_id} updated user {target_user_id} "
            f"({user.username})"
        )

        return user

    async def issue_password_reset(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        request_metadata: AuditContext,
        db: AsyncSession,
    ) -> PasswordResetResult:
        """
        Issue an admin-initiated password reset.

        This will:
        - Generate a one-time reset token
        - Invalidate the current password
        - Revoke all active sessions
        - Create reset request record

        Args:
            admin_user_id: ID of the admin issuing the reset
            target_user_id: ID of the user to reset
            request_metadata: Request context for audit logging
            db: Database session

        Returns:
            PasswordResetResult with reset details

        Raises:
            AdminAuthNotFoundError: If the target user does not exist
            AdminAuthValidationError: If the operation is invalid for the target
        """
        # Prevent self-modification
        if admin_user_id == target_user_id:
            raise AdminAuthValidationError(
                "Cannot reset your own password through admin panel"
            )

        # Fail fast if a reciprocal administrative request owns the target.
        # The HTTP seam retries with canonical actor/target locking for writer
        # progress; direct service callers must never form a database deadlock.
        result = await db.execute(
            select(UserAccount)
            .where(UserAccount.id == target_user_id)
            .execution_options(populate_existing=True)
            .with_for_update(skip_locked=True)
        )
        user = result.scalar_one_or_none()

        if user is None:
            exists_result = await db.execute(
                select(UserAccount.id).where(UserAccount.id == target_user_id)
            )
            if exists_result.scalar_one_or_none() is None:
                raise AdminAuthNotFoundError(
                    f"User with ID {target_user_id} not found"
                )
            raise AdminAuthBusyError(
                "User account is being modified; retry the request"
            )

        if user.account_type == AccountType.NHI:
            raise AdminAuthValidationError(
                "Cannot issue password reset for NHI accounts; they authenticate via API keys only"
            )
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )
        if not capabilities.password_login_allowed:
            raise AdminAuthPolicyError(
                "Local password resets are disabled for this account"
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=await self._get_reset_token_expiry_minutes(db))
        reset_token = self._generate_reset_token()
        temporary_password_lock = (
            user.status == UserStatus.LOCKED
            and user.lockout_expires_at is not None
        )

        await password_login_request_service.clear_pending_failures(
            db,
            user_id=user.id,
        )

        await self._invalidate_active_reset_requests(user_id=target_user_id, now=now, db=db)

        user.password_hash = None
        user.password_updated_at = None
        user.must_change_password = False
        user.failed_login_attempts = 0
        # A non-null expiry is the existing distinction between a temporary
        # password lock and an indefinite administrative lock. Keep it until
        # the reset is consumed so consumption cannot reinterpret a temporary
        # lock as an administrative one.
        if not temporary_password_lock:
            user.lockout_expires_at = None
        user.updated_at = now

        # Create reset request record
        reset_request = AdminResetRequest(
            target_user_id=target_user_id,
            issued_by_admin_id=admin_user_id,
            token_hash=self._hash_reset_token(reset_token),
            expires_at=expires_at,
            created_at=now,
        )

        db.add(reset_request)

        # Revoke all active sessions
        await self._revoke_user_sessions(
            user_id=target_user_id,
            reason=SessionRevokedReason.RESET_REQUIRED,
            db=db,
        )

        await get_audit_service(db).password_reset_issued(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            reset_request_id=reset_request.id,
            expires_at=expires_at,
            context=request_metadata,
        )
        response = PasswordResetResult(
            reset_request_id=reset_request.id,
            expires_at=expires_at,
            reset_token=reset_token,
        )
        await db.commit()

        logger.info(
            f"Admin {admin_user_id} issued password reset for user {target_user_id}"
        )

        return response

    async def consume_reset_token(
        self,
        *,
        token: str,
        new_password: str,
        request_metadata: AuditContext,
        db: AsyncSession,
    ) -> None:
        """Consume a one-time reset token and set a new password."""
        candidate = validate_password_policy(new_password)

        token_hash = self._hash_reset_token(token)
        candidate_result = await db.execute(
            select(AdminResetRequest).where(
                AdminResetRequest.token_hash == token_hash
            )
        )
        candidate_request = candidate_result.scalar_one_or_none()

        if candidate_request is None:
            raise AdminAuthValidationError("Password reset token is invalid")

        user, reset_request, _ = await self._lock_reset_request_for_consumption(
            db,
            reset_request_id=candidate_request.id,
            target_user_id=candidate_request.target_user_id,
            token_hash=token_hash,
        )
        snapshot_reset_request_id = reset_request.id
        snapshot_target_user_id = user.id

        # Release the account gate and reset/user row locks before Argon2.
        await db.commit()
        hashed = await password_hash_work_service.reserve_commit_and_run(
            db,
            work_kind="password_reset",
            operation=lambda: self._hasher.hash(candidate),
        )

        # The token, account posture, OIDC policy, and credential cutoff may all
        # have changed while hashing. Re-lock and revalidate exact current rows
        # before consuming the one-time token.
        user, reset_request, now = await self._lock_reset_request_for_consumption(
            db,
            reset_request_id=snapshot_reset_request_id,
            target_user_id=snapshot_target_user_id,
            token_hash=token_hash,
        )

        preserve_administrative_lock = (
            user.status == UserStatus.LOCKED and user.lockout_expires_at is None
        )

        await self._invalidate_active_reset_requests(
            user_id=user.id,
            now=now,
            db=db,
            exclude_id=reset_request.id,
        )

        await password_login_request_service.clear_pending_failures(
            db,
            user_id=user.id,
        )

        user.password_hash = hashed
        user.password_updated_at = now
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.updated_at = now
        if user.status != UserStatus.DISABLED and not preserve_administrative_lock:
            user.status = UserStatus.ACTIVE

        reset_request.consumed_at = now
        await self._revoke_user_sessions(
            user_id=user.id,
            reason=SessionRevokedReason.RESET_REQUIRED,
            db=db,
        )

        await get_audit_service(db).password_changed(
            user_id=user.id,
            username=user.username,
            was_forced=False,
            context=request_metadata,
        )
        await db.commit()

    async def _lock_reset_request_for_consumption(
        self,
        db: AsyncSession,
        *,
        reset_request_id: UUID,
        target_user_id: UUID,
        token_hash: str,
    ) -> tuple[UserAccount, AdminResetRequest, datetime]:
        """Lock and validate the exact reset-token/account pair."""

        await acquire_authorization_lock(
            db,
            user_id=target_user_id,
            shared=False,
        )
        user = await db.get(
            UserAccount,
            target_user_id,
            populate_existing=True,
            with_for_update=True,
        )
        if user is None:
            raise AdminAuthValidationError("Password reset token is invalid")

        result = await db.execute(
            select(AdminResetRequest)
            .where(
                AdminResetRequest.id == reset_request_id,
                AdminResetRequest.token_hash == token_hash,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        reset_request = result.scalar_one_or_none()

        if reset_request is None:
            raise AdminAuthValidationError("Password reset token is invalid")
        now = datetime.now(timezone.utc)
        if reset_request.invalidated_at is not None or reset_request.consumed_at is not None:
            raise AdminAuthValidationError("Password reset token is no longer valid")
        if reset_request.expires_at <= now:
            reset_request.invalidated_at = now
            await db.commit()
            raise AdminAuthValidationError("Password reset token has expired")

        if user.account_type == AccountType.NHI:
            raise AdminAuthValidationError("Password reset token is invalid")
        capabilities = await oidc_local_credential_policy.capabilities_for(
            db,
            user=user,
        )
        if not capabilities.password_login_allowed:
            reset_request.invalidated_at = now
            await db.commit()
            raise AdminAuthPolicyError(
                "Local password resets are disabled for this account"
            )
        if not credential_was_issued_after_cutoff(
            user,
            issued_at=reset_request.created_at,
        ):
            reset_request.invalidated_at = now
            await db.commit()
            raise AdminAuthValidationError("Password reset token is no longer valid")
        if (
            user.password_updated_at is not None
            and _utc_timestamp(reset_request.created_at)
            <= _utc_timestamp(user.password_updated_at)
        ):
            # PostgreSQL and Python both retain microsecond precision here. A
            # tie fails closed: only a reset token strictly newer than the
            # current password version may replace it.
            reset_request.invalidated_at = now
            await db.commit()
            raise AdminAuthValidationError("Password reset token is no longer valid")
        return user, reset_request, now

    async def _revoke_user_sessions(
        self,
        *,
        user_id: UUID,
        reason: SessionRevokedReason,
        db: AsyncSession,
    ) -> int:
        """
        Revoke all active sessions for a user.

        Returns:
            Number of sessions revoked
        """
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                cast(Any, AuthSession.revoked_at).is_(None),
                AuthSession.expires_at > now,
            )
        )
        active_sessions = result.scalars().all()

        for session in active_sessions:
            session.revoked_at = now
            session.revoked_reason = reason

        return len(active_sessions)

    async def _invalidate_active_reset_requests(
        self,
        *,
        user_id: UUID,
        now: datetime,
        db: AsyncSession,
        exclude_id: Optional[UUID] = None,
    ) -> None:
        result = await db.execute(
            select(AdminResetRequest).where(
                AdminResetRequest.target_user_id == user_id,
                cast(Any, AdminResetRequest.consumed_at).is_(None),
                cast(Any, AdminResetRequest.invalidated_at).is_(None),
            )
        )
        for reset_request in result.scalars().all():
            if exclude_id is not None and reset_request.id == exclude_id:
                continue
            reset_request.invalidated_at = now

    async def _get_reset_token_expiry_minutes(self, db: AsyncSession) -> int:
        from app.services.settings_service import SettingsService

        svc = SettingsService(db)  # type: ignore[arg-type]
        return int(await svc.get("reset_token.expiry_minutes", default=30))

    @staticmethod
    def _generate_reset_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def _hash_reset_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def get_users(
        self,
        *,
        db: AsyncSession,
        status: Optional[UserStatus] = UserStatus.ACTIVE,
        role: Optional[UserRole] = None,
        account_type: Optional[str] = None,
    ) -> list[UserAccount]:
        """
        Get list of users for filtering purposes.

        Args:
            db: Database session
            status: Filter by user status (default: ACTIVE only)
            role: Optional filter by user role

        Returns:
            List of UserAccount objects matching the criteria
        """
        query = select(UserAccount)
        
        if status is not None:
            query = query.where(UserAccount.status == status)
        
        if role is not None:
            query = query.where(UserAccount.role == role)

        if account_type is not None:
            query = query.where(UserAccount.account_type == account_type)
            
        query = query.order_by(UserAccount.username)
        
        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance
admin_auth_service = AdminAuthService()
