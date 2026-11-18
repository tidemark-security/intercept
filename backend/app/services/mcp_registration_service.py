"""Durable abuse controls for unauthenticated MCP OAuth entry points."""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Callable
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import (
    MCPDCRRegistration,
    MCPOAuthAuthorizationCapacity,
    MCPOAuthAuthorizationCode,
    MCPOAuthClient,
    MCPOAuthConsent,
    MCPOAuthPendingAuthorization,
    MCPOAuthProviderGrantReference,
    MCPOAuthToken,
)
from app.services.mcp_oauth_epoch import next_mcp_oauth_grant_epoch


# One transaction-wide lock serializes the small global quota ledger across all
# workers. The critical section contains indexed counts and cleanup only.
_DCR_ADVISORY_LOCK_ID = 0x544D_4944_4352
_AUTHORIZATION_CAPACITY_ADVISORY_LOCK_ID = 0x544D_4944_4155
_registration_source_ip: ContextVar[str] = ContextVar(
    "mcp_registration_source_ip",
    default="unknown",
)
_authorization_request_active: ContextVar[bool] = ContextVar(
    "mcp_authorization_request_active",
    default=False,
)


@dataclass(frozen=True, slots=True)
class MCPRegistrationPolicy:
    """Startup-frozen limits for public MCP OAuth entry points."""

    max_body_bytes: int = 64 * 1024
    pending_quota: int = 1_000
    total_quota: int = 5_000
    per_ip_quota: int = 600
    rate_window_seconds: int = 60 * 60
    abandoned_ttl_seconds: int = 60 * 60
    active_ttl_seconds: int = 30 * 24 * 60 * 60
    pending_authorization_global_quota: int = 1_000
    pending_authorization_per_client_quota: int = 10
    pending_authorization_per_source_quota: int = 50
    cimd_fetch_reservation_ttl_seconds: int = 60
    cimd_cache_max_entries: int = 256
    client_assertion_replay_global_quota: int = 100_000
    client_assertion_replay_per_client_quota: int = 10_000


@dataclass(frozen=True, slots=True)
class MCPRegistrationReservation:
    """Reservation result containing stale native clients to remove."""

    expired_client_ids: tuple[str, ...]


class MCPRegistrationLimitError(RuntimeError):
    """Raised when a durable DCR quota rejects a registration."""


class MCPRegistrationExpiredError(RuntimeError):
    """Raised when a tracked DCR client attempts to use an expired lease."""


class MCPAuthorizationCapacityLimitError(RuntimeError):
    """Raised when an unauthenticated authorization exceeds durable capacity."""


def registration_source_ip() -> str:
    """Return the trusted-proxy-resolved source for the current public request."""

    return _registration_source_ip.get()


def bind_registration_source_ip(source_ip: str) -> Token[str]:
    """Bind the validated request source for the current asynchronous request."""

    normalized = str(source_ip or "unknown").strip()[:64] or "unknown"
    return _registration_source_ip.set(normalized)


def reset_registration_source_ip(token: Token[str]) -> None:
    """Restore the previous public-request source context."""

    _registration_source_ip.reset(token)


def authorization_request_active() -> bool:
    """Return whether the current ASGI task is serving an authorize request."""

    return _authorization_request_active.get()


def bind_authorization_request() -> Token[bool]:
    """Mark the current asynchronous request as an OAuth authorization request."""

    return _authorization_request_active.set(True)


def reset_authorization_request(token: Token[bool]) -> None:
    """Restore the previous authorization-request context."""

    _authorization_request_active.reset(token)


