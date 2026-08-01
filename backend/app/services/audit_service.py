"""Persisted audit logging helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col

from app.models.enums import SessionRevokedReason, UserRole, UserStatus
from app.models.models import AuditLog
from app.services.date_filter_utils import parse_datetime_filter


logger = logging.getLogger("app.audit")

AuditSessionFactory = Callable[[], AsyncSession]


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


def _json_default(item: Any) -> Any:
    if isinstance(item, datetime):
        return item.isoformat()
    if isinstance(item, UUID):
        return str(item)
    if hasattr(item, "value"):
        return item.value
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return str(item)


def _serialize_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=_json_default, sort_keys=True)


class AuditService:
    """Persist audit rows to PostgreSQL and emit structured logs."""

    def __init__(self, db: AsyncSession, *, logger_: Optional[logging.Logger] = None) -> None:
        self._db = db
        self._logger = logger_ or logger

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

        start_dt = parse_datetime_filter(
            start_date,
            parameter="audit log start_date",
        )
        if start_dt is not None:
            filters.append(col(AuditLog.performed_at) >= start_dt)

        end_dt = parse_datetime_filter(
            end_date,
            parameter="audit log end_date",
        )
        if end_dt is not None:
            filters.append(col(AuditLog.performed_at) <= end_dt)

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
        item_type: Optional[str] = None,
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
        if item_type is not None:
            payload["item_type"] = item_type
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
            item_type=item_type,
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
            item_type=item_type,
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
            item_type=item_type,
        )

    async def login_success(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole | str,
        session_id: UUID,
        issued_at: datetime,
        expires_at: datetime,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.login.success",
            entity_type="user",
            entity_id=str(user_id),
            description="User login succeeded",
            new_value={
                "username": username,
                "role": getattr(role, "value", role),
                "session_id": str(session_id),
                "issued_at": issued_at,
                "expires_at": expires_at,
            },
            performed_by=username,
            context=context,
        )

    async def login_failure(
        self,
        *,
        username: str,
        reason: str,
        role: Optional[UserRole | str] = None,
        attempts_remaining: Optional[int] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.login.failure",
            entity_type="user",
            description="User login failed",
            new_value={
                "username": username,
                "role": getattr(role, "value", role),
                "reason": reason,
                "attempts_remaining": attempts_remaining,
            },
            performed_by=username,
            context=context,
        )

    async def logout(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        reason: SessionRevokedReason | str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.logout",
            entity_type="user",
            entity_id=str(user_id),
            description="User logged out",
            new_value={
                "session_id": str(session_id),
                "reason": getattr(reason, "value", reason),
            },
            context=context,
        )

    async def oidc_login_success(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole | str,
        oidc_issuer: str,
        oidc_subject: str,
        session_id: UUID,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.login.success",
            entity_type="user",
            entity_id=str(user_id),
            description="OIDC login succeeded",
            new_value={
                "username": username,
                "role": getattr(role, "value", role),
                "oidc_issuer": oidc_issuer,
                "oidc_subject": oidc_subject,
                "session_id": str(session_id),
            },
            performed_by=username,
            context=context,
        )

    async def oidc_login_failure(
        self,
        *,
        reason: str,
        oidc_issuer: Optional[str] = None,
        username: Optional[str] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.login.failure",
            entity_type="user",
            description="OIDC login failed",
            new_value={
                "reason": reason,
                "oidc_issuer": oidc_issuer,
                "username": username,
            },
            performed_by=username,
            context=context,
        )

    async def oidc_account_linked(
        self,
        *,
        user_id: UUID,
        username: str,
        oidc_issuer: str,
        oidc_subject: str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.account_linked",
            entity_type="user",
            entity_id=str(user_id),
            description="OIDC account linked",
            new_value={
                "username": username,
                "oidc_issuer": oidc_issuer,
                "oidc_subject": oidc_subject,
            },
            performed_by=username,
            context=context,
        )

    async def oidc_account_provisioned(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole | str,
        oidc_issuer: str,
        oidc_subject: str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.oidc.account_provisioned",
            entity_type="user",
            entity_id=str(user_id),
            description="OIDC account provisioned",
            new_value={
                "username": username,
                "role": getattr(role, "value", role),
                "oidc_issuer": oidc_issuer,
                "oidc_subject": oidc_subject,
            },
            performed_by=username,
            context=context,
        )

    async def account_locked(
        self,
        *,
        user_id: UUID,
        username: str,
        role: UserRole | str,
        lockout_expires_at: datetime,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.lockout",
            entity_type="user",
            entity_id=str(user_id),
            description="Account locked",
            new_value={
                "username": username,
                "role": getattr(role, "value", role),
                "lockout_expires_at": lockout_expires_at,
            },
            performed_by=username,
            context=context,
        )

    async def user_created(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        username: str,
        email: Optional[str],
        role: UserRole | str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.user_created",
            entity_type="user",
            entity_id=str(target_user_id),
            description="Admin created user",
            new_value={
                "admin_user_id": str(admin_user_id),
                "username": username,
                "email": email,
                "role": getattr(role, "value", role),
            },
            performed_by=str(admin_user_id),
            context=context,
        )

    async def user_status_changed(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        old_status: UserStatus | str,
        new_status: UserStatus | str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.user_status_changed",
            entity_type="user",
            entity_id=str(target_user_id),
            description="Admin changed user status",
            old_value={"status": getattr(old_status, "value", old_status)},
            new_value={"status": getattr(new_status, "value", new_status)},
            performed_by=str(admin_user_id),
            context=context,
        )

    async def user_updated(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        old_value: dict[str, Any],
        new_value: dict[str, Any],
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.user_updated",
            entity_type="user",
            entity_id=str(target_user_id),
            description="Admin updated user",
            old_value=old_value,
            new_value=new_value,
            performed_by=str(admin_user_id),
            context=context,
        )

    async def password_reset_issued(
        self,
        *,
        admin_user_id: UUID,
        target_user_id: UUID,
        reset_request_id: UUID,
        expires_at: datetime,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.admin.password_reset_issued",
            entity_type="user",
            entity_id=str(target_user_id),
            description="Admin issued password reset",
            new_value={
                "admin_user_id": str(admin_user_id),
                "reset_request_id": str(reset_request_id),
                "expires_at": expires_at,
            },
            performed_by=str(admin_user_id),
            context=context,
        )

    async def password_changed(
        self,
        *,
        user_id: UUID,
        username: str,
        was_forced: bool,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.password_changed",
            entity_type="user",
            entity_id=str(user_id),
            description="User password changed",
            new_value={"username": username, "was_forced": was_forced},
            performed_by=username,
            context=context,
        )

    async def api_key_created(
        self,
        *,
        user_id: UUID,
        username: str,
        api_key_id: UUID,
        api_key_name: str,
        api_key_prefix: str,
        expires_at: datetime,
        created_by_user_id: Optional[UUID] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.created",
            entity_type="api_key",
            entity_id=str(api_key_id),
            description="API key created",
            new_value={
                "user_id": str(user_id),
                "username": username,
                "api_key_name": api_key_name,
                "api_key_prefix": api_key_prefix,
                "expires_at": expires_at,
                "created_by_user_id": (
                    str(created_by_user_id) if created_by_user_id else None
                ),
            },
            performed_by=username,
            context=context,
        )

    async def api_key_revoked(
        self,
        *,
        user_id: UUID,
        username: str,
        api_key_id: UUID,
        api_key_name: str,
        api_key_prefix: str,
        revoked_by_user_id: Optional[UUID] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.revoked",
            entity_type="api_key",
            entity_id=str(api_key_id),
            description="API key revoked",
            new_value={
                "user_id": str(user_id),
                "username": username,
                "api_key_name": api_key_name,
                "api_key_prefix": api_key_prefix,
                "revoked_by_user_id": (
                    str(revoked_by_user_id) if revoked_by_user_id else None
                ),
            },
            performed_by=username,
            context=context,
        )

    async def api_key_auth_success(
        self,
        *,
        user_id: UUID,
        username: str,
        api_key_id: UUID,
        api_key_prefix: str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.auth_success",
            entity_type="api_key",
            entity_id=str(api_key_id),
            description="API key authenticated successfully",
            new_value={
                "user_id": str(user_id),
                "username": username,
                "api_key_prefix": api_key_prefix,
            },
            performed_by=username,
            context=context,
        )

    async def api_key_auth_failure(
        self,
        *,
        reason: str,
        api_key_prefix: Optional[str] = None,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.api_key.auth_failure",
            entity_type="api_key",
            description="API key authentication failed",
            new_value={"reason": reason, "api_key_prefix": api_key_prefix},
            context=context,
        )

    async def nhi_account_created(
        self,
        *,
        admin_user_id: UUID,
        admin_username: str,
        nhi_user_id: UUID,
        nhi_username: str,
        role: UserRole | str,
        initial_api_key_id: UUID,
        initial_api_key_prefix: str,
        context: Optional[AuditContext] = None,
    ) -> AuditLog:
        return await self.log_event(
            event_type="auth.nhi.account_created",
            entity_type="user",
            entity_id=str(nhi_user_id),
            description="NHI account created",
            new_value={
                "admin_user_id": str(admin_user_id),
                "admin_username": admin_username,
                "nhi_username": nhi_username,
                "role": getattr(role, "value", role),
                "initial_api_key_id": str(initial_api_key_id),
                "initial_api_key_prefix": initial_api_key_prefix,
            },
            performed_by=admin_username,
            context=context,
        )


def get_audit_service(db: AsyncSession) -> AuditService:
    return AuditService(db)


async def persist_api_key_auth_failure(
    source_db: AsyncSession,
    *,
    reason: str,
    api_key_prefix: Optional[str],
    context: Optional[AuditContext],
    session_factory: Optional[AuditSessionFactory] = None,
) -> AuditLog:
    """Persist an authentication failure after ending the rejected request transaction.

    API-key validation performs a lookup before it can reject a credential, so the
    source session already owns a connection. Release that connection before opening
    the independent audit transaction; otherwise concurrent rejections can exhaust a
    bounded pool while every request waits for a second connection.
    """
    if session_factory is None:
        if source_db.bind is None:
            raise RuntimeError("Cannot persist API key audit without a database bind")
        session_factory = async_sessionmaker(
            bind=source_db.bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    await source_db.rollback()

    async with session_factory() as audit_db:
        audit_log = await get_audit_service(audit_db).api_key_auth_failure(
            reason=reason,
            api_key_prefix=api_key_prefix,
            context=context,
        )
        await audit_db.commit()
        return audit_log


__all__ = [
    "AuditContext",
    "AuditService",
    "AuditSessionFactory",
    "get_audit_service",
    "persist_api_key_auth_failure",
]
