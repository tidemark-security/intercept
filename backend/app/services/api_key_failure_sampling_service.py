"""Durable sampling for rejected API-key authentication attempts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_registry import get_local
from app.models.models import ApiKeyFailureSample, AuditLog
from app.services.audit_service import (
    AuditContext,
    AuditSessionFactory,
    get_audit_service,
)


# Serialize admitted samples across backend workers so concurrent hostile
# requests cannot each observe spare source/global capacity and overfill the
# ledger. Sampling is optional telemetry: callers must never wait for this lock.
_API_KEY_FAILURE_ADVISORY_LOCK_ID = 0x544D_4150_494B


@dataclass(frozen=True, slots=True)
class ApiKeyFailureAuditPolicy:
    """Bounds for durable samples of rejected API-key authentication."""

    per_failure_quota: int = 3
    per_failure_window_seconds: int = 5 * 60
    per_source_quota: int = 30
    per_source_window_seconds: int = 5 * 60
    global_quota: int = 10_000
    global_window_seconds: int = 60 * 60


def _normalize_source(source_address: str | None) -> str:
    return str(source_address or "unknown").strip() or "unknown"


def _fingerprint(message: bytes) -> str:
    key = str(get_local("secret_key")).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def api_key_failure_source_fingerprint(source_address: str | None) -> str:
    """Return a fixed-size HMAC without retaining the source address in the ledger."""

    normalized_source = _normalize_source(source_address)
    return _fingerprint(
        b"intercept-api-key-failure-source-v1\x00"
        + normalized_source.encode("utf-8")
    )


def api_key_failure_fingerprint(
    *,
    source_address: str | None,
    api_key_id: UUID | None,
    reason: str,
) -> str:
    """Group one source, stable credential, and failure reason without raw keys."""

    normalized_source = _normalize_source(source_address)
    credential_identity = str(api_key_id) if api_key_id is not None else "unresolved"
    return _fingerprint(
        b"intercept-api-key-failure-bucket-v1\x00"
        + normalized_source.encode("utf-8")
        + b"\x00"
        + credential_identity.encode("ascii")
        + b"\x00"
        + reason.encode("utf-8")
    )


class ApiKeyFailureAuditService:
    """Persist only admitted API-key failure samples in bounded durable windows."""

    async def persist_if_admitted(
        self,
        source_db: AsyncSession,
        *,
        reason: str,
        api_key_id: UUID | None,
        api_key_prefix: str | None,
        context: Optional[AuditContext],
        session_factory: Optional[AuditSessionFactory] = None,
        policy: ApiKeyFailureAuditPolicy = ApiKeyFailureAuditPolicy(),
    ) -> Optional[AuditLog]:
        if session_factory is None:
            if source_db.bind is None:
                raise RuntimeError(
                    "Cannot sample API key audit without a database bind"
                )
            session_factory = async_sessionmaker(
                bind=source_db.bind,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        # The rejected request may already own the only connection in a
        # bounded pool. Release it before reserving a sample independently.
        await source_db.rollback()

        source_address = context.ip_address if context is not None else None
        source_fingerprint = api_key_failure_source_fingerprint(source_address)
        failure_fingerprint = api_key_failure_fingerprint(
            source_address=source_address,
            api_key_id=api_key_id,
            reason=reason,
        )
        failure_quota = max(1, int(policy.per_failure_quota))
        failure_window = max(1, int(policy.per_failure_window_seconds))
        source_quota = max(1, int(policy.per_source_quota))
        source_window = max(1, int(policy.per_source_window_seconds))
        global_quota = max(1, int(policy.global_quota))
        global_window = max(1, int(policy.global_window_seconds))
        now = datetime.now(timezone.utc)

        async with session_factory() as audit_db:
            lock_result = await audit_db.execute(
                select(
                    func.pg_try_advisory_xact_lock(
                        _API_KEY_FAILURE_ADVISORY_LOCK_ID
                    )
                )
            )
            # Small unit-test session doubles return None from execute; real
            # AsyncSession results always expose scalar_one().
            lock_acquired = (
                True if lock_result is None else bool(lock_result.scalar_one())
            )
            if not lock_acquired:
                await audit_db.rollback()
                return None

            retention_cutoff = now - timedelta(
                seconds=max(failure_window, source_window, global_window)
            )
            await audit_db.execute(
                delete(ApiKeyFailureSample).where(
                    ApiKeyFailureSample.created_at <= retention_cutoff
                )
            )

            global_recent = await audit_db.scalar(
                select(func.count())
                .select_from(ApiKeyFailureSample)
                .where(
                    ApiKeyFailureSample.created_at
                    > now - timedelta(seconds=global_window)
                )
            )
            if int(global_recent or 0) >= global_quota:
                await audit_db.rollback()
                return None

            source_recent = await audit_db.scalar(
                select(func.count())
                .select_from(ApiKeyFailureSample)
                .where(
                    ApiKeyFailureSample.source_fingerprint == source_fingerprint,
                    ApiKeyFailureSample.created_at
                    > now - timedelta(seconds=source_window),
                )
            )
            if int(source_recent or 0) >= source_quota:
                await audit_db.rollback()
                return None

            failure_recent = await audit_db.scalar(
                select(func.count())
                .select_from(ApiKeyFailureSample)
                .where(
                    ApiKeyFailureSample.failure_fingerprint
                    == failure_fingerprint,
                    ApiKeyFailureSample.created_at
                    > now - timedelta(seconds=failure_window),
                )
            )
            if int(failure_recent or 0) >= failure_quota:
                await audit_db.rollback()
                return None

            audit_db.add(
                ApiKeyFailureSample(
                    source_fingerprint=source_fingerprint,
                    failure_fingerprint=failure_fingerprint,
                    created_at=now,
                )
            )
            audit_log = await get_audit_service(audit_db).api_key_auth_failure(
                reason=reason,
                api_key_id=api_key_id,
                api_key_prefix=api_key_prefix if api_key_id is not None else None,
                source_fingerprint=source_fingerprint,
                failure_fingerprint=failure_fingerprint,
                sampled=True,
                context=context,
            )
            await audit_db.commit()
            return audit_log


api_key_failure_audit_service = ApiKeyFailureAuditService()


async def persist_sampled_api_key_auth_failure(
    source_db: AsyncSession,
    *,
    reason: str,
    api_key_id: UUID | None,
    api_key_prefix: str | None,
    context: Optional[AuditContext],
    session_factory: Optional[AuditSessionFactory] = None,
) -> Optional[AuditLog]:
    """Persist an API-key failure only while durable capacity is available."""

    return await api_key_failure_audit_service.persist_if_admitted(
        source_db,
        reason=reason,
        api_key_id=api_key_id,
        api_key_prefix=api_key_prefix,
        context=context,
        session_factory=session_factory,
    )


__all__ = [
    "ApiKeyFailureAuditPolicy",
    "ApiKeyFailureAuditService",
    "api_key_failure_audit_service",
    "api_key_failure_fingerprint",
    "api_key_failure_source_fingerprint",
    "persist_sampled_api_key_auth_failure",
]
