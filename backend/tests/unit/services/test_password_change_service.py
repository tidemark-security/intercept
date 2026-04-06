"""
Unit tests for password change service logic.

Tests cover current password verification and session preservation during voluntary password changes.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SessionRevokedReason, UserRole, UserStatus
from app.models.models import AuthSession, UserAccount
from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    PasswordPolicyViolation,
    RequestMetadata,
    SessionNotFoundError,
)
from app.services.security.password_hasher import PasswordHasher


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def password_hasher() -> PasswordHasher:
    """Create a real password hasher for testing."""
    from app.core.settings_registry import get_local
    from app.services.security.password_hasher import Argon2Parameters
    return PasswordHasher(
        Argon2Parameters(
            time_cost=get_local("auth.argon2.time_cost"),
            memory_cost=get_local("auth.argon2.memory_cost_kib"),
            parallelism=get_local("auth.argon2.parallelism"),
            hash_len=get_local("auth.argon2.hash_len"),
            salt_len=get_local("auth.argon2.salt_len"),
            encoding=get_local("auth.argon2.encoding"),
        )
    )


@pytest.fixture
def auth_service(password_hasher: PasswordHasher) -> AuthService:
    """Create an AuthService instance with mocked audit service."""
    return AuthService(password_hasher=password_hasher)


@pytest.fixture
def sample_user(password_hasher: PasswordHasher) -> UserAccount:
    """Create a sample user account."""
    password_hash = password_hasher.hash("OldPassword123!")
    return UserAccount(
        id=uuid4(),
        username="analyst1",
        email="analyst1@example.com",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        password_hash=password_hash,
        password_updated_at=datetime.now(timezone.utc) - timedelta(days=30),
        must_change_password=False,
        failed_login_attempts=0,
        lockout_expires_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_session(sample_user: UserAccount) -> AuthSession:
    """Create a sample auth session."""
    return AuthSession(
        id=uuid4(),
        session_token_hash="abc123hash",
        user_id=sample_user.id,
        user=sample_user,
        issued_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        revoked_at=None,
        revoked_reason=None,
        ip_address="192.168.1.100",
        user_agent="TestAgent/1.0",
        correlation_id=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_change_password_verifies_current_password(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
) -> None:
    """Test that change_password verifies the current password correctly."""
    # Mock the execute query to return empty list for other sessions
    from unittest.mock import MagicMock
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)
    
    # Mock session resolution + audit service
    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service") as mock_get_audit:
        mock_audit_svc = MagicMock()
        mock_audit_svc.password_changed = AsyncMock()
        mock_get_audit.return_value = mock_audit_svc

        # Attempt with correct current password should not raise
        await auth_service.change_password(
            mock_db,
            session_token="valid_token",
            current_password="OldPassword123!",
            new_password="NewSecure!Pass456",
            metadata=RequestMetadata(),
        )

        # Verify commit was called
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_change_password_rejects_incorrect_current_password(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
) -> None:
    """Test that change_password rejects incorrect current password."""
    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session):
        with pytest.raises(InvalidCredentialsError):
            await auth_service.change_password(
                mock_db,
                session_token="valid_token",
                current_password="WrongPassword!",
                new_password="NewSecure!Pass456",
                metadata=RequestMetadata(),
            )

        # Verify commit was NOT called
        mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_change_password_enforces_minimum_length(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
) -> None:
    """Test that change_password enforces minimum password length of 12 characters."""
    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service"):
        with pytest.raises(PasswordPolicyViolation, match="minimum length"):
            await auth_service.change_password(
                mock_db,
                session_token="valid_token",
                current_password="OldPassword123!",
                new_password="Short1!",  # Only 7 characters
                metadata=RequestMetadata(),
            )


@pytest.mark.asyncio
async def test_change_password_enforces_complexity_requirements(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
) -> None:
    """Test that change_password enforces password complexity (upper, lower, number, special)."""
    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service"):
        # Missing uppercase
        with pytest.raises(PasswordPolicyViolation, match="upper, lower, number, and special"):
            await auth_service.change_password(
                mock_db,
                session_token="valid_token",
                current_password="OldPassword123!",
                new_password="nouppercase123!",
                metadata=RequestMetadata(),
            )

        # Missing lowercase
        with pytest.raises(PasswordPolicyViolation):
            await auth_service.change_password(
                mock_db,
                session_token="valid_token",
                current_password="OldPassword123!",
                new_password="NOLOWERCASE123!",
                metadata=RequestMetadata(),
            )

        # Missing number
        with pytest.raises(PasswordPolicyViolation):
            await auth_service.change_password(
                mock_db,
                session_token="valid_token",
                current_password="OldPassword123!",
                new_password="NoNumbersHere!",
                metadata=RequestMetadata(),
            )

        # Missing special character
        with pytest.raises(PasswordPolicyViolation):
            await auth_service.change_password(
                mock_db,
                session_token="valid_token",
                current_password="OldPassword123!",
                new_password="NoSpecialChar123",
                metadata=RequestMetadata(),
            )


@pytest.mark.asyncio
async def test_change_password_preserves_current_session(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
    password_hasher: PasswordHasher,
) -> None:
    """Test that change_password does not revoke the current session."""
    # Create a second session for the same user
    other_session = AuthSession(
        id=uuid4(),
        session_token_hash="other_hash",
        user_id=sample_user.id,
        issued_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        revoked_at=None,
        revoked_reason=None,
    )

    # Mock database to return other session when querying for user's sessions
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [other_session]
    mock_db.execute.return_value = mock_result

    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service") as mock_get_audit:
        mock_audit_svc = MagicMock()
        mock_audit_svc.password_changed = AsyncMock()
        mock_get_audit.return_value = mock_audit_svc

        await auth_service.change_password(
            mock_db,
            session_token="valid_token",
            current_password="OldPassword123!",
            new_password="NewSecure!Pass456",
            metadata=RequestMetadata(),
        )

        # Verify current session was NOT revoked
        assert sample_session.revoked_at is None
        assert sample_session.revoked_reason is None

        # Verify last_seen_at was updated
        assert sample_session.last_seen_at is not None


@pytest.mark.asyncio
async def test_change_password_revokes_other_sessions(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
) -> None:
    """Test that change_password revokes all OTHER active sessions."""
    # Create other sessions for the same user
    session2 = AuthSession(
        id=uuid4(),
        session_token_hash="hash2",
        user_id=sample_user.id,
        issued_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        revoked_at=None,
        revoked_reason=None,
    )

    session3 = AuthSession(
        id=uuid4(),
        session_token_hash="hash3",
        user_id=sample_user.id,
        issued_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        revoked_at=None,
        revoked_reason=None,
    )

    # Mock database to return other sessions
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [session2, session3]
    mock_db.execute.return_value = mock_result

    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service") as mock_get_audit:
        mock_audit_svc = MagicMock()
        mock_audit_svc.password_changed = AsyncMock()
        mock_get_audit.return_value = mock_audit_svc

        await auth_service.change_password(
            mock_db,
            session_token="valid_token",
            current_password="OldPassword123!",
            new_password="NewSecure!Pass456",
            metadata=RequestMetadata(),
        )

        # Verify other sessions were revoked with correct reason
        assert session2.revoked_at is not None
        assert session2.revoked_reason == SessionRevokedReason.RESET_REQUIRED

        assert session3.revoked_at is not None
        assert session3.revoked_reason == SessionRevokedReason.RESET_REQUIRED


@pytest.mark.asyncio
async def test_change_password_updates_user_fields(
    auth_service: AuthService,
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
    password_hasher: PasswordHasher,
) -> None:
    """Test that change_password properly updates user account fields."""
    original_password_hash = sample_user.password_hash
    sample_user.must_change_password = True  # Simulate forced change flag
    sample_user.failed_login_attempts = 3
    sample_user.lockout_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    # Mock no other sessions
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service") as mock_get_audit:
        mock_audit_svc = MagicMock()
        mock_audit_svc.password_changed = AsyncMock()
        mock_get_audit.return_value = mock_audit_svc

        await auth_service.change_password(
            mock_db,
            session_token="valid_token",
            current_password="OldPassword123!",
            new_password="NewSecure!Pass456",
            metadata=RequestMetadata(),
        )

        # Verify password hash was updated
        assert sample_user.password_hash != original_password_hash
        assert password_hasher.verify(sample_user.password_hash, "NewSecure!Pass456")

        # Verify must_change_password flag was cleared
        assert sample_user.must_change_password is False

        # Verify failed login attempts were reset
        assert sample_user.failed_login_attempts == 0

        # Verify lockout was cleared
        assert sample_user.lockout_expires_at is None

        # Verify password_updated_at was set
        assert sample_user.password_updated_at is not None

        # Verify updated_at timestamp was updated
        assert sample_user.updated_at is not None


@pytest.mark.asyncio
async def test_change_password_requires_valid_session(
    auth_service: AuthService,
    mock_db: AsyncMock,
) -> None:
    """Test that change_password requires a valid active session."""
    with patch.object(
        auth_service,
        "_resolve_active_session",
        side_effect=SessionNotFoundError(),
    ):
        with pytest.raises(SessionNotFoundError):
            await auth_service.change_password(
                mock_db,
                session_token="invalid_token",
                current_password="OldPassword123!",
                new_password="NewSecure!Pass456",
                metadata=RequestMetadata(),
            )


@pytest.mark.asyncio
async def test_change_password_calls_audit_logging(
    mock_db: AsyncMock,
    sample_user: UserAccount,
    sample_session: AuthSession,
    password_hasher: PasswordHasher,
) -> None:
    """Test that change_password calls audit service with correct parameters."""
    # Create auth service
    auth_service = AuthService(password_hasher=password_hasher)

    # Mock no other sessions
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    metadata = RequestMetadata(
        ip_address="192.168.1.100",
        user_agent="TestAgent/1.0",
        correlation_id="test-correlation-123",
    )

    with patch.object(auth_service, "_resolve_active_session", return_value=sample_session), \
         patch("app.services.auth_service.get_audit_service") as mock_get_audit:
        mock_audit_svc = MagicMock()
        mock_audit_svc.password_changed = AsyncMock()
        mock_get_audit.return_value = mock_audit_svc

        await auth_service.change_password(
            mock_db,
            session_token="valid_token",
            current_password="OldPassword123!",
            new_password="NewSecure!Pass456",
            metadata=metadata,
        )

        # Verify audit logging was called
        mock_audit_svc.password_changed.assert_called_once()
        
        # Verify audit call parameters
        call_args = mock_audit_svc.password_changed.call_args
        assert call_args.kwargs["user_id"] == sample_user.id
        assert call_args.kwargs["username"] == sample_user.username
        assert call_args.kwargs["was_forced"] is False  # Voluntary change
        assert call_args.kwargs["context"].ip_address == "192.168.1.100"
        assert call_args.kwargs["context"].correlation_id == "test-correlation-123"
