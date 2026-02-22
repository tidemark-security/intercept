# Models package - using SQLModel for unified database and API models

from .enums import CaseStatus, Priority, AlertStatus
from .models import (
    # Database models
    Case,
    Alert,
    CaseAuditLog,
    UserAccount,
    AuthSession,
    AdminResetRequest,
    PasskeyCredential,
    WebAuthnChallenge,

    # API schemas
    CaseBase,
    CaseCreate,
    CaseUpdate,
    CaseRead,
    CaseReadWithAlerts,
    AlertBase,
    AlertCreate,
    AlertUpdate,
    AlertRead,
    AlertReadWithCase,
    AlertTriageRequest,
    CaseAuditLogRead,
    UserAccountBase,
    UserAccountRead,
    UserAccountCreate,
    AuthSessionBase,
    AuthSessionRead,
    AdminResetRequestBase,
    AdminResetRequestRead,
    PasswordChangeRequest,
    PasskeyCredentialRead,
)

__all__ = [
    # Enums
    "CaseStatus", "Priority", "AlertStatus",
    
    # Database models
    "Case",
    "Alert",
    "CaseAuditLog",
    "UserAccount",
    "AuthSession",
    "AdminResetRequest",
    "PasskeyCredential",
    "WebAuthnChallenge",
    
    # API schemas
    "CaseBase",
    "CaseCreate",
    "CaseUpdate",
    "CaseRead",
    "CaseReadWithAlerts",
    "AlertBase",
    "AlertCreate",
    "AlertUpdate",
    "AlertRead",
    "AlertReadWithCase",
    "AlertTriageRequest",
    "CaseAuditLogRead",
    "UserAccountBase",
    "UserAccountRead",
    "UserAccountCreate",
    "AuthSessionBase",
    "AuthSessionRead",
    "AdminResetRequestBase",
    "AdminResetRequestRead",
    "PasswordChangeRequest",
    "PasskeyCredentialRead",
]