class MCPOAuthAuthorizationCapacityService:
    """Serialize and clean durable pending-authorization reservations."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        policy: MCPRegistrationPolicy,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.policy = policy
        self._now = now or (lambda: datetime.now(timezone.utc))

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def reserve(
        self,
        *,
        reservation_id: str,
        client_id: str,
        provider_mode: str,
        ttl_seconds: int,
        source_ip: str | None = None,
    ) -> int:
        """Atomically reserve global, client, and trusted-source capacity."""

        now = self._now()
        normalized_source = str(
            source_ip if source_ip is not None else registration_source_ip()
        ).strip()[:64] or "unknown"
        async with self._session() as session:
            await self._lock(session)
            await self._cleanup(session, now=now)

            global_count = await session.scalar(
                select(func.count())
                .select_from(MCPOAuthAuthorizationCapacity)
                .where(MCPOAuthAuthorizationCapacity.expires_at > now)
            )
            if int(global_count or 0) >= self.policy.pending_authorization_global_quota:
                raise MCPAuthorizationCapacityLimitError(
                    "The MCP authorization queue is full; retry later"
                )

            client_count = await session.scalar(
                select(func.count())
                .select_from(MCPOAuthAuthorizationCapacity)
                .where(
                    MCPOAuthAuthorizationCapacity.client_id == client_id,
                    MCPOAuthAuthorizationCapacity.expires_at > now,
                )
            )
            if (
                int(client_count or 0)
                >= self.policy.pending_authorization_per_client_quota
            ):
                raise MCPAuthorizationCapacityLimitError(
                    "This MCP client has too many pending authorizations; retry later"
                )

            source_count = await session.scalar(
                select(func.count())
                .select_from(MCPOAuthAuthorizationCapacity)
                .where(
                    MCPOAuthAuthorizationCapacity.source_ip == normalized_source,
                    MCPOAuthAuthorizationCapacity.expires_at > now,
                )
            )
            if (
                int(source_count or 0)
                >= self.policy.pending_authorization_per_source_quota
            ):
                raise MCPAuthorizationCapacityLimitError(
                    "This source has too many pending MCP authorizations; retry later"
                )

            authorization_epoch = await next_mcp_oauth_grant_epoch(session)
            session.add(
                MCPOAuthAuthorizationCapacity(
                    reservation_id=reservation_id[:128],
                    client_id=client_id,
                    provider_mode=provider_mode[:32],
                    source_ip=normalized_source,
                    authorization_epoch=authorization_epoch,
                    created_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
            )
            await session.flush()
            return authorization_epoch

    async def promote(
        self,
        *,
        reservation_id: str,
        pending_id: str,
        client_id: str,
        provider_mode: str,
        ttl_seconds: int,
    ) -> int:
        """Bind a pre-fetch reservation to its durable pending request ID."""

        now = self._now()
        async with self._session() as session:
            await self._lock(session)
            await self._cleanup(session, now=now)
            row = await session.scalar(
                select(MCPOAuthAuthorizationCapacity)
                .where(
                    MCPOAuthAuthorizationCapacity.reservation_id == reservation_id
                )
                .with_for_update()
            )
            if row is None or row.expires_at <= now or row.client_id != client_id:
                raise MCPAuthorizationCapacityLimitError(
                    "The MCP authorization reservation expired; retry later"
                )
            authorization_epoch = await next_mcp_oauth_grant_epoch(session)
            row.reservation_id = pending_id[:128]
            row.provider_mode = provider_mode[:32]
            row.authorization_epoch = authorization_epoch
            row.expires_at = now + timedelta(seconds=ttl_seconds)
            await session.flush()
            return authorization_epoch

    async def refresh(
        self,
        *,
        reservation_id: str,
        client_id: str,
        provider_mode: str,
        ttl_seconds: int,
    ) -> int:
        """Extend an existing reservation without changing its causal epoch."""

        async with self._session() as session:
            await self._lock(session)
            now = self._now()
            row = await session.scalar(
                select(MCPOAuthAuthorizationCapacity)
                .where(
                    MCPOAuthAuthorizationCapacity.reservation_id
                    == reservation_id[:128]
                )
                .with_for_update()
            )
            if row is None or row.expires_at <= now:
                raise MCPAuthorizationCapacityLimitError(
                    "The MCP authorization transaction expired; retry later"
                )
            if (
                row.client_id != client_id
                or row.provider_mode != provider_mode[:32]
            ):
                raise MCPAuthorizationCapacityLimitError(
                    "The MCP authorization transaction does not match this request"
                )
            row.expires_at = max(
                row.expires_at,
                now + timedelta(seconds=ttl_seconds),
            )
            await session.flush()
            return row.authorization_epoch

    async def require_authorization_epoch(self, reservation_id: str) -> int:
        """Load the database-issued epoch bound to an OIDC transaction."""

        async with self._session() as session:
            epoch = await session.scalar(
                select(MCPOAuthAuthorizationCapacity.authorization_epoch).where(
                    MCPOAuthAuthorizationCapacity.reservation_id
                    == reservation_id[:128]
                )
            )
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch <= 0:
            raise MCPAuthorizationCapacityLimitError(
                "The MCP authorization transaction is no longer active"
            )
        return epoch

    async def release(
        self,
        reservation_id: str,
        *,
        cleanup_pending: bool = False,
    ) -> None:
        """Release a completed/failed reservation and optionally its local handoff."""

        now = self._now()
        async with self._session() as session:
            await self._lock(session)
            await session.execute(
                delete(MCPOAuthAuthorizationCapacity).where(
                    MCPOAuthAuthorizationCapacity.reservation_id == reservation_id
                )
            )
            if cleanup_pending:
                try:
                    request_id = UUID(reservation_id)
                except ValueError:
                    request_id = None
                if request_id is not None:
                    await session.execute(
                        delete(MCPOAuthPendingAuthorization).where(
                            MCPOAuthPendingAuthorization.id == request_id,
                            MCPOAuthPendingAuthorization.consumed_at.is_not(None),
                        )
                    )
            await self._cleanup(session, now=now)

    @staticmethod
    async def _cleanup(session: AsyncSession, *, now: datetime) -> None:
        """Remove expired capacity, stale handoffs, and orphan CIMD projections."""

        await session.execute(
            delete(MCPOAuthAuthorizationCapacity).where(
                MCPOAuthAuthorizationCapacity.expires_at <= now
            )
        )
        stale_pending_rows = tuple(
            (
                request_id,
                consumed_at,
                expires_at,
            )
            for request_id, consumed_at, expires_at in (
                await session.execute(
                    select(
                        MCPOAuthPendingAuthorization.id,
                        MCPOAuthPendingAuthorization.consumed_at,
                        MCPOAuthPendingAuthorization.expires_at,
                    ).where(
                        (MCPOAuthPendingAuthorization.consumed_at.is_not(None))
                        | (MCPOAuthPendingAuthorization.expires_at <= now)
                    )
                )
            ).all()
        )
        candidate_reservation_ids = tuple(
            str(request_id)
            for request_id, _consumed_at, _expires_at in stale_pending_rows
        )
        active_reservation_ids = (
            set(
                await session.scalars(
                    select(MCPOAuthAuthorizationCapacity.reservation_id).where(
                        MCPOAuthAuthorizationCapacity.reservation_id.in_(
                            candidate_reservation_ids
                        )
                    )
                )
            )
            if candidate_reservation_ids
            else set()
        )
        stale_pending_ids = tuple(
            request_id
            for request_id, consumed_at, expires_at in stale_pending_rows
            if expires_at <= now
            or (consumed_at is not None and str(request_id) not in active_reservation_ids)
        )
        if stale_pending_ids:
            stale_reservation_ids = tuple(
                str(request_id) for request_id in stale_pending_ids
            )
            await session.execute(
                delete(MCPOAuthAuthorizationCapacity).where(
                    MCPOAuthAuthorizationCapacity.reservation_id.in_(
                        stale_reservation_ids
                    )
                )
            )
            await session.execute(
                delete(MCPOAuthPendingAuthorization).where(
                    MCPOAuthPendingAuthorization.id.in_(stale_pending_ids)
                )
            )

        orphan_cimd_ids = tuple(
            await session.scalars(
                select(MCPOAuthClient.id).where(
                    MCPOAuthClient.client_id.ilike("https://%"),
                    ~select(MCPOAuthPendingAuthorization.id)
                    .where(
                        MCPOAuthPendingAuthorization.client_db_id
                        == MCPOAuthClient.id
                    )
                    .exists(),
                    ~select(MCPOAuthAuthorizationCode.id)
                    .where(
                        MCPOAuthAuthorizationCode.client_db_id == MCPOAuthClient.id
                    )
                    .exists(),
                    ~select(MCPOAuthToken.id)
                    .where(MCPOAuthToken.client_db_id == MCPOAuthClient.id)
                    .exists(),
                    ~select(MCPOAuthConsent.id)
                    .where(MCPOAuthConsent.client_db_id == MCPOAuthClient.id)
                    .exists(),
                    ~select(MCPOAuthAuthorizationCapacity.reservation_id)
                    .where(
                        MCPOAuthAuthorizationCapacity.client_id
                        == MCPOAuthClient.client_id
                    )
                    .exists(),
                )
            )
        )
        if orphan_cimd_ids:
            await session.execute(
                delete(MCPOAuthClient).where(MCPOAuthClient.id.in_(orphan_cimd_ids))
            )

    @staticmethod
    async def _lock(session: AsyncSession) -> None:
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    _AUTHORIZATION_CAPACITY_ADVISORY_LOCK_ID
                )
            )
        )


class MCPDCRRegistrationService:
    """Reserve, activate, and expire DCR clients with PostgreSQL serialization."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        policy: MCPRegistrationPolicy,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.policy = policy
        self._now = now or (lambda: datetime.now(timezone.utc))

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def reserve(
        self,
        *,
        client_id: str,
        provider_mode: str,
        source_ip: str | None = None,
    ) -> MCPRegistrationReservation:
        """Atomically clean stale clients and reserve one pending registration."""

        now = self._now()
        source = (source_ip or registration_source_ip()).strip()[:64] or "unknown"
        policy = self.policy
        async with self._session() as session:
            await self._lock(session)
            expired_rows = tuple(
                (
                    str(client_id),
                    str(expired_provider_mode),
                )
                for client_id, expired_provider_mode in (
                    await session.execute(
                        select(
                            MCPDCRRegistration.client_id,
                            MCPDCRRegistration.provider_mode,
                        ).where(MCPDCRRegistration.expires_at <= now)
                    )
                ).all()
            )
            expired_ids = tuple(client_id for client_id, _mode in expired_rows)
            recent_from_source = await session.scalar(
                select(func.count())
                .select_from(MCPDCRRegistration)
                .where(
                    MCPDCRRegistration.source_ip == source,
                    MCPDCRRegistration.created_at
                    > now - timedelta(seconds=policy.rate_window_seconds),
                )
            )
            if expired_ids:
                await self._delete_expired_client_state(session, expired_ids)
            expired_oidc_ids = tuple(
                client_id
                for client_id, expired_mode in expired_rows
                if expired_mode == "oidc"
            )
            if expired_ids:
                # Consume cleanup ownership while the global advisory lock is
                # still held. Native OIDC deletion happens after this transaction;
                # a failure may leave an inaccessible native orphan, but another
                # public registration cannot claim and replay the same work.
                await session.execute(
                    delete(MCPDCRRegistration).where(
                        MCPDCRRegistration.client_id.in_(expired_ids),
                        MCPDCRRegistration.expires_at <= now,
                    )
                )

            total_count = await session.scalar(
                select(func.count())
                .select_from(MCPDCRRegistration)
                .where(MCPDCRRegistration.expires_at > now)
            )
            if int(total_count or 0) >= policy.total_quota:
                raise MCPRegistrationLimitError(
                    "The MCP registration capacity is full; retry after inactive "
                    "clients expire"
                )

            pending_count = await session.scalar(
                select(func.count())
                .select_from(MCPDCRRegistration)
                .where(
                    MCPDCRRegistration.activated_at.is_(None),
                    MCPDCRRegistration.expires_at > now,
                )
            )
            if int(pending_count or 0) >= policy.pending_quota:
                raise MCPRegistrationLimitError(
                    "The MCP registration queue is full; retry after existing "
                    "registrations expire"
                )

            if int(recent_from_source or 0) >= policy.per_ip_quota:
                raise MCPRegistrationLimitError(
                    "Too many MCP registrations from this client; retry later"
                )

            session.add(
                MCPDCRRegistration(
                    client_id=client_id,
                    provider_mode=provider_mode[:32],
                    source_ip=source,
                    created_at=now,
                    expires_at=now
                    + timedelta(seconds=policy.abandoned_ttl_seconds),
                )
            )
            await session.flush()
            return MCPRegistrationReservation(
                expired_client_ids=(
                    expired_oidc_ids if provider_mode == "oidc" else ()
                )
            )

    async def require_valid(self, client_id: str) -> bool:
        """Require an unexpired lease recorded in the durable DCR ledger."""

        now = self._now()
        async with self._session() as session:
            await self._lock(session)
            row = await session.scalar(
                select(MCPDCRRegistration)
                .where(MCPDCRRegistration.client_id == client_id)
                .with_for_update()
            )
            if row is None:
                raise MCPRegistrationExpiredError(
                    "The MCP client registration is not recognized"
                )
            if row.expires_at <= now:
                raise MCPRegistrationExpiredError(
                    "The MCP client registration has expired"
                )
            return True

    async def activate(self, client_id: str) -> bool:
        """Mark a DCR client as used by an authorization request."""

        now = self._now()
        async with self._session() as session:
            await self._lock(session)
            row = await session.scalar(
                select(MCPDCRRegistration)
                .where(MCPDCRRegistration.client_id == client_id)
                .with_for_update()
            )
            if row is None:
                raise MCPRegistrationExpiredError(
                    "The MCP client registration is not recognized"
                )
            if row.expires_at <= now:
                raise MCPRegistrationExpiredError(
                    "The MCP client registration has expired"
                )
            row.activated_at = row.activated_at or now
            row.expires_at = now + timedelta(seconds=self.policy.active_ttl_seconds)
            return True

    async def release(self, client_id: str) -> None:
        """Release a reservation when native provider persistence fails."""

        async with self._session() as session:
            await self._lock(session)
            await session.execute(
                delete(MCPDCRRegistration).where(
                    MCPDCRRegistration.client_id == client_id,
                    MCPDCRRegistration.activated_at.is_(None),
                )
            )

    async def finalize_expired(self, client_ids: tuple[str, ...]) -> None:
        """Idempotently finalize cleanup claimed during reservation."""

        if not client_ids:
            return
        now = self._now()
        async with self._session() as session:
            await self._lock(session)
            await session.execute(
                delete(MCPDCRRegistration).where(
                    MCPDCRRegistration.client_id.in_(client_ids),
                    MCPDCRRegistration.expires_at <= now,
                )
            )

    @staticmethod
    async def _delete_expired_client_state(
        session: AsyncSession,
        client_ids: tuple[str, ...],
    ) -> None:
        """Remove expired native clients and their live OAuth state.

        Audit records are independent and intentionally remain available. OIDC
        native key-value registrations are returned to the proxy for deletion.
        """

        client_db_ids = tuple(
            await session.scalars(
                select(MCPOAuthClient.id).where(
                    MCPOAuthClient.client_id.in_(client_ids)
                )
            )
        )
        if client_db_ids:
            consent_ids = tuple(
                await session.scalars(
                    select(MCPOAuthConsent.id).where(
                        MCPOAuthConsent.client_db_id.in_(client_db_ids)
                    )
                )
            )
            if consent_ids:
                await session.execute(
                    delete(MCPOAuthProviderGrantReference).where(
                        MCPOAuthProviderGrantReference.consent_id.in_(consent_ids)
                    )
                )
            await session.execute(
                delete(MCPOAuthToken).where(
                    MCPOAuthToken.client_db_id.in_(client_db_ids)
                )
            )
            await session.execute(
                delete(MCPOAuthAuthorizationCode).where(
                    MCPOAuthAuthorizationCode.client_db_id.in_(client_db_ids)
                )
            )
            await session.execute(
                delete(MCPOAuthPendingAuthorization).where(
                    MCPOAuthPendingAuthorization.client_db_id.in_(client_db_ids)
                )
            )
            await session.execute(
                delete(MCPOAuthConsent).where(
                    MCPOAuthConsent.client_db_id.in_(client_db_ids)
                )
            )
            await session.execute(
                delete(MCPOAuthClient).where(MCPOAuthClient.id.in_(client_db_ids))
            )

    @staticmethod
    async def _lock(session: AsyncSession) -> None:
        await session.execute(
            select(func.pg_advisory_xact_lock(_DCR_ADVISORY_LOCK_ID))
        )


__all__ = [
    "MCPDCRRegistrationService",
    "MCPOAuthAuthorizationCapacityService",
    "MCPAuthorizationCapacityLimitError",
    "MCPRegistrationExpiredError",
    "MCPRegistrationLimitError",
    "MCPRegistrationPolicy",
    "MCPRegistrationReservation",
    "authorization_request_active",
    "bind_authorization_request",
    "bind_registration_source_ip",
    "registration_source_ip",
    "reset_authorization_request",
    "reset_registration_source_ip",
]
