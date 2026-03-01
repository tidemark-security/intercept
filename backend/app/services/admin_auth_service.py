"""Admin authentication service for user management operations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import secrets
import string
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings_registry import get_local
from app.models.enums import (
    AccountType,
    ResetDeliveryChannel,
    SessionRevokedReason,
    UserRole,
    UserStatus,
)
from app.models.models import (
    AdminResetRequest,
    AuthSession,
    UserAccount,
)
from app.services import AuditContext, AuthAuditService, PasswordHasher
from app.services.auth_service import RequestMetadata
from app.services.notifications import email_service
from app.services.security.password_hasher import Argon2Parameters

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CreateUserResult:
    """Result of user creation operation."""

    user_id: UUID
    temporary_credential_expires_at: datetime
    delivery_channel: ResetDeliveryChannel
    temporary_password: str  # For email delivery


@dataclass(slots=True)
class PasswordResetResult:
    """Result of password reset issuance."""

    reset_request_id: UUID
    expires_at: datetime
    temporary_password: str  # For email delivery


# ---------------------------------------------------------------------------
# Admin Auth Service
# ---------------------------------------------------------------------------


class AdminAuthService:
    """Service layer for admin-initiated user management operations."""

    def __init__(
        self,
        *,
        password_hasher: Optional[PasswordHasher] = None,
        audit_service: Optional[AuthAuditService] = None,
    ) -> None:
        self._hasher = password_hasher or PasswordHasher(
            Argon2Parameters(
                time_cost=get_local("auth.argon2.time_cost"),
                memory_cost=get_local("auth.argon2.memory_cost_kib"),
                parallelism=get_local("auth.argon2.parallelism"),
                hash_len=get_local("auth.argon2.hash_len"),
                salt_len=get_local("auth.argon2.salt_len"),
                encoding=get_local("auth.argon2.encoding"),
            )
        )
        self._audit = audit_service or AuthAuditService()

    async def create_user(
        self,
        *,
        admin_user_id: UUID,
        username: str,
        email: str,
        role: UserRole,
        description: Optional[str] = None,
        delivery_channel: ResetDeliveryChannel,
        request_metadata: RequestMetadata,
        db: AsyncSession,
    ) -> CreateUserResult:
        """
        Create a new user account with a temporary password.

        Args:
            admin_user_id: ID of the admin creating the user
            username: Username for the new account
            email: Email address for the new account
            role: Role to assign to the user
            description: Optional job title or role description
            delivery_channel: How to deliver the temporary credential
            request_metadata: Request context for audit logging
            db: Database session

        Returns:
            CreateUserResult with user ID and temporary credential details

        Raises:
            ValueError: If username or email already exists
        """
        # Check for duplicate username
        result = await db.execute(
            select(UserAccount).where(UserAccount.username == username.lower())
        )
        if result.scalar_one_or_none() is not None:
            raise ValueError(f"Username '{username}' already exists")

        # Check for duplicate email
        result = await db.execute(
            select(UserAccount).where(UserAccount.email == email.lower())
        )
        if result.scalar_one_or_none() is not None:
            raise ValueError(f"Email '{email}' already exists")

        # Generate temporary password
        temporary_password = self._generate_temporary_password()
        password_hash = self._hasher.hash(temporary_password)

        # Create user account
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)

        user = UserAccount(
            username=username.lower(),
            email=email.lower(),
            role=role,
            description=description,
            status=UserStatus.ACTIVE,
            password_hash=password_hash,
            password_updated_at=now,
            must_change_password=True,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
            created_by_admin_id=admin_user_id,
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Send temporary credential via email
        try:
            await email_service.send_temporary_credential(
                recipient_email=user.email,
                username=user.username,
                temporary_password=temporary_password,
                expires_in_minutes=30,
            )
        except Exception as e:
            logger.error(f"Failed to send temporary credential email to {user.email}: {e}")
            # Continue anyway - the user was created successfully

        # Audit log
        self._audit.user_created(
            admin_user_id=admin_user_id,
            target_user_id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            context=request_metadata.to_audit_context(),
        )

        logger.info(
            f"Admin {admin_user_id} created user {user.id} ({username}) with role {role.value}"
        )

        return CreateUserResult(
            user_id=user.id,
            temporary_credential_expires_at=expires_at,
            delivery_channel=delivery_channel,
            temporary_password=temporary_password,
        )

    async def update_user_status(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        new_status: UserStatus,
        request_metadata: RequestMetadata,
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
            ValueError: If user not found or attempting self-modification
        """
        # Prevent self-modification
        if admin_user_id == target_user_id:
            raise ValueError("Cannot change your own account status")

        # Load user
        result = await db.execute(
            select(UserAccount)
            .where(UserAccount.id == target_user_id)
            .options(selectinload(UserAccount.sessions))
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise ValueError(f"User with ID {target_user_id} not found")

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

        await db.commit()

        # Audit log
        self._audit.user_status_changed(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            old_status=old_status,
            new_status=new_status,
            context=request_metadata.to_audit_context(),
        )

        logger.info(
            f"Admin {admin_user_id} changed status of user {target_user_id} "
            f"from {old_status.value} to {new_status.value}"
        )

    async def issue_password_reset(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        delivery_channel: ResetDeliveryChannel,
        request_metadata: RequestMetadata,
        db: AsyncSession,
    ) -> PasswordResetResult:
        """
        Issue an admin-initiated password reset.

        This will:
        - Generate a temporary password
        - Set must_change_password flag
        - Revoke all active sessions
        - Create reset request record

        Args:
            admin_user_id: ID of the admin issuing the reset
            target_user_id: ID of the user to reset
            delivery_channel: How to deliver the temporary credential
            request_metadata: Request context for audit logging
            db: Database session

        Returns:
            PasswordResetResult with reset details

        Raises:
            ValueError: If user not found or attempting self-modification
        """
        # Prevent self-modification
        if admin_user_id == target_user_id:
            raise ValueError("Cannot reset your own password through admin panel")

        # Load user
        result = await db.execute(
            select(UserAccount).where(UserAccount.id == target_user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise ValueError(f"User with ID {target_user_id} not found")

        if user.account_type == AccountType.NHI:
            raise ValueError(
                "Cannot issue password reset for NHI accounts; they authenticate via API keys only"
            )

        # Generate temporary password
        temporary_password = self._generate_temporary_password()
        password_hash = self._hasher.hash(temporary_password)

        # Update user
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)

        user.password_hash = password_hash
        user.password_updated_at = now
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.updated_at = now

        # Create reset request record
        reset_request = AdminResetRequest(
            target_user_id=target_user_id,
            issued_by_admin_id=admin_user_id,
            temporary_secret_hash=password_hash,
            delivery_channel=delivery_channel,
            delivery_reference=f"email:{user.email}",
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

        await db.commit()
        await db.refresh(reset_request)

        # Send temporary credential via email
        try:
            await email_service.send_temporary_credential(
                recipient_email=user.email,
                username=user.username,
                temporary_password=temporary_password,
                expires_in_minutes=30,
            )
        except Exception as e:
            logger.error(f"Failed to send password reset email to {user.email}: {e}")
            # Continue anyway - the reset was created successfully

        # Audit log
        self._audit.password_reset_issued(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            reset_request_id=reset_request.id,
            delivery_channel=delivery_channel.value,
            context=request_metadata.to_audit_context(),
        )

        logger.info(
            f"Admin {admin_user_id} issued password reset for user {target_user_id}"
        )

        return PasswordResetResult(
            reset_request_id=reset_request.id,
            expires_at=expires_at,
            temporary_password=temporary_password,
        )

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
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        active_sessions = result.scalars().all()

        for session in active_sessions:
            session.revoked_at = now
            session.revoked_reason = reason

        if active_sessions:
            await db.commit()

        return len(active_sessions)

    def _generate_temporary_password(self) -> str:
        """
        Generate a secure temporary password.

        Returns a 16-character password meeting policy requirements:
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        """
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
        
        # Ensure password meets all requirements
        password_chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*()"),
        ]
        
        # Fill remaining characters
        for _ in range(12):
            password_chars.append(secrets.choice(alphabet))
        
        # Shuffle to avoid predictable patterns
        secrets.SystemRandom().shuffle(password_chars)
        
        return ''.join(password_chars)

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
