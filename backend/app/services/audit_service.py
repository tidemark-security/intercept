from __future__ import annotations

"""Structured audit helpers for authentication flows."""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Optional
from uuid import UUID

from app.models.enums import ResetDeliveryChannel, SessionRevokedReason, UserRole, UserStatus


logger = logging.getLogger("app.audit.auth")


@dataclass(slots=True)
class AuditContext:
    """Optional correlation metadata for audit log entries."""

    correlation_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.correlation_id:
            payload["correlation_id"] = self.correlation_id
        if self.ip_address:
            payload["ip_address"] = self.ip_address
        if self.user_agent:
            payload["user_agent"] = self.user_agent
        return payload


class AuthAuditService:
    """Emit structured audit logs and metrics for authentication events."""

    def __init__(self, *, logger_: Optional[logging.Logger] = None) -> None:
        self._logger = logger_ or logger

    # ------------------------------------------------------------------
    # Login / logout events
    # ------------------------------------------------------------------

    def login_success(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole,
        session_id: UUID,
        issued_at: datetime,
        expires_at: datetime,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record a successful login event."""

        payload = {
            "event": "auth.login.success",
            "user_id": str(user_id),
            "username": username,
            "role": role.value,
            "session_id": str(session_id),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def login_failure(
        self,
        *,
        username: str,
        role: Optional[UserRole],
        reason: str,
        attempts_remaining: Optional[int],
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record a failed login event."""

        payload = {
            "event": "auth.login.failure",
            "username": username,
            "role": role.value if role else None,
            "reason": reason,
            "attempts_remaining": attempts_remaining,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.warning(payload["event"], extra={"auth": payload})

    def logout(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        reason: SessionRevokedReason,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record an explicit session revocation."""

        payload = {
            "event": "auth.logout",
            "user_id": str(user_id),
            "session_id": str(session_id),
            "reason": reason.value,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def oidc_login_success(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole,
        oidc_issuer: str,
        oidc_subject: str,
        session_id: UUID,
        context: Optional[AuditContext] = None,
    ) -> None:
        payload = {
            "event": "auth.oidc.login.success",
            "user_id": str(user_id),
            "username": username,
            "role": role.value,
            "oidc_issuer": oidc_issuer,
            "oidc_subject": oidc_subject,
            "session_id": str(session_id),
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def oidc_login_failure(
        self,
        *,
        reason: str,
        oidc_issuer: Optional[str],
        username: Optional[str] = None,
        context: Optional[AuditContext] = None,
    ) -> None:
        payload = {
            "event": "auth.oidc.login.failure",
            "reason": reason,
            "oidc_issuer": oidc_issuer,
            "username": username,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.warning(payload["event"], extra={"auth": payload})

    def oidc_account_linked(
        self,
        *,
        user_id: UUID,
        username: str,
        oidc_issuer: str,
        oidc_subject: str,
        context: Optional[AuditContext] = None,
    ) -> None:
        payload = {
            "event": "auth.oidc.account_linked",
            "user_id": str(user_id),
            "username": username,
            "oidc_issuer": oidc_issuer,
            "oidc_subject": oidc_subject,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def oidc_account_provisioned(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole,
        oidc_issuer: str,
        oidc_subject: str,
        context: Optional[AuditContext] = None,
    ) -> None:
        payload = {
            "event": "auth.oidc.account_provisioned",
            "user_id": str(user_id),
            "username": username,
            "role": role.value,
            "oidc_issuer": oidc_issuer,
            "oidc_subject": oidc_subject,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    # ------------------------------------------------------------------
    # Security protections
    # ------------------------------------------------------------------

    def account_locked(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole,
        lockout_expires_at: datetime,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record an account lockout event."""

        payload = {
            "event": "auth.lockout",
            "user_id": str(user_id),
            "username": username,
            "role": role.value,
            "lockout_expires_at": lockout_expires_at.isoformat(),
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.warning(payload["event"], extra={"auth": payload})

    # ------------------------------------------------------------------
    # Administrative actions
    # ------------------------------------------------------------------

    def user_created(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        username: str,
        email: str,
        role: UserRole,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record a user creation event by an administrator."""

        payload = {
            "event": "auth.admin.user_created",
            "admin_user_id": str(admin_user_id),
            "target_user_id": str(target_user_id),
            "username": username,
            "email": email,
            "role": role.value,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def user_status_changed(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        old_status: UserStatus,
        new_status: UserStatus,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record a user status change by an administrator."""

        payload = {
            "event": "auth.admin.user_status_changed",
            "admin_user_id": str(admin_user_id),
            "target_user_id": str(target_user_id),
            "old_status": old_status.value,
            "new_status": new_status.value,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def password_reset_issued(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        reset_request_id: UUID,
        delivery_channel: str,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record an administrator-initiated password reset."""

        payload = {
            "event": "auth.admin.password_reset_issued",
            "admin_user_id": str(admin_user_id),
            "target_user_id": str(target_user_id),
            "reset_request_id": str(reset_request_id),
            "delivery_channel": delivery_channel,
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def admin_reset_issued(
        self,
        *,
        admin_id: UUID,
        admin_username: str,
        target_user_id: UUID,
        target_username: str,
        delivery_channel: ResetDeliveryChannel,
        reset_request_id: UUID,
        expires_at: datetime,
        context: Optional[AuditContext] = None,
    ) -> None:
        """Record an administrator-initiated password reset."""

        payload = {
            "event": "auth.admin.reset_issued",
            "admin_id": str(admin_id),
            "admin_username": admin_username,
            "target_user_id": str(target_user_id),
            "target_username": target_username,
            "delivery_channel": delivery_channel.value,
            "reset_request_id": str(reset_request_id),
            "expires_at": expires_at.isoformat(),
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})

    def password_changed(
        self,
        *,
        user_id: UUID,
        username: str,
        was_forced: bool,
        context: Optional[AuditContext] = None,
    ) -> None:
        """
        Log user password change completion.

        Args:
            user_id: ID of the user who changed their password
            username: Username of the user
            was_forced: Whether password change was mandatory (must_change_password flag)
            context: Optional metadata for the audit log
        """

        payload = {
            "event": "auth.password_changed",
            "user_id": str(user_id),
            "username": username,
            "was_forced": was_forced,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        payload.update((context or AuditContext()).to_payload())

        self._logger.info(payload["event"], extra={"auth": payload})


class TimelineAuditService:
    """Emit structured audit logs for timeline item operations."""
    
    def __init__(self, *, logger_: Optional[logging.Logger] = None) -> None:
        self._logger = logger_ or logger
    
    def log_timeline_edit(
        self,
        *,
        entity_type: str,
        entity_id: int,
        item_id: str,
        item_type: str,
        before: dict[str, Any],
        after: dict[str, Any],
        user: str,
        context: Optional[AuditContext] = None,
    ) -> None:
        """
        Log timeline item edit with field-level change tracking.
        
        Args:
            entity_type: Type of entity (alert, case)
            entity_id: ID of the entity containing the timeline
            item_id: ID of the timeline item being edited
            item_type: Type of timeline item (note, task, observable, etc.)
            before: Item state before edit
            after: Item state after edit
            user: Username who performed the edit
            context: Optional audit context
        """
        # Calculate field differences
        changes = []
        skip_fields = {'id', 'created_by', 'created_at', 'updated_by', 'updated_at', 'replies'}
        all_fields = set(before.keys()) | set(after.keys())
        
        for field in all_fields:
            if field in skip_fields:
                continue
            
            before_value = before.get(field)
            after_value = after.get(field)
            
            if before_value != after_value:
                changes.append({
                    "field": field,
                    "before": before_value,
                    "after": after_value,
                })
        
        payload = {
            "event": "timeline.item.updated",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "item_id": item_id,
            "item_type": item_type,
            "user": user,
            "changes": changes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        payload.update((context or AuditContext()).to_payload())
        
        self._logger.info(payload["event"], extra={"timeline_audit": payload})


__all__ = [
    "AuditContext",
    "AuthAuditService",
    "TimelineAuditService",
]
