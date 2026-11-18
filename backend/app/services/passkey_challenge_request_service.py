"""Durable controls for unauthenticated passkey authentication initiation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_registry import get_local
from app.models.models import WebAuthnChallenge


# Serialize the small passkey challenge ledger across backend workers. The
# transaction-scoped lock makes each committed reservation visible before the
# next worker evaluates capacity.
_PASSKEY_CHALLENGE_ADVISORY_LOCK_ID = 0x544D_504B_4348


@dataclass(frozen=True, slots=True)
class PasskeyChallengeRequestPolicy:
    global_outstanding_quota: int = 1_000
    per_source_outstanding_quota: int = 20
    global_rate_quota: int = 10_000
    per_source_rate_quota: int = 120
    registration_global_outstanding_quota: int = 1_000
    registration_global_rate_quota: int = 10_000
    registration_per_user_rate_quota: int = 30
    rate_window_seconds: int = 60 * 60
    retry_after_seconds: int = 60


class PasskeyChallengeRequestLimitError(RuntimeError):
    """Raised when the durable passkey initiation ledger is at capacity."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = max(1, int(retry_after_seconds))


def _fingerprint(*, namespace: bytes, value: str | None) -> str:
    normalized = str(value or "unknown").strip().lower() or "unknown"
    key = str(get_local("secret_key")).encode("utf-8")
    return hmac.new(
        key,
        namespace + b"\x00" + normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def passkey_source_fingerprint(source_address: str | None) -> str:
    """Return a stable cross-worker HMAC without retaining the raw peer IP."""

    return _fingerprint(
        namespace=b"intercept-passkey-login-source-v1",
        value=source_address,
    )


def passkey_user_fingerprint(username: str) -> str:
    """Return a stable HMAC for a canonical username, including unknown users."""

    return _fingerprint(
        namespace=b"intercept-passkey-login-user-v1",
        value=username,
    )


class PasskeyChallengeRequestService:
    """Reserve passkey authentication challenges under a PostgreSQL lock."""

    async def reserve(
        self,
        db: AsyncSession,
        *,
        challenge: WebAuthnChallenge,
        policy: PasskeyChallengeRequestPolicy,
    ) -> None:
        if not challenge.source_fingerprint or not challenge.user_fingerprint:
            raise ValueError(
                "Passkey authentication reservations require source and user fingerprints"
            )

        now = datetime.now(timezone.utc)
        await db.execute(
            select(func.pg_advisory_xact_lock(_PASSKEY_CHALLENGE_ADVISORY_LOCK_ID))
        )
        history_cutoff = now - timedelta(seconds=policy.rate_window_seconds)
        ledger_filter = (
            WebAuthnChallenge.flow_type == "authentication",
            WebAuthnChallenge.source_fingerprint.is_not(None),
            WebAuthnChallenge.user_fingerprint.is_not(None),
        )
        await db.execute(
            delete(WebAuthnChallenge).where(
                *ledger_filter,
                WebAuthnChallenge.created_at <= history_cutoff,
                or_(
                    WebAuthnChallenge.consumed_at.is_not(None),
                    WebAuthnChallenge.expires_at <= now,
                ),
            )
        )

        await self._enforce_count(
            db,
            conditions=(
                *ledger_filter,
                WebAuthnChallenge.consumed_at.is_(None),
                WebAuthnChallenge.expires_at > now,
            ),
            quota=policy.global_outstanding_quota,
            message="The passkey sign-in queue is full; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )
        await self._enforce_count(
            db,
            conditions=(
                *ledger_filter,
                WebAuthnChallenge.created_at > history_cutoff,
            ),
            quota=policy.global_rate_quota,
            message="The passkey sign-in rate capacity is full; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )
        await self._enforce_count(
            db,
            conditions=(
                *ledger_filter,
                WebAuthnChallenge.source_fingerprint
                == challenge.source_fingerprint,
                WebAuthnChallenge.consumed_at.is_(None),
                WebAuthnChallenge.expires_at > now,
            ),
            quota=policy.per_source_outstanding_quota,
            message="This client has too many pending passkey sign-ins; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )
        await self._enforce_count(
            db,
            conditions=(
                *ledger_filter,
                WebAuthnChallenge.source_fingerprint
                == challenge.source_fingerprint,
                WebAuthnChallenge.created_at > history_cutoff,
            ),
            quota=policy.per_source_rate_quota,
            message="Too many passkey sign-ins from this client; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )
        db.add(challenge)
        await db.flush()

    async def reserve_durably(
        self,
        db: AsyncSession,
        *,
        challenge: WebAuthnChallenge,
        policy: PasskeyChallengeRequestPolicy,
    ) -> None:
        """Commit admission before any costly, user-specific option work."""

        if db.bind is None:
            raise RuntimeError("Passkey admission requires a bound database session")
        reservation_sessions = async_sessionmaker(
            bind=db.bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with reservation_sessions() as reservation_db:
            try:
                await self.reserve(
                    reservation_db,
                    challenge=challenge,
                    policy=policy,
                )
                await reservation_db.commit()
            except Exception:
                await reservation_db.rollback()
                raise

    async def reserve_registration(
        self,
        db: AsyncSession,
        *,
        challenge: WebAuthnChallenge,
        policy: PasskeyChallengeRequestPolicy,
    ) -> None:
        """Bound authenticated registration work and keep one live ceremony per user."""

        if challenge.flow_type != "registration" or challenge.user_id is None:
            raise ValueError("Registration reservations require a user-bound challenge")

        now = datetime.now(timezone.utc)
        history_cutoff = now - timedelta(seconds=policy.rate_window_seconds)
        await db.execute(
            select(func.pg_advisory_xact_lock(_PASSKEY_CHALLENGE_ADVISORY_LOCK_ID))
        )
        registration_filter = (
            WebAuthnChallenge.flow_type == "registration",
            WebAuthnChallenge.user_id.is_not(None),
        )
        # Expired/consumed rows remain during the rate window, then any
        # ceremony path may remove them. This keeps authentication history
        # bounded even if the next traffic is registration-only. Pre-ledger
        # registration rows without an owner cannot contribute to a valid
        # ceremony or rate bucket and may be removed immediately.
        completed_or_expired = or_(
            WebAuthnChallenge.consumed_at.is_not(None),
            WebAuthnChallenge.expires_at <= now,
        )
        await db.execute(
            delete(WebAuthnChallenge).where(
                WebAuthnChallenge.created_at <= history_cutoff,
                completed_or_expired,
            )
        )
        await db.execute(
            delete(WebAuthnChallenge).where(
                WebAuthnChallenge.flow_type == "registration",
                WebAuthnChallenge.user_id.is_(None),
                completed_or_expired,
            )
        )

        # Replacing this user's current ceremony does not increase outstanding
        # global work, so exclude it from the global capacity calculation.
        await self._enforce_count(
            db,
            conditions=(
                *registration_filter,
                WebAuthnChallenge.user_id != challenge.user_id,
                WebAuthnChallenge.consumed_at.is_(None),
                WebAuthnChallenge.expires_at > now,
            ),
            quota=policy.registration_global_outstanding_quota,
            message="The passkey registration queue is full; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )
        await self._enforce_count(
            db,
            conditions=(
                *registration_filter,
                WebAuthnChallenge.created_at > history_cutoff,
            ),
            quota=policy.registration_global_rate_quota,
            message="The passkey registration rate capacity is full; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )
        await self._enforce_count(
            db,
            conditions=(
                *registration_filter,
                WebAuthnChallenge.user_id == challenge.user_id,
                WebAuthnChallenge.created_at > history_cutoff,
            ),
            quota=policy.registration_per_user_rate_quota,
            message="Too many passkey registrations for this account; retry later",
            retry_after_seconds=policy.retry_after_seconds,
        )

        await db.execute(
            update(WebAuthnChallenge)
            .where(
                *registration_filter,
                WebAuthnChallenge.user_id == challenge.user_id,
                WebAuthnChallenge.consumed_at.is_(None),
                WebAuthnChallenge.expires_at > now,
            )
            .values(consumed_at=now)
        )
        db.add(challenge)
        await db.flush()

    @staticmethod
    async def _enforce_count(
        db: AsyncSession,
        *,
        conditions: tuple,
        quota: int,
        message: str,
        retry_after_seconds: int,
    ) -> None:
        count = await db.scalar(
            select(func.count()).select_from(WebAuthnChallenge).where(*conditions)
        )
        if int(count or 0) >= quota:
            raise PasskeyChallengeRequestLimitError(
                message,
                retry_after_seconds=retry_after_seconds,
            )


passkey_challenge_request_service = PasskeyChallengeRequestService()


__all__ = [
    "PasskeyChallengeRequestLimitError",
    "PasskeyChallengeRequestPolicy",
    "PasskeyChallengeRequestService",
    "passkey_challenge_request_service",
    "passkey_source_fingerprint",
    "passkey_user_fingerprint",
]
