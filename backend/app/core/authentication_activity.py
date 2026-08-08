"""Best-effort activity touches performed after protected auth transactions."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ApiKey, AuthSession


_SESSION_TOUCHES = "deferred_auth_session_touches"
_API_KEY_TOUCHES = "deferred_api_key_touches"


def _defer_touch(
    db: Any,
    *,
    info_key: str,
    credential_id: UUID,
    observed_at: datetime,
) -> None:
    if not issubclass(type(db), AsyncSession):
        return
    touches: dict[UUID, datetime] = db.info.setdefault(info_key, {})
    previous = touches.get(credential_id)
    if previous is None or observed_at > previous:
        touches[credential_id] = observed_at


def defer_session_activity(
    db: Any,
    *,
    session_id: UUID,
    observed_at: datetime,
) -> None:
    """Queue an idle-window touch until shared authorization locks are released."""
    _defer_touch(
        db,
        info_key=_SESSION_TOUCHES,
        credential_id=session_id,
        observed_at=observed_at,
    )


def defer_api_key_activity(
    db: Any,
    *,
    api_key_id: UUID,
    observed_at: datetime,
) -> None:
    """Queue API-key usage telemetry until shared locks are released."""
    _defer_touch(
        db,
        info_key=_API_KEY_TOUCHES,
        credential_id=api_key_id,
        observed_at=observed_at,
    )


async def flush_deferred_authentication_activity(db: AsyncSession) -> bool:
    """Apply queued touches without waiting behind credential writers.

    The caller must first commit or roll back the protected authorization
    transaction. Locked credentials are skipped because activity timestamps are
    telemetry, while disable/revocation is security-critical.
    """
    session_touches: dict[UUID, datetime] = db.info.pop(_SESSION_TOUCHES, {})
    api_key_touches: dict[UUID, datetime] = db.info.pop(_API_KEY_TOUCHES, {})
    changed = False

    for session_id, observed_at in session_touches.items():
        result = await db.execute(
            select(AuthSession)
            .where(AuthSession.id == session_id)
            .with_for_update(skip_locked=True)
        )
        session = result.scalar_one_or_none()
        if (
            session is not None
            and session.revoked_at is None
            and session.expires_at > observed_at
            and session.last_seen_at < observed_at
        ):
            session.last_seen_at = observed_at
            changed = True

    for api_key_id, observed_at in api_key_touches.items():
        result = await db.execute(
            select(ApiKey)
            .where(ApiKey.id == api_key_id)
            .with_for_update(skip_locked=True)
        )
        api_key = result.scalar_one_or_none()
        if (
            api_key is not None
            and api_key.revoked_at is None
            and api_key.expires_at > observed_at
            and (api_key.last_used_at is None or api_key.last_used_at < observed_at)
        ):
            api_key.last_used_at = observed_at
            changed = True

    return changed


__all__ = [
    "defer_api_key_activity",
    "defer_session_activity",
    "flush_deferred_authentication_activity",
]
