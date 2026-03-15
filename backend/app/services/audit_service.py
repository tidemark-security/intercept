from __future__ import annotations

"""Persisted audit logging helpers."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.models import AuditLog, AuditLogRead


logger = logging.getLogger("app.audit")


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


def _serialize_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value

    def default_serializer(item: Any) -> Any:
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, UUID):
            return str(item)
        if hasattr(item, "value"):
            return item.value
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        return str(item)

    return json.dumps(value, default=default_serializer, sort_keys=True)


class AuditService:
    """Persist audit rows to PostgreSQL and emit structured logs."""

    def __init__(self, db: AsyncSession, *, logger_: Optional[logging.Logger] = None) -> None:
        self._db = db
        self._logger = logger_ or logger

    @staticmethod
    def compute_changes(old_value: Optional[str], new_value: Optional[str]) -> list[dict[str, Any]]:
        return AuditLogRead.compute_changes(old_value, new_value)

    async def get_audit_logs(
        self,
        *,
        event_type: Optional[list[str]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        performed_by: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Page[AuditLog]:
        """Return persisted audit logs with optional filtering and pagination."""

        query = select(AuditLog).order_by(col(AuditLog.performed_at).desc())
        filters = []

        if event_type:
            filters.append(col(AuditLog.event_type).in_(event_type))

        if entity_type:
            filters.append(col(AuditLog.entity_type) == entity_type)

        if entity_id:
            filters.append(col(AuditLog.entity_id) == entity_id)

        if performed_by:
            filters.append(col(AuditLog.performed_by) == performed_by)

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                filters.append(col(AuditLog.performed_at) >= start_dt)
            except ValueError:
                logger.warning("Invalid audit log start_date format: %s", start_date)

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                filters.append(col(AuditLog.performed_at) <= end_dt)
            except ValueError:
                logger.warning("Invalid audit log end_date format: %s", end_date)

        if search:
            search_pattern = f"%{search}%"
            filters.append(
                or_(
                    col(AuditLog.event_type).ilike(search_pattern),
                    cast(AuditLog.description, String).ilike(search_pattern),  # type: ignore[arg-type]
                    cast(AuditLog.entity_id, String).ilike(search_pattern),  # type: ignore[arg-type]
                    cast(AuditLog.performed_by, String).ilike(search_pattern),  # type: ignore[arg-type]
                )
            )

        if filters:
            query = query.where(and_(*filters))

        return await apaginate(self._db, query)

    async def log_event(
        self,
        *,
        event_type: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        item_id: Optional[str] = None,
        description: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        performed_by: Optional[str] = None,
        context: Optional[AuditContext] = None,
        extra_payload: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        audit_context = context or AuditContext()
        audit_log = AuditLog(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            item_id=item_id,
            description=description,
            old_value=_serialize_value(old_value),
            new_value=_serialize_value(new_value),
            performed_by=performed_by,
            ip_address=audit_context.ip_address,
            user_agent=audit_context.user_agent,
            correlation_id=audit_context.correlation_id,
        )
        self._db.add(audit_log)
        await self._db.flush()

        payload = {
            "event": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "item_id": item_id,
            "description": description,
            "performed_by": performed_by,
            "performed_at": audit_log.performed_at.isoformat(),
        }
        payload.update(audit_context.to_payload())
        if extra_payload:
            payload.update(extra_payload)
        self._logger.info(event_type, extra={"audit": payload})
        return audit_log

    async def log_entity_updated(
        self,
        *,
        entity_type: str,
        entity_id: int | str,
        before: dict[str, Any],
        after: dict[str, Any],
        user: str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="entity.updated",
            entity_type=entity_type,
            entity_id=str(entity_id),
            description=f"{entity_type} updated",
            old_value=before,
            new_value=after,
            performed_by=user,
            context=context,
        )

    async def log_entity_deleted(
        self,
        *,
        entity_type: str,
        entity_id: int | str,
        user: str,
        old_value: Any = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="entity.deleted",
            entity_type=entity_type,
            entity_id=str(entity_id),
            description=f"{entity_type} deleted",
            old_value=old_value,
            performed_by=user,
            context=context,
        )

    async def log_timeline_item_added(
        self,
        *,
        entity_type: str,
        entity_id: int | str,
        item_id: str,
        item_type: str,
        user: str,
        new_value: Any = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="timeline.item.added",
            entity_type=entity_type,
            entity_id=str(entity_id),
            item_id=item_id,
            description=f"Timeline item added: {item_type}",
            new_value=new_value,
            performed_by=user,
            context=context,
            extra_payload={"item_type": item_type},
        )

    async def log_timeline_item_deleted(
        self,
        *,
        entity_type: str,
        entity_id: int | str,
        item_id: str,
        item_type: str,
        user: str,
        old_value: Any = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="timeline.item.deleted",
            entity_type=entity_type,
            entity_id=str(entity_id),
            item_id=item_id,
            description=f"Timeline item deleted: {item_type}",
            old_value=old_value,
            performed_by=user,
            context=context,
            extra_payload={"item_type": item_type},
        )

    async def log_timeline_edit(
        self,
        *,
        entity_type: str,
        entity_id: int | str,
        item_id: str,
        item_type: str,
        before: dict[str, Any],
        after: dict[str, Any],
        user: str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="timeline.item.updated",
            entity_type=entity_type,
            entity_id=str(entity_id),
            item_id=item_id,
            description=f"Timeline item updated: {item_type}",
            old_value=before,
            new_value=after,
            performed_by=user,
            context=context,
            extra_payload={"item_type": item_type},
        )

    async def login_success(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.login.success",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="User login succeeded",
            new_value={
                "username": kwargs["username"],
                "role": getattr(kwargs["role"], "value", kwargs["role"]),
                "session_id": str(kwargs["session_id"]),
                "issued_at": kwargs["issued_at"],
                "expires_at": kwargs["expires_at"],
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def login_failure(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.login.failure",
            entity_type="user",
            description="User login failed",
            new_value={
                "username": kwargs["username"],
                "role": getattr(kwargs.get("role"), "value", kwargs.get("role")),
                "reason": kwargs["reason"],
                "attempts_remaining": kwargs.get("attempts_remaining"),
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def logout(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.logout",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="User logged out",
            new_value={
                "session_id": str(kwargs["session_id"]),
                "reason": getattr(kwargs["reason"], "value", kwargs["reason"]),
            },
            context=kwargs.get("context"),
        )

    async def oidc_login_success(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.login.success",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="OIDC login succeeded",
            new_value={
                "username": kwargs["username"],
                "role": getattr(kwargs["role"], "value", kwargs["role"]),
                "oidc_issuer": kwargs["oidc_issuer"],
                "oidc_subject": kwargs["oidc_subject"],
                "session_id": str(kwargs["session_id"]),
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def oidc_login_failure(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.login.failure",
            entity_type="user",
            description="OIDC login failed",
            new_value={
                "reason": kwargs["reason"],
                "oidc_issuer": kwargs.get("oidc_issuer"),
                "username": kwargs.get("username"),
            },
            performed_by=kwargs.get("username"),
            context=kwargs.get("context"),
        )

    async def oidc_account_linked(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.account_linked",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="OIDC account linked",
            new_value={
                "username": kwargs["username"],
                "oidc_issuer": kwargs["oidc_issuer"],
                "oidc_subject": kwargs["oidc_subject"],
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def oidc_account_provisioned(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.account_provisioned",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="OIDC account provisioned",
            new_value={
                "username": kwargs["username"],
                "role": getattr(kwargs["role"], "value", kwargs["role"]),
                "oidc_issuer": kwargs["oidc_issuer"],
                "oidc_subject": kwargs["oidc_subject"],
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def account_locked(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.lockout",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="Account locked",
            new_value={
                "username": kwargs["username"],
                "role": getattr(kwargs["role"], "value", kwargs["role"]),
                "lockout_expires_at": kwargs["lockout_expires_at"],
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def user_created(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.user_created",
            entity_type="user",
            entity_id=str(kwargs["target_user_id"]),
            description="Admin created user",
            new_value={
                "admin_user_id": str(kwargs["admin_user_id"]),
                "username": kwargs["username"],
                "email": kwargs["email"],
                "role": getattr(kwargs["role"], "value", kwargs["role"]),
            },
            performed_by=str(kwargs["admin_user_id"]),
            context=kwargs.get("context"),
        )

    async def user_status_changed(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.user_status_changed",
            entity_type="user",
            entity_id=str(kwargs["target_user_id"]),
            description="Admin changed user status",
            old_value={"status": getattr(kwargs["old_status"], "value", kwargs["old_status"])},
            new_value={"status": getattr(kwargs["new_status"], "value", kwargs["new_status"])},
            performed_by=str(kwargs["admin_user_id"]),
            context=kwargs.get("context"),
        )

    async def user_updated(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.user_updated",
            entity_type="user",
            entity_id=str(kwargs["target_user_id"]),
            description="Admin updated user",
            old_value=kwargs["old_value"],
            new_value=kwargs["new_value"],
            performed_by=str(kwargs["admin_user_id"]),
            context=kwargs.get("context"),
        )

    async def password_reset_issued(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.password_reset_issued",
            entity_type="user",
            entity_id=str(kwargs["target_user_id"]),
            description="Admin issued password reset",
            new_value={
                "admin_user_id": str(kwargs["admin_user_id"]),
                "reset_request_id": str(kwargs["reset_request_id"]),
                "delivery_channel": kwargs["delivery_channel"],
            },
            performed_by=str(kwargs["admin_user_id"]),
            context=kwargs.get("context"),
        )

    async def admin_reset_issued(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.reset_issued",
            entity_type="user",
            entity_id=str(kwargs["target_user_id"]),
            description="Admin reset issued",
            new_value={
                "admin_id": str(kwargs["admin_id"]),
                "admin_username": kwargs["admin_username"],
                "target_username": kwargs["target_username"],
                "delivery_channel": getattr(kwargs["delivery_channel"], "value", kwargs["delivery_channel"]),
                "reset_request_id": str(kwargs["reset_request_id"]),
                "expires_at": kwargs["expires_at"],
            },
            performed_by=kwargs["admin_username"],
            context=kwargs.get("context"),
        )

    async def password_changed(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.password_changed",
            entity_type="user",
            entity_id=str(kwargs["user_id"]),
            description="User password changed",
            new_value={"username": kwargs["username"], "was_forced": kwargs["was_forced"]},
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def api_key_created(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.created",
            entity_type="api_key",
            entity_id=str(kwargs["api_key_id"]),
            description="API key created",
            new_value={
                "user_id": str(kwargs["user_id"]),
                "username": kwargs["username"],
                "api_key_name": kwargs["api_key_name"],
                "api_key_prefix": kwargs["api_key_prefix"],
                "expires_at": kwargs["expires_at"],
                "created_by_user_id": str(kwargs["created_by_user_id"]) if kwargs.get("created_by_user_id") else None,
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def api_key_revoked(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.revoked",
            entity_type="api_key",
            entity_id=str(kwargs["api_key_id"]),
            description="API key revoked",
            new_value={
                "user_id": str(kwargs["user_id"]),
                "username": kwargs["username"],
                "api_key_name": kwargs["api_key_name"],
                "api_key_prefix": kwargs["api_key_prefix"],
                "revoked_by_user_id": str(kwargs["revoked_by_user_id"]) if kwargs.get("revoked_by_user_id") else None,
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def api_key_auth_success(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.auth_success",
            entity_type="api_key",
            entity_id=str(kwargs["api_key_id"]),
            description="API key authenticated successfully",
            new_value={
                "user_id": str(kwargs["user_id"]),
                "username": kwargs["username"],
                "api_key_prefix": kwargs["api_key_prefix"],
            },
            performed_by=kwargs["username"],
            context=kwargs.get("context"),
        )

    async def api_key_auth_failure(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.auth_failure",
            entity_type="api_key",
            description="API key authentication failed",
            new_value={"reason": kwargs["reason"], "api_key_prefix": kwargs.get("api_key_prefix")},
            context=kwargs.get("context"),
        )

    async def nhi_account_created(self, **kwargs: Any) -> AuditLog:
        return await self.log_event(
            event_type="auth.nhi.account_created",
            entity_type="user",
            entity_id=str(kwargs["nhi_user_id"]),
            description="NHI account created",
            new_value={
                "admin_user_id": str(kwargs["admin_user_id"]),
                "admin_username": kwargs["admin_username"],
                "nhi_username": kwargs["nhi_username"],
                "role": kwargs["role"],
                "initial_api_key_id": str(kwargs["initial_api_key_id"]),
                "initial_api_key_prefix": kwargs["initial_api_key_prefix"],
            },
            performed_by=kwargs["admin_username"],
            context=kwargs.get("context"),
        )


def get_audit_service(db: AsyncSession) -> AuditService:
    return AuditService(db)


__all__ = ["AuditContext", "AuditService", "get_audit_service"]
