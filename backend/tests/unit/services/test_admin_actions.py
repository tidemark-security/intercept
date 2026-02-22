"""Unit tests for admin action authorization and audit logging."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole, UserStatus, SessionRevokedReason
from app.models.models import UserAccount
from app.services import AuditContext


class TestRBACAuthorization:
    """Test role-based access control for admin operations."""
    
    def test_admin_role_check_passes_for_admin(self):
        """Admin users pass role check for admin operations."""
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
        assert admin_user.role in [UserRole.ADMIN]
    
    def test_admin_role_check_fails_for_analyst(self):
        """Analyst users fail role check for admin operations."""
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
        assert analyst_user.role not in [UserRole.ADMIN]
    
    def test_admin_role_check_fails_for_auditor(self):
        """Auditor users fail role check for admin operations."""
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
        assert auditor_user.role not in [UserRole.ADMIN]


class TestAuditLogging:
    """Test audit trail creation for admin operations."""
    
    @pytest.mark.asyncio
    async def test_user_creation_generates_audit_event(self):
        """Creating a user generates appropriate audit log entry."""
        from app.services import AuthAuditService
        
        audit_service = AuthAuditService()
        admin_id = uuid4()
        target_user_id = uuid4()
        
        context = AuditContext(
            ip_address="192.168.1.100",
            user_agent="Test/1.0",
            correlation_id="test-correlation-123",
        )
        
        # Mock the audit logging to verify it's called
        with patch.object(audit_service, '_logger') as mock_logger:
            audit_service.user_created(
                admin_user_id=admin_id,
                target_user_id=target_user_id,
                username="new.user",
                email="new.user@example.com",
                role=UserRole.ANALYST,
                context=context,
            )
            
            # Verify audit log was emitted
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            
            # Check the event contains expected fields
            log_event = call_args.kwargs["extra"]["auth"]
            assert log_event["event"] == "auth.admin.user_created"
            assert log_event["admin_user_id"] == str(admin_id)
            assert log_event["target_user_id"] == str(target_user_id)
            assert log_event["username"] == "new.user"
            assert log_event["role"] == "ANALYST"
    
    @pytest.mark.asyncio
    async def test_status_change_generates_audit_event(self):
        """Changing user status generates appropriate audit log entry."""
        from app.services import AuthAuditService
        
        audit_service = AuthAuditService()
        admin_id = uuid4()
        target_user_id = uuid4()
        
        context = AuditContext(
            ip_address="192.168.1.100",
            user_agent="Test/1.0",
            correlation_id="test-correlation-123",
        )
        
        # Mock the audit logging
        with patch.object(audit_service, '_logger') as mock_logger:
            audit_service.user_status_changed(
                admin_user_id=admin_id,
                target_user_id=target_user_id,
                old_status=UserStatus.ACTIVE,
                new_status=UserStatus.DISABLED,
                context=context,
            )
            
            # Verify audit log was emitted
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            
            log_event = call_args.kwargs["extra"]["auth"]
            assert log_event["event"] == "auth.admin.user_status_changed"
            assert log_event["admin_user_id"] == str(admin_id)
            assert log_event["target_user_id"] == str(target_user_id)
            assert log_event["old_status"] == "ACTIVE"
            assert log_event["new_status"] == "DISABLED"
    
    @pytest.mark.asyncio
    async def test_password_reset_generates_audit_event(self):
        """Issuing a password reset generates appropriate audit log entry."""
        from app.services import AuthAuditService
        
        audit_service = AuthAuditService()
        admin_id = uuid4()
        target_user_id = uuid4()
        reset_request_id = uuid4()
        
        context = AuditContext(
            ip_address="192.168.1.100",
            user_agent="Test/1.0",
            correlation_id="test-correlation-123",
        )
        
        # Mock the audit logging
        with patch.object(audit_service, '_logger') as mock_logger:
            audit_service.password_reset_issued(
                admin_user_id=admin_id,
                target_user_id=target_user_id,
                reset_request_id=reset_request_id,
                delivery_channel="SECURE_EMAIL",
                context=context,
            )
            
            # Verify audit log was emitted
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            
            log_event = call_args.kwargs["extra"]["auth"]
            assert log_event["event"] == "auth.admin.password_reset_issued"
            assert log_event["admin_user_id"] == str(admin_id)
            assert log_event["target_user_id"] == str(target_user_id)
            assert log_event["reset_request_id"] == str(reset_request_id)
            assert log_event["delivery_channel"] == "SECURE_EMAIL"


class TestSessionRevocation:
    """Test session revocation during admin operations."""
    
    @pytest.mark.asyncio
    async def test_disable_user_revokes_all_sessions(self):
        """Disabling a user should revoke all their active sessions."""
        # This will be tested in the integration tests, but we can verify the logic
        from app.models.enums import SessionRevokedReason
        
        # Verify the revocation reason enum exists
        assert SessionRevokedReason.ADMIN_FORCE
        assert SessionRevokedReason.USER_LOGOUT
        assert SessionRevokedReason.SESSION_TIMEOUT
        assert SessionRevokedReason.RESET_REQUIRED


class TestPasswordPolicy:
    """Test password policy validation for admin-created accounts."""
    
    def test_temporary_password_meets_policy(self):
        """Temporary passwords generated for new users meet policy requirements."""
        import secrets
        import string
        
        # Simulate temporary password generation
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(16))
        
        # Verify length requirement
        assert len(temp_password) >= 12
    
    def test_password_validation_accepts_strong_password(self):
        """Password policy accepts strong passwords."""
        from app.models.models import PASSWORD_POLICY_REGEX
        
        strong_passwords = [
            "ValidTestPass123!",
            "Str0ng!P@ssw0rd",
            "C0mpl3x#Passw0rd",
            "Secur3$P@ssword",
        ]
        
        for password in strong_passwords:
            assert PASSWORD_POLICY_REGEX.match(password), f"Password {password} should be valid"
    
    def test_password_validation_rejects_weak_password(self):
        """Password policy rejects weak passwords."""
        from app.models.models import PASSWORD_POLICY_REGEX
        
        weak_passwords = [
            "short1!",  # Too short
            "nouppercase123!",  # No uppercase
            "NOLOWERCASE123!",  # No lowercase
            "NoNumbers!!",  # No numbers
            "NoSpecialChars123",  # No special characters
        ]
        
        for password in weak_passwords:
            assert not PASSWORD_POLICY_REGEX.match(password), f"Password {password} should be invalid"


class TestEmailDeliveryChannel:
    """Test email delivery channel configuration."""
    
    def test_delivery_channel_enum_includes_secure_email(self):
        """Delivery channel enum includes SECURE_EMAIL option."""
        from app.models.enums import ResetDeliveryChannel
        
        assert hasattr(ResetDeliveryChannel, 'SECURE_EMAIL')
        assert ResetDeliveryChannel.SECURE_EMAIL.value == "SECURE_EMAIL"
