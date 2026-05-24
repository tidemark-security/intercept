"""Service for analyst-authored context supplied to AI triage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AITriageContextScopeType
from app.models.models import (
    AITriageContextEntry,
    AITriageContextEntryCreate,
    AITriageContextEntryRead,
    AITriageContextEntryUpdate,
    AITriageContextScope,
    Alert,
)
from app.services.audit_service import AuditContext, get_audit_service


EXTRACTABLE_OBSERVABLE_KEYS = {
    "value",
    "observable",
    "ip",
    "ip_address",
    "domain",
    "url",
    "email",
    "hash",
    "filename",
    "file_name",
}
EXTRACTABLE_HOST_KEYS = {"host", "hostname", "system", "system_name", "device", "asset"}


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_scope_value(scope_type: AITriageContextScopeType, value: str | None) -> str | None:
    if scope_type == AITriageContextScopeType.GLOBAL:
        return None
    if value is None or not value.strip():
        raise ValueError("Scope value is required unless scope type is GLOBAL")
    return value.strip()


def _normalize_body(value: str) -> str:
    body = value.strip()
    if not body:
        raise ValueError("Context body is required")
    return body


def _read_model(entry: AITriageContextEntry) -> AITriageContextEntryRead:
    if entry.id is None:
        raise ValueError("Cannot serialize unsaved AI triage context entry")
    return AITriageContextEntryRead(
        id=entry.id,
        scope=AITriageContextScope(type=entry.scope_type, value=entry.scope_value),
        body=entry.body,
        author=entry.author,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        expires_at=entry.expires_at,
        expired_at=entry.expired_at,
    )


def _audit_snapshot(entry: AITriageContextEntry) -> dict[str, Any]:
    return _read_model(entry).model_dump(mode="json")


def _context_snapshot(entry: AITriageContextEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "scope": {
            "type": entry.scope_type.value,
            "value": entry.scope_value,
        },
        "body": entry.body,
        "author": entry.author,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "expires_at": entry.expires_at.isoformat(),
    }


def _walk_values(value: Any) -> Iterable[tuple[str | None, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str):
                yield str(key), child
            else:
                yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _add_candidate(candidates: set[tuple[AITriageContextScopeType, str | None]], scope_type: AITriageContextScopeType, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        candidates.add((scope_type, text.casefold()))


def _alert_context_candidates(alert: Alert) -> set[tuple[AITriageContextScopeType, str | None]]:
    candidates: set[tuple[AITriageContextScopeType, str | None]] = {
        (AITriageContextScopeType.GLOBAL, None)
    }
    _add_candidate(candidates, AITriageContextScopeType.ALERT_SOURCE, alert.source)
    _add_candidate(candidates, AITriageContextScopeType.CASE, alert.case_id)
    _add_candidate(candidates, AITriageContextScopeType.USER_ACCOUNT, alert.assignee)

    for tag in alert.tags or []:
        _add_candidate(candidates, AITriageContextScopeType.TAG, tag)

    for key, value in _walk_values(alert.timeline_items or {}):
        normalized_key = (key or "").casefold()
        if normalized_key in EXTRACTABLE_OBSERVABLE_KEYS:
            _add_candidate(candidates, AITriageContextScopeType.OBSERVABLE, value)
        if normalized_key in EXTRACTABLE_HOST_KEYS:
            _add_candidate(candidates, AITriageContextScopeType.HOST_SYSTEM, value)

    return candidates


class AITriageContextService:
    """Manage shared AI triage context and match it to alerts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_entries(self, *, include_expired: bool = False) -> list[AITriageContextEntryRead]:
        now = datetime.now(timezone.utc)
        query = select(AITriageContextEntry).order_by(AITriageContextEntry.updated_at.desc())
        if not include_expired:
            query = query.where(
                AITriageContextEntry.expired_at.is_(None),
                AITriageContextEntry.expires_at > now,
            )
        result = await self.db.execute(query)
        return [_read_model(entry) for entry in result.scalars().all()]

    async def create_entry(
        self,
        payload: AITriageContextEntryCreate,
        *,
        author: str,
        audit_context: AuditContext | None = None,
    ) -> AITriageContextEntryRead:
        expires_at = _ensure_aware(payload.expires_at)
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("Expiry must be in the future")

        now = datetime.now(timezone.utc)
        entry = AITriageContextEntry(
            scope_type=payload.scope.type,
            scope_value=_normalize_scope_value(payload.scope.type, payload.scope.value),
            body=_normalize_body(payload.body),
            author=author,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self.db.add(entry)
        await self.db.flush()
        await get_audit_service(self.db).log_event(
            event_type="ai_triage_context.created",
            entity_type="ai_triage_context",
            entity_id=str(entry.id),
            description="AI triage context created",
            new_value=_audit_snapshot(entry),
            performed_by=author,
            context=audit_context,
        )
        await self.db.commit()
        await self.db.refresh(entry)
        return _read_model(entry)

    async def update_entry(
        self,
        entry_id: int,
        payload: AITriageContextEntryUpdate,
        *,
        updated_by: str,
        audit_context: AuditContext | None = None,
    ) -> AITriageContextEntryRead:
        entry = await self.db.get(AITriageContextEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="AI triage context entry not found")

        before = _audit_snapshot(entry)
        if payload.scope is not None:
            entry.scope_type = payload.scope.type
            entry.scope_value = _normalize_scope_value(payload.scope.type, payload.scope.value)
        if payload.body is not None:
            entry.body = _normalize_body(payload.body)
        if payload.expires_at is not None:
            expires_at = _ensure_aware(payload.expires_at)
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("Expiry must be in the future")
            entry.expires_at = expires_at
            entry.expired_at = None
        entry.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await get_audit_service(self.db).log_event(
            event_type="ai_triage_context.updated",
            entity_type="ai_triage_context",
            entity_id=str(entry.id),
            description="AI triage context updated",
            old_value=before,
            new_value=_audit_snapshot(entry),
            performed_by=updated_by,
            context=audit_context,
        )
        await self.db.commit()
        await self.db.refresh(entry)
        return _read_model(entry)

    async def expire_entry(
        self,
        entry_id: int,
        *,
        expired_by: str,
        audit_context: AuditContext | None = None,
    ) -> AITriageContextEntryRead:
        entry = await self.db.get(AITriageContextEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="AI triage context entry not found")

        before = _audit_snapshot(entry)
        now = datetime.now(timezone.utc)
        entry.expired_at = now
        entry.expires_at = min(_ensure_aware(entry.expires_at), now)
        entry.updated_at = now

        await self.db.flush()
        await get_audit_service(self.db).log_event(
            event_type="ai_triage_context.expired",
            entity_type="ai_triage_context",
            entity_id=str(entry.id),
            description="AI triage context expired",
            old_value=before,
            new_value=_audit_snapshot(entry),
            performed_by=expired_by,
            context=audit_context,
        )
        await self.db.commit()
        await self.db.refresh(entry)
        return _read_model(entry)

    async def get_matching_context_for_alert(self, alert_id: int) -> list[dict[str, Any]]:
        alert = await self.db.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(AITriageContextEntry).where(
                AITriageContextEntry.expired_at.is_(None),
                AITriageContextEntry.expires_at > now,
                or_(
                    AITriageContextEntry.scope_type == AITriageContextScopeType.GLOBAL,
                    AITriageContextEntry.scope_value.is_not(None),
                ),
            )
        )

        candidates = _alert_context_candidates(alert)
        matches: list[AITriageContextEntry] = []
        for entry in result.scalars().all():
            key = (
                entry.scope_type,
                entry.scope_value.casefold() if entry.scope_value is not None else None,
            )
            if key in candidates:
                matches.append(entry)

        matches.sort(key=lambda item: (item.scope_type.value, item.scope_value or "", item.id or 0))
        return [_context_snapshot(entry) for entry in matches]
