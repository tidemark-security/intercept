"""Unit tests for admin-issued password reset tokens."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.models.enums import AccountType, SessionRevokedReason, UserRole, UserStatus
from app.models.models import AdminResetRequest, AuthSession, UserAccount
from app.services.admin_auth_service import admin_auth_service
from app.services.auth_service import RequestMetadata, auth_service
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def _metadata() -> RequestMetadata:
    return RequestMetadata(
        ip_address="127.0.0.1",
        user_agent="test-agent",
        correlation_id="test-correlation-id",
    )


@pytest.mark.asyncio
async def test_reset_request_expires_after_30_minutes(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)

        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )

        now = datetime.now(timezone.utc)
        expected_expiry = now + timedelta(minutes=30)
        time_diff = abs((result.expires_at - expected_expiry).total_seconds())
        assert time_diff < 10


@pytest.mark.asyncio
async def test_reset_request_created_with_token_hash_and_invalidated_password(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)

        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )

        db_result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.id == result.reset_request_id)
        )
        reset_request = db_result.scalar_one()

        await session.refresh(analyst)

        assert result.reset_token
        assert reset_request.target_user_id == analyst.id
        assert reset_request.issued_by_admin_id == admin.id
        assert reset_request.token_hash == hashlib.sha256(result.reset_token.encode("utf-8")).hexdigest()
        assert reset_request.consumed_at is None
        assert reset_request.invalidated_at is None
        assert analyst.password_hash is None
        assert analyst.must_change_password is False
        assert analyst.failed_login_attempts == 0
        assert analyst.lockout_expires_at is None


@pytest.mark.asyncio
async def test_new_reset_invalidates_previous_request(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)

        first = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )
        second = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )

        result = await session.execute(
            select(AdminResetRequest)
            .where(AdminResetRequest.target_user_id == analyst.id)
            .order_by(AdminResetRequest.created_at)
        )
        reset_requests = result.scalars().all()

        assert len(reset_requests) == 2
        assert first.reset_request_id != second.reset_request_id
        assert reset_requests[0].invalidated_at is not None
        assert reset_requests[1].invalidated_at is None


@pytest.mark.asyncio
async def test_reset_invalidates_previous_sessions(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)

        login_result = await auth_service.login(
            db=session,
            username=analyst.username,
            password=DEFAULT_TEST_PASSWORD,
            metadata=_metadata(),
        )
        assert login_result.session_token

        await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )

        all_sessions_result = await session.execute(
            select(AuthSession).where(AuthSession.user_id == analyst.id)
        )
        all_sessions = all_sessions_result.scalars().all()
        assert all_sessions
        for session_record in all_sessions:
            assert session_record.revoked_at is not None
            assert session_record.revoked_reason == SessionRevokedReason.RESET_REQUIRED


@pytest.mark.asyncio
async def test_consume_reset_token_sets_new_password(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")
    new_password = "NewSecurePassword123!"

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)

        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )

        await admin_auth_service.consume_reset_token(
            token=result.reset_token,
            new_password=new_password,
            request_metadata=_metadata(),
            db=session,
        )

        await session.refresh(analyst)
        reset_request_result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.id == result.reset_request_id)
        )
        reset_request = reset_request_result.scalar_one()

        assert analyst.password_hash is not None
        assert analyst.must_change_password is False
        assert analyst.password_updated_at is not None
        assert reset_request.consumed_at is not None

        login_result = await auth_service.login(
            db=session,
            username=analyst.username,
            password=new_password,
            metadata=_metadata(),
        )
        assert login_result.user.id == analyst.id


@pytest.mark.asyncio
async def test_consume_reset_token_rejects_expired_request(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
    analyst_user_factory,
) -> None:
    admin = admin_user_factory()
    analyst = analyst_user_factory(username="target.analyst")

    async with session_maker() as session:
        session.add(admin)
        session.add(analyst)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(analyst)

        result = await admin_auth_service.issue_password_reset(
            admin_user_id=admin.id,
            target_user_id=analyst.id,
            request_metadata=_metadata(),
            db=session,
        )

        db_result = await session.execute(
            select(AdminResetRequest).where(AdminResetRequest.id == result.reset_request_id)
        )
        reset_request = db_result.scalar_one()
        reset_request.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

        with pytest.raises(ValueError, match="expired"):
            await admin_auth_service.consume_reset_token(
                token=result.reset_token,
                new_password="NewSecurePassword123!",
                request_metadata=_metadata(),
                db=session,
            )


@pytest.mark.asyncio
async def test_cannot_reset_nonexistent_or_invalid_targets(
    session_maker: async_sessionmaker[AsyncSession],
    admin_user_factory,
) -> None:
    admin = admin_user_factory()
    fake_user_id = uuid4()
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

        with pytest.raises(ValueError, match="not found"):
            await admin_auth_service.issue_password_reset(
                admin_user_id=admin.id,
                target_user_id=fake_user_id,
                request_metadata=_metadata(),
                db=session,
            )

        with pytest.raises(ValueError, match="Cannot reset your own password"):
            await admin_auth_service.issue_password_reset(
                admin_user_id=admin.id,
                target_user_id=admin.id,
                request_metadata=_metadata(),
                db=session,
            )

        with pytest.raises(ValueError, match="NHI accounts"):
            await admin_auth_service.issue_password_reset(
                admin_user_id=admin.id,
                target_user_id=nhi_user.id,
                request_metadata=_metadata(),
                db=session,
            )
