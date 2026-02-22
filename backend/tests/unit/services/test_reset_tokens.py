"""Unit tests for password reset token handling and expiry logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import AccountType, ResetDeliveryChannel, SessionRevokedReason, UserRole, UserStatus
from app.models.models import AdminResetRequest, AuthSession, UserAccount
from app.services.admin_auth_service import admin_auth_service
from app.services.auth_service import RequestMetadata, auth_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


@pytest.mark.asyncio
async def test_reset_request_expires_after_30_minutes(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Reset requests expire after 30 minutes."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        # Issue password reset
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Verify reset request expiration is approximately 30 minutes from now
        now = datetime.now(timezone.utc)
        expected_expiry = now + timedelta(minutes=30)
        
        # Allow 10 second tolerance for test execution time
        time_diff = abs((result.expires_at - expected_expiry).total_seconds())
        assert time_diff < 10, f"Expected expiry around 30 minutes, got diff of {time_diff}s"


@pytest.mark.asyncio
async def test_reset_request_created_with_correct_fields(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Reset request is created with all required fields."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        metadata = RequestMetadata(
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            correlation_id="test-123",
        )
        
        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Fetch the reset request from database
        db_result = await session.execute(
            select(AdminResetRequest).where(
                AdminResetRequest.id == result.reset_request_id
            )
        )
        reset_request = db_result.scalar_one()
        
        # Verify all fields are set correctly
        assert reset_request.target_user_id == analyst.id
        assert reset_request.issued_by_admin_id == admin.id
        assert reset_request.temporary_secret_hash is not None
        assert reset_request.delivery_channel == ResetDeliveryChannel.SECURE_EMAIL
        assert reset_request.delivery_reference == f"email:{analyst.email}"
        assert reset_request.expires_at is not None
        assert reset_request.consumed_at is None
        assert reset_request.invalidated_at is None
        assert reset_request.created_at is not None


@pytest.mark.asyncio
async def test_multiple_resets_create_separate_records(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Issuing multiple resets creates separate AdminResetRequest records."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        # Issue first reset
        result1 = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Issue second reset
        result2 = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Verify two separate records exist
        assert result1.reset_request_id != result2.reset_request_id
        
        db_result = await session.execute(
            select(AdminResetRequest).where(
                AdminResetRequest.target_user_id == analyst.id
            )
        )
        reset_requests = db_result.scalars().all()
        
        assert len(reset_requests) == 2


@pytest.mark.asyncio
async def test_reset_invalidates_previous_sessions(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Issuing a reset invalidates all previous sessions for the user."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        # Create a session for the analyst
        login_metadata = RequestMetadata(
            ip_address="10.0.0.1",
            user_agent="test-browser",
            correlation_id="login-123",
        )
        
        login_result = await auth_service.login(
            db=session,
            username=analyst.username,
            password=DEFAULT_TEST_PASSWORD,
            metadata=login_metadata,
        )
        
        session_token = login_result.session_token
        
        # Verify session is active
        active_result = await session.execute(
            select(AuthSession).where(AuthSession.user_id == analyst.id)
        )
        active_sessions = [s for s in active_result.scalars().all() if s.revoked_at is None]
        assert len(active_sessions) == 1
        
        # Issue password reset
        reset_metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="admin-panel",
            correlation_id="reset-456",
        )
        
        await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=reset_metadata,
            db=session,
        )
        
        # Verify all sessions are now revoked
        active_result = await session.execute(
            select(AuthSession).where(AuthSession.user_id == analyst.id)
        )
        active_sessions = [s for s in active_result.scalars().all() if s.revoked_at is None]
        assert len(active_sessions) == 0
        
        # Verify revocation reason - check all sessions for the analyst
        all_sessions_result = await session.execute(
            select(AuthSession).where(AuthSession.user_id == analyst.id)
        )
        all_sessions = all_sessions_result.scalars().all()
        
        # All sessions should be revoked with RESET_REQUIRED reason
        for session_record in all_sessions:
            assert session_record.revoked_at is not None
            assert session_record.revoked_reason == SessionRevokedReason.RESET_REQUIRED


@pytest.mark.asyncio
async def test_reset_sets_must_change_password_flag(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Issuing a reset sets the must_change_password flag on the user."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        # Verify flag is initially false
        assert analyst.must_change_password is False
        
        # Issue password reset
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Verify flag is now true
        await session.refresh(analyst)
        assert analyst.must_change_password is True


@pytest.mark.asyncio
async def test_reset_clears_lockout_state(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Issuing a reset clears any lockout state on the user account."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        # Simulate locked account
        analyst.failed_login_attempts = 5
        analyst.lockout_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        await session.commit()
        
        # Issue password reset
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Verify lockout is cleared
        await session.refresh(analyst)
        assert analyst.failed_login_attempts == 0
        assert analyst.lockout_expires_at is None


@pytest.mark.asyncio
async def test_temporary_password_hash_is_stored(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    """Reset request stores the hash of the temporary password."""
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    
    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)
        
        original_password_hash = analyst.password_hash
        
        # Issue password reset
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
            request_metadata=metadata,
            db=session,
        )
        
        # Verify user's password hash was updated
        await session.refresh(analyst)
        assert analyst.password_hash != original_password_hash
        
        # Verify reset request has the same hash
        db_result = await session.execute(
            select(AdminResetRequest).where(
                AdminResetRequest.id == result.reset_request_id
            )
        )
        reset_request = db_result.scalar_one()
        
        assert reset_request.temporary_secret_hash == analyst.password_hash


@pytest.mark.asyncio
async def test_cannot_reset_nonexistent_user(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Attempting to reset password for non-existent user raises ValueError."""
    admin = admin_user_factory()
    fake_user_id = uuid4()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        with pytest.raises(ValueError, match="not found"):
            await admin_auth_service.issue_password_reset(
                admin_user_id=admin.id,
                target_user_id=fake_user_id,
                delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
                request_metadata=metadata,
                db=session,
            )


@pytest.mark.asyncio
async def test_admin_cannot_reset_own_password(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Admin cannot reset their own password through the admin panel."""
    admin = admin_user_factory()
    
    async with session_maker() as session:
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        
        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )
        
        with pytest.raises(ValueError, match="Cannot reset your own password"):
            await admin_auth_service.issue_password_reset(
                admin_user_id=admin.id,
                target_user_id=admin.id,
                delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
                request_metadata=metadata,
                db=session,
            )


@pytest.mark.asyncio
async def test_cannot_reset_nhi_password(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    """Password reset cannot be issued for NHI accounts."""
    admin = admin_user_factory()
    now = datetime.now(timezone.utc)
    nhi_user = UserAccount(
        username=f"svc-test-{uuid4().hex[:8]}",
        account_type=AccountType.NHI,
        email=None,
        password_hash=None,
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        failed_login_attempts=0,
        created_at=now,
        updated_at=now,
    )

    async with session_maker() as session:
        session.add(admin)
        session.add(nhi_user)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(nhi_user)

        metadata = RequestMetadata(
            ip_address="127.0.0.1",
            user_agent="test-agent",
            correlation_id="test-correlation-id",
        )

        with pytest.raises(ValueError, match="NHI accounts"):
            await admin_auth_service.issue_password_reset(
                admin_user_id=admin.id,
                target_user_id=nhi_user.id,
                delivery_channel=ResetDeliveryChannel.SECURE_EMAIL,
                request_metadata=metadata,
                db=session,
            )
