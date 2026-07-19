"""Admin authentication service for user management operations."""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Optional, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.password_policy import validate_password_policy
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
)
from app.services import PasswordHasher, get_audit_service
from app.services.audit_service import AuditContext

logger = logging.getLogger(__name__)


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

        # Load user
        result = await db.execute(
            select(UserAccount)
            .where(UserAccount.id == target_user_id)
            .options(selectinload(UserAccount.sessions))
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise AdminAuthNotFoundError(
                f"User with ID {target_user_id} not found"
            )

        old_status = user.status

        # Update status
        user.status = new_status
        user.updated_at = datetime.now(timezone.utc)

        # If disabling, revoke all active sessions
        if new_status == UserStatus.DISABLED:
            await self._revoke_user_sessions(
                user_id=target_user_id,
                reason=SessionRevokedReason.ADMIN_FORCE,
                db=db,
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
            select(UserAccount).where(UserAccount.id == target_user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise AdminAuthNotFoundError(
                f"User with ID {target_user_id} not found"
            )

        old_values = {
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "assignable": user.assignable,
            "override_timestamps": user.override_timestamps,
            "description": user.description,
        }

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

        # Load user
        result = await db.execute(
            select(UserAccount).where(UserAccount.id == target_user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise AdminAuthNotFoundError(
                f"User with ID {target_user_id} not found"
            )

        if user.account_type == AccountType.NHI:
            raise AdminAuthValidationError(
                "Cannot issue password reset for NHI accounts; they authenticate via API keys only"
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=await self._get_reset_token_expiry_minutes(db))
        reset_token = self._generate_reset_token()

        await self._invalidate_active_reset_requests(user_id=target_user_id, now=now, db=db)

        user.password_hash = None
        user.password_updated_at = None
        user.must_change_password = False
        user.failed_login_attempts = 0
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

        now = datetime.now(timezone.utc)
        token_hash = self._hash_reset_token(token)
        result = await db.execute(
            select(AdminResetRequest)
            .options(selectinload(AdminResetRequest.target_user))
            .where(AdminResetRequest.token_hash == token_hash)
            .with_for_update()
        )
        reset_request = result.scalar_one_or_none()

        if reset_request is None:
            raise AdminAuthValidationError("Password reset token is invalid")
        if reset_request.invalidated_at is not None or reset_request.consumed_at is not None:
            raise AdminAuthValidationError("Password reset token is no longer valid")
        if reset_request.expires_at <= now:
            reset_request.invalidated_at = now
            await db.commit()
            raise AdminAuthValidationError("Password reset token has expired")

        user = reset_request.target_user
        if user is None:
            user = await db.get(UserAccount, reset_request.target_user_id)
        if user is None:
            raise AdminAuthValidationError("Password reset token is invalid")
        if user.account_type == AccountType.NHI:
            raise AdminAuthValidationError("Password reset token is invalid")

        await self._invalidate_active_reset_requests(user_id=user.id, now=now, db=db, exclude_id=reset_request.id)

        loop = asyncio.get_running_loop()
        hashed = await loop.run_in_executor(None, self._hasher.hash, candidate)

        user.password_hash = hashed
        user.password_updated_at = now
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.updated_at = now
        if user.status != UserStatus.DISABLED:
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
