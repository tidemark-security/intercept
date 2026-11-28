"""Durable controls for unauthenticated main-application OIDC initiation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local
from app.models.models import OIDCAuthRequest


# Serialize the small global OIDC state ledger across backend workers. The lock
# is transaction-scoped, so the route commit makes the reservation visible
# before the next worker evaluates capacity.
_OIDC_AUTH_REQUEST_ADVISORY_LOCK_ID = 0x544D_4F49_4443


@dataclass(frozen=True, slots=True)
class OIDCAuthRequestPolicy:
    global_outstanding_quota: int = 1_000
    per_source_outstanding_quota: int = 20
    global_rate_quota: int = 10_000
    per_source_rate_quota: int = 120
    rate_window_seconds: int = 60 * 60
    retry_after_seconds: int = 60


class OIDCAuthRequestLimitError(RuntimeError):
    """Raised when the durable OIDC initiation ledger is at capacity."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, int(retry_after_seconds))


def oidc_source_fingerprint(source_address: str | None) -> str:
    """Return a stable cross-worker HMAC without retaining the raw peer IP."""

    normalized = str(source_address or "unknown").strip() or "unknown"
    key = str(get_local("secret_key")).encode("utf-8")
    message = b"intercept-oidc-login-source-v1\x00" + normalized.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


class OIDCAuthRequestService:
    """Reserve OIDC state rows under a PostgreSQL transaction lock."""

    async def reserve(
        self,
        db: AsyncSession,
        *,
        auth_request: OIDCAuthRequest,
        policy: OIDCAuthRequestPolicy,
    ) -> None:
        now = datetime.now(timezone.utc)
        await db.execute(
            select(
                func.pg_advisory_xact_lock(
                    _OIDC_AUTH_REQUEST_ADVISORY_LOCK_ID
                )
            )
        )
        history_cutoff = now - timedelta(seconds=policy.rate_window_seconds)
        await db.execute(
            delete(OIDCAuthRequest).where(
                OIDCAuthRequest.created_at <= history_cutoff,
                or_(
                    OIDCAuthRequest.consumed_at.is_not(None),
                    OIDCAuthRequest.expires_at <= now,
                ),
            )
        )
        outstanding = await db.scalar(
            select(func.count())
            .select_from(OIDCAuthRequest)
            .where(
                OIDCAuthRequest.consumed_at.is_(None),
                OIDCAuthRequest.expires_at > now,
            )
        )
        if int(outstanding or 0) >= policy.global_outstanding_quota:
            raise OIDCAuthRequestLimitError(
                "The OIDC sign-in queue is full; retry later",
                retry_after_seconds=policy.retry_after_seconds,
            )

        global_recent = await db.scalar(
            select(func.count())
            .select_from(OIDCAuthRequest)
            .where(
                OIDCAuthRequest.created_at
                > history_cutoff,
            )
        )
        if int(global_recent or 0) >= policy.global_rate_quota:
            raise OIDCAuthRequestLimitError(
                "The OIDC sign-in rate capacity is full; retry later",
                retry_after_seconds=policy.retry_after_seconds,
            )

        source_outstanding = await db.scalar(
            select(func.count())
            .select_from(OIDCAuthRequest)
            .where(
                OIDCAuthRequest.source_fingerprint
                == auth_request.source_fingerprint,
                OIDCAuthRequest.consumed_at.is_(None),
                OIDCAuthRequest.expires_at > now,
            )
        )
        if int(source_outstanding or 0) >= policy.per_source_outstanding_quota:
            raise OIDCAuthRequestLimitError(
                "This client has too many pending OIDC sign-ins; retry later",
                retry_after_seconds=policy.retry_after_seconds,
            )

        source_recent = await db.scalar(
            select(func.count())
            .select_from(OIDCAuthRequest)
            .where(
                OIDCAuthRequest.source_fingerprint
                == auth_request.source_fingerprint,
                OIDCAuthRequest.created_at
                > history_cutoff,
            )
        )
        if int(source_recent or 0) >= policy.per_source_rate_quota:
            raise OIDCAuthRequestLimitError(
                "Too many OIDC sign-ins from this client; retry later",
                retry_after_seconds=policy.retry_after_seconds,
            )

        db.add(auth_request)
        await db.flush()


oidc_auth_request_service = OIDCAuthRequestService()


__all__ = [
    "OIDCAuthRequestLimitError",
    "OIDCAuthRequestPolicy",
    "OIDCAuthRequestService",
    "oidc_auth_request_service",
    "oidc_source_fingerprint",
]
