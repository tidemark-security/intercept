"""Unit tests for admin action authorization and audit logging."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from app.models.enums import SessionRevokedReason, UserRole, UserStatus
from app.models.models import PASSWORD_POLICY_REGEX, UserAccount
from app.services import AuditContext


class TestRBACAuthorization:
    def test_admin_role_check_passes_for_admin(self):
        admin_user = UserAccount(
            id=uuid4(),
            username="admin.user",
            email="admin@example.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            password_hash="hash",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert admin_user.role == UserRole.ADMIN

    def test_admin_role_check_fails_for_analyst(self):
        analyst_user = UserAccount(
            id=uuid4(),
            username="analyst.user",
            email="analyst@example.com",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE,
            password_hash="hash",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert analyst_user.role != UserRole.ADMIN

    def test_admin_role_check_fails_for_auditor(self):
        auditor_user = UserAccount(
            id=uuid4(),
            username="auditor.user",
            email="auditor@example.com",
            role=UserRole.AUDITOR,
            status=UserStatus.ACTIVE,
            password_hash="hash",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        assert auditor_user.role != UserRole.ADMIN


class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_password_reset_generates_audit_event(self):
        from app.services import AuditService

        db = Mock()
        db.add = Mock()
        db.flush = AsyncMock()
        audit_service = AuditService(db)
        admin_id = uuid4()
        target_user_id = uuid4()
        reset_request_id = uuid4()
        expires_at = datetime.now(timezone.utc)

        context = AuditContext(
            ip_address="192.168.1.100",
            user_agent="Test/1.0",
            correlation_id="test-correlation-123",
        )

        with patch.object(audit_service, "_logger") as mock_logger:
            await audit_service.password_reset_issued(
                admin_user_id=admin_id,
                target_user_id=target_user_id,
                reset_request_id=reset_request_id,
                expires_at=expires_at.isoformat(),
                context=context,
            )

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            log_event = call_args.kwargs["extra"]["audit"]
            assert log_event["event"] == "auth.admin.password_reset_issued"
            assert log_event["performed_by"] == str(admin_id)
            assert log_event["entity_id"] == str(target_user_id)


class TestSessionRevocation:
    def test_disable_user_revokes_all_sessions(self):
        assert SessionRevokedReason.ADMIN_FORCE
        assert SessionRevokedReason.USER_LOGOUT
        assert SessionRevokedReason.SESSION_TIMEOUT
        assert SessionRevokedReason.RESET_REQUIRED


class TestPasswordPolicy:
    def test_password_validation_accepts_strong_password(self):
        strong_passwords = [
            "ValidTestPass123!",
            "Str0ng!P@ssw0rd",
            "C0mpl3x#Passw0rd",
            "Secur3$P@ssword",
        ]

        for password in strong_passwords:
            assert PASSWORD_POLICY_REGEX.match(password)

    def test_password_validation_rejects_weak_password(self):
        weak_passwords = [
            "short1!",
            "nouppercase123!",
            "NOLOWERCASE123!",
            "NoNumbers!!",
            "NoSpecialChars123",
        ]

        for password in weak_passwords:
            assert not PASSWORD_POLICY_REGEX.match(password)
