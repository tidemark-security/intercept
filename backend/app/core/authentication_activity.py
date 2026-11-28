"""Best-effort activity touches performed after protected auth transactions."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.models.models import (
    ApiKey,
    AuthSession,
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthProviderGrantReference,
    MCPOAuthToken,
)


_DEFERRED_ACTIVITY = "deferred_authentication_activity"

logger = logging.getLogger(__name__)


def _defer_touch(
    db: Any, model: type[SQLModel], row_id: UUID, observed_at: datetime
) -> None:
    if not issubclass(type(db), AsyncSession):
        return
    pending = db.info.setdefault(_DEFERRED_ACTIVITY, {})
    touches: dict[UUID, datetime] = pending.setdefault(model, {})
    previous = touches.get(row_id)
    if previous is None or observed_at > previous:
        touches[row_id] = observed_at


def defer_session_activity(
    db: Any,
    *,
    session_id: UUID,
    observed_at: datetime,
) -> None:
    """Queue an idle-window touch until shared authorization locks are released."""
    _defer_touch(db, AuthSession, session_id, observed_at)


def defer_api_key_activity(
    db: Any,
    *,
    api_key_id: UUID,
    observed_at: datetime,
) -> None:
    """Queue API-key usage telemetry until shared locks are released."""
    _defer_touch(db, ApiKey, api_key_id, observed_at)


def defer_mcp_oauth_activity(
    db: AsyncSession, *, client_id: UUID, token_id: UUID, observed_at: datetime
) -> None:
    """Remember local OAuth usage without dirtying the validated credential."""
    _defer_touch(db, MCPOAuthClient, client_id, observed_at)
    _defer_touch(db, MCPOAuthToken, token_id, observed_at)


def defer_mcp_oidc_activity(
    db: AsyncSession,
    *,
    client_id: UUID,
    consent_id: UUID,
    reference_id: UUID,
    observed_at: datetime,
) -> None:
    """Remember use of the exact OIDC grant that was authorized."""
    _defer_touch(db, MCPOAuthClient, client_id, observed_at)
    _defer_touch(db, MCPOAuthConsent, consent_id, observed_at)
    _defer_touch(db, MCPOAuthProviderGrantReference, reference_id, observed_at)


async def flush_deferred_authentication_activity(db: AsyncSession) -> bool:
    """Apply queued touches without waiting behind credential writers.

    The caller must first commit or roll back the protected authorization
    transaction. Locked credentials are skipped because activity timestamps are
    telemetry, while disable/revocation is security-critical.
    """
    pending: dict[type[SQLModel], dict[UUID, datetime]] = db.info.pop(_DEFERRED_ACTIVITY, {})
    changed = False

    for session_id, observed_at in pending.pop(AuthSession, {}).items():
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

    # A single conditional UPDATE uses the current database value even when
    # an older observation finishes last or the session cached an older row.
    for model, touches in pending.items():
        table = model.__table__
        timestamp = table.c.last_seen_at if model is MCPOAuthClient else table.c.last_used_at
        for row_id, observed_at in touches.items():
            available = select(table.c.id).where(
                table.c.id == row_id,
                table.c.revoked_at.is_(None),
                or_(timestamp.is_(None), timestamp < observed_at),
            )
            if "expires_at" in table.c:
                available = available.where(table.c.expires_at > observed_at)
            # FOR NO KEY UPDATE is compatible with a tool's FOR KEY SHARE.
            available = available.with_for_update(key_share=True, skip_locked=True)
            result = await db.execute(
                update(table).where(table.c.id.in_(available)).values({timestamp: observed_at})
            )
            if result.rowcount > 0:
                changed = True

    return changed


async def persist_deferred_authentication_activity(db: AsyncSession) -> None:
    """Flush usage in its own transaction after the caller releases auth locks."""
    if not isinstance(db, AsyncSession):
        return
    pending = db.info.pop(_DEFERRED_ACTIVITY, None)
    if not pending:
        return
    # A telemetry rollback must not expire the principal that the successful
    # authorization transaction returns to the caller.
    try:
        async with AsyncSession(bind=db.bind, info={_DEFERRED_ACTIVITY: pending}) as activity_db:
            if await flush_deferred_authentication_activity(activity_db):
                await activity_db.commit()
    except Exception:
        logger.warning("Unable to persist deferred authentication activity", exc_info=True)


__all__ = [
    "defer_api_key_activity",
    "defer_mcp_oauth_activity",
    "defer_mcp_oidc_activity",
    "defer_session_activity",
    "flush_deferred_authentication_activity",
    "persist_deferred_authentication_activity",
]
