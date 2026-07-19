"""Service for analyst-authored context entries."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContextCriterionType
from app.models.models import (
    Alert,
    ContextCriterion,
    ContextEntry,
    ContextEntryCreate,
    ContextEntryRead,
    ContextEntryUpdate,
)
from app.services.audit_service import AuditContext, get_audit_service


EXTRACTABLE_OBSERVABLE_KEYS = {
    "value",
    "observable",
    "observable_value",
    "ip",
    "ip_address",
    "domain",
    "url",
    "email",
    "hash",
    "filename",
    "file_name",
}
EXTRACTABLE_SYSTEM_KEYS = {
    "host",
    "hostname",
    "system",
    "system_name",
    "device",
    "asset",
    "fqdn",
    "ip",
    "ip_address",
    "private_ip",
    "public_ip",
}
ACTOR_ITEM_TYPES = {"internal_actor", "external_actor", "threat_actor"}
ACTOR_IDENTIFIER_KEYS = {
    "actor_id",
    "user_id",
    "username",
    "name",
    "tag_id",
    "org",
    "organization",
    "contact_email",
    "email",
    "upn",
}
SYSTEM_IDENTIFIER_KEYS = {
    "hostname",
    "name",
    "fqdn",
    "ip",
    "ip_address",
    "private_ip",
    "public_ip",
    "asset",
    "device",
    "system_name",
}
CandidateMap = dict[ContextCriterionType, set[str]]


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_body(value: str) -> str:
    body = value.strip()
    if not body:
        raise ValueError("Context body is required")
    return body


def _normalize_criteria(criteria: Iterable[ContextCriterion]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for criterion in criteria:
        value = criterion.value.strip()
        if not value:
            raise ValueError("Criterion value is required")
        normalized.append({"type": criterion.type.value, "value": value})
    return normalized


def _entry_criteria(entry: ContextEntry) -> list[ContextCriterion]:
    return [ContextCriterion.model_validate(item) for item in entry.criteria or []]


def _read_model(entry: ContextEntry) -> ContextEntryRead:
    if entry.id is None:
        raise ValueError("Cannot serialize unsaved context entry")
    return ContextEntryRead(
        id=entry.id,
        criteria=_entry_criteria(entry),
        body=entry.body,
        author=entry.author,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        expires_at=entry.expires_at,
        expired_at=entry.expired_at,
    )


def _audit_snapshot(entry: ContextEntry) -> dict[str, Any]:
    return _read_model(entry).model_dump(mode="json")


def _context_snapshot(entry: ContextEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "criteria": [criterion.model_dump(mode="json") for criterion in _entry_criteria(entry)],
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


def _iter_timeline_items(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("type"), str):
            yield value
        for child in value.values():
            yield from _iter_timeline_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_timeline_items(child)


def _add_candidate(candidates: CandidateMap, criterion_type: ContextCriterionType, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        candidates.setdefault(criterion_type, set()).add(text)


def _add_values_for_keys(candidates: CandidateMap, criterion_type: ContextCriterionType, item: dict[str, Any], keys: set[str]) -> None:
    for key in keys:
        _add_candidate(candidates, criterion_type, item.get(key))


def _alert_context_candidates(alert: Alert) -> CandidateMap:
    candidates: CandidateMap = {criterion_type: set() for criterion_type in ContextCriterionType}
    _add_candidate(candidates, ContextCriterionType.ALERT_SOURCE, alert.source)

    for tag in alert.tags or []:
        _add_candidate(candidates, ContextCriterionType.TAG, tag)

    for item in _iter_timeline_items(alert.timeline_items or {}):
        item_type = item.get("type")
        if item_type == "observable":
            _add_candidate(candidates, ContextCriterionType.OBSERVABLE, item.get("observable_value"))
            _add_candidate(candidates, ContextCriterionType.OBSERVABLE, item.get("value"))
        elif item_type == "system":
            _add_values_for_keys(candidates, ContextCriterionType.SYSTEM, item, SYSTEM_IDENTIFIER_KEYS)
        elif item_type in ACTOR_ITEM_TYPES:
            _add_values_for_keys(candidates, ContextCriterionType.ACTOR, item, ACTOR_IDENTIFIER_KEYS)

    for key, value in _walk_values(alert.timeline_items or {}):
        normalized_key = (key or "").casefold()
        if normalized_key in EXTRACTABLE_OBSERVABLE_KEYS:
            _add_candidate(candidates, ContextCriterionType.OBSERVABLE, value)
        if normalized_key in EXTRACTABLE_SYSTEM_KEYS:
            _add_candidate(candidates, ContextCriterionType.SYSTEM, value)

    return candidates


def _wildcard_matches(pattern: str, candidate: str) -> bool:
    parts: list[str] = []
    for char in pattern.strip():
        if char == "*":
            parts.append(".*")
        elif char == "?":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return re.fullmatch("".join(parts), candidate.strip(), flags=re.IGNORECASE) is not None


def _criterion_matches(criterion: ContextCriterion, candidates: CandidateMap) -> bool:
    return any(_wildcard_matches(criterion.value, candidate) for candidate in candidates.get(criterion.type, set()))


def _entry_matches(entry: ContextEntry, candidates: CandidateMap) -> bool:
    return all(_criterion_matches(criterion, candidates) for criterion in _entry_criteria(entry))


class ContextService:
    """Manage shared context and match it to alerts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_entries(self, *, include_expired: bool = False) -> list[ContextEntryRead]:
        now = datetime.now(timezone.utc)
        query = select(ContextEntry).order_by(ContextEntry.updated_at.desc())
        if not include_expired:
            query = query.where(
                ContextEntry.expired_at.is_(None),
                ContextEntry.expires_at > now,
            )
        result = await self.db.execute(query)
        return [_read_model(entry) for entry in result.scalars().all()]

    async def create_entry(
        self,
        payload: ContextEntryCreate,
        *,
        author: str,
        audit_context: AuditContext | None = None,
    ) -> ContextEntryRead:
        expires_at = _ensure_aware(payload.expires_at)
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("Expiry must be in the future")

        now = datetime.now(timezone.utc)
        entry = ContextEntry(
            criteria=_normalize_criteria(payload.criteria),
            body=_normalize_body(payload.body),
            author=author,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self.db.add(entry)
        await self.db.flush()
        await get_audit_service(self.db).log_event(
            event_type="context_entry.created",
            entity_type="context_entry",
            entity_id=str(entry.id),
            description="Context entry created",
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
        payload: ContextEntryUpdate,
        *,
        updated_by: str,
        audit_context: AuditContext | None = None,
    ) -> ContextEntryRead:
        entry = await self.db.get(ContextEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Context entry not found")

        before = _audit_snapshot(entry)
        if payload.criteria is not None:
            entry.criteria = _normalize_criteria(payload.criteria)
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
            event_type="context_entry.updated",
            entity_type="context_entry",
            entity_id=str(entry.id),
            description="Context entry updated",
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
    ) -> ContextEntryRead:
        entry = await self.db.get(ContextEntry, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Context entry not found")

        before = _audit_snapshot(entry)
        now = datetime.now(timezone.utc)
        entry.expired_at = now
        entry.expires_at = min(_ensure_aware(entry.expires_at), now)
        entry.updated_at = now

        await self.db.flush()
        await get_audit_service(self.db).log_event(
            event_type="context_entry.expired",
            entity_type="context_entry",
            entity_id=str(entry.id),
            description="Context entry expired",
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
            select(ContextEntry).where(
                ContextEntry.expired_at.is_(None),
                ContextEntry.expires_at > now,
            )
        )

        candidates = _alert_context_candidates(alert)
        matches = [entry for entry in result.scalars().all() if _entry_matches(entry, candidates)]
        matches.sort(key=lambda item: (len(item.criteria or []), item.id or 0))
        return [_context_snapshot(entry) for entry in matches]
