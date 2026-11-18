"""Durable admission controls for unauthenticated password login."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local
from app.models.models import PasswordLoginAttempt, PasswordLoginFailureCounter


# Serialize the bounded password-login ledger across backend workers. The
# caller commits immediately after reservation, before performing Argon2 work.
_PASSWORD_LOGIN_ADVISORY_LOCK_ID = 0x544D_5057_4C47


@dataclass(frozen=True, slots=True)
class PasswordLoginRequestPolicy:
    global_rate_quota: int = 10_000
    global_rate_window_seconds: int = 60 * 60
    retry_after_seconds: int = 60


class PasswordLoginRequestLimitError(RuntimeError):
    """Raised when the durable password-login ledger is at capacity."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, int(retry_after_seconds))


def password_login_source_fingerprint(source_address: str | None) -> str:
    """Return a fixed-length HMAC without retaining the raw client address."""

    normalized = str(source_address or "unknown").strip() or "unknown"
    key = str(get_local("secret_key")).encode("utf-8")
    message = b"intercept-password-login-source-v1\x00" + normalized.encode(
        "utf-8"
    )
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def password_version_fingerprint(password_hash: str) -> str:
    """Return a stable, non-reversible key for one password version."""

    return hashlib.sha256(
        b"intercept-password-version-v1\x00" + password_hash.encode("utf-8")
    ).hexdigest()


def _password_failure_lock_key(user_id: UUID) -> int:
    """Return a separate per-account lock key for failure-counter updates."""

    digest = hashlib.blake2b(
        user_id.bytes,
        digest_size=8,
        person=b"tmi-pwd-fail",
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


class PasswordLoginRequestService:
    """Reserve password-login work under a PostgreSQL transaction lock."""

    async def reserve(
        self,
        db: AsyncSession,
        *,
        attempt: PasswordLoginAttempt,
        policy: PasswordLoginRequestPolicy,
        per_source_rate_quota: int,
        per_source_rate_window_seconds: int,
    ) -> None:
        if not attempt.source_fingerprint:
            raise ValueError("Password-login reservations require a source fingerprint")

        global_quota = max(1, int(policy.global_rate_quota))
        global_window = max(1, int(policy.global_rate_window_seconds))
        source_quota = max(1, int(per_source_rate_quota))
        source_window = max(1, int(per_source_rate_window_seconds))
        now = datetime.now(timezone.utc)

        await db.execute(
            select(func.pg_advisory_xact_lock(_PASSWORD_LOGIN_ADVISORY_LOCK_ID))
        )
        history_cutoff = now - timedelta(seconds=max(global_window, source_window))
        await db.execute(
            delete(PasswordLoginAttempt).where(
                PasswordLoginAttempt.created_at <= history_cutoff
            )
        )

        global_recent = await db.scalar(
            select(func.count())
            .select_from(PasswordLoginAttempt)
            .where(
                PasswordLoginAttempt.created_at
                > now - timedelta(seconds=global_window)
            )
        )
        if int(global_recent or 0) >= global_quota:
            raise PasswordLoginRequestLimitError(
                "The password sign-in rate capacity is full; retry later",
                retry_after_seconds=policy.retry_after_seconds,
            )

        source_recent = await db.scalar(
            select(func.count())
            .select_from(PasswordLoginAttempt)
            .where(
                PasswordLoginAttempt.source_fingerprint
                == attempt.source_fingerprint,
                PasswordLoginAttempt.created_at
                > now - timedelta(seconds=source_window),
            )
        )
        if int(source_recent or 0) >= source_quota:
            raise PasswordLoginRequestLimitError(
                "Too many password sign-ins from this client; retry later",
                retry_after_seconds=min(
                    max(1, source_window),
                    max(1, int(policy.retry_after_seconds)),
                ),
            )

        db.add(attempt)
        await db.flush()

    async def record_failure(
        self,
        db: AsyncSession,
        *,
        failed_user_id: UUID | None = None,
        password_fingerprint: str | None = None,
    ) -> int:
        """Durably enqueue one password failure for later account materialization.

        Failure accounting uses a lock namespace separate from the account
        authorization gate. Invalid guesses therefore serialize with each
        other without waiting behind an administrator or a valid login.
        """

        if (failed_user_id is None) != (password_fingerprint is None):
            raise ValueError(
                "Failure accounting requires both user and password fingerprint"
            )

        pending_failures = 0
        if failed_user_id is not None and password_fingerprint is not None:
            await db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        _password_failure_lock_key(failed_user_id)
                    )
                )
            )
            now = datetime.now(timezone.utc)
            statement = (
                pg_insert(PasswordLoginFailureCounter)
                .values(
                    user_id=failed_user_id,
                    password_fingerprint=password_fingerprint,
                    failed_attempts=1,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[
                        PasswordLoginFailureCounter.user_id,
                        PasswordLoginFailureCounter.password_fingerprint,
                    ],
                    set_={
                        "failed_attempts": (
                            PasswordLoginFailureCounter.failed_attempts + 1
                        ),
                        "updated_at": now,
                    },
                )
                .returning(PasswordLoginFailureCounter.failed_attempts)
            )
            pending_failures = int((await db.execute(statement)).scalar_one())

        if failed_user_id is not None:
            await db.commit()
        return pending_failures

    async def consume_pending_failures(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        password_fingerprint: str,
    ) -> int:
        """Consume the pending delta while the caller owns the account gate."""

        await db.execute(
            select(
                func.pg_advisory_xact_lock(_password_failure_lock_key(user_id))
            )
        )
        pending = await db.scalar(
            select(PasswordLoginFailureCounter.failed_attempts).where(
                PasswordLoginFailureCounter.user_id == user_id,
                PasswordLoginFailureCounter.password_fingerprint
                == password_fingerprint,
            )
        )
        await db.execute(
            delete(PasswordLoginFailureCounter).where(
                PasswordLoginFailureCounter.user_id == user_id,
                PasswordLoginFailureCounter.password_fingerprint
                == password_fingerprint,
            )
        )
        return int(pending or 0)

    async def clear_pending_failures(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
    ) -> None:
        """Discard every pending password-version delta for an account.

        Account recovery and credential/posture transitions call this while
        holding the exclusive account authorization gate. The separate failure
        lock makes the clear linearizable with invalid guesses that have already
        completed Argon2 work but have not yet reached the account gate.
        """

        await db.execute(
            select(func.pg_advisory_xact_lock(_password_failure_lock_key(user_id)))
        )
        await db.execute(
            delete(PasswordLoginFailureCounter).where(
                PasswordLoginFailureCounter.user_id == user_id
            )
        )


password_login_request_service = PasswordLoginRequestService()


__all__ = [
    "PasswordLoginRequestLimitError",
    "PasswordLoginRequestPolicy",
    "PasswordLoginRequestService",
    "password_login_request_service",
    "password_login_source_fingerprint",
    "password_version_fingerprint",
]
