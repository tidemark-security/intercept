"""Cluster-wide replay claims for FastMCP private_key_jwt authentication."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
_CLIENT_ID_HASH_DOMAIN = b"intercept:mcp-client-assertion:client-id:\x00"
_JTI_HASH_DOMAIN = b"intercept:mcp-client-assertion:jti:\x00"
MAX_CLIENT_ASSERTION_JTI_BYTES = 512
MAX_MCP_CLIENT_ID_BYTES = 2048
MAX_REPLAY_RESERVATION_LIFETIME_SECONDS = 420
DEFAULT_MAX_REPLAY_LEDGER_ROWS = 100_000
DEFAULT_MAX_REPLAY_LEDGER_ROWS_PER_CLIENT = 10_000
MCP_CLIENT_ASSERTION_REPLAY_CAPACITY_LOCK_ID = 0x544D_4944_4A54


class MCPClientAssertionReplayError(ValueError):
    """Raised when an unexpired client assertion has already been claimed."""


class MCPClientAssertionReplayStoreError(RuntimeError):
    """Raised when replay state cannot be committed durably."""


class MCPClientAssertionReplayCapacityError(MCPClientAssertionReplayStoreError):
    """Raised when a new claim would exceed the durable ledger bound."""


class MCPClientAssertionReplayBusyError(MCPClientAssertionReplayStoreError):
    """Raised when another worker owns the short capacity critical section."""


def _digest_component(domain: bytes, value: str) -> str:
    return hashlib.sha256(domain + value.encode("utf-8")).hexdigest()


def assertion_replay_digests(client_id: str, jti: str) -> tuple[str, str]:
    """Return fixed-size, domain-separated ledger keys without storing raw claims."""

    return (
        _digest_component(_CLIENT_ID_HASH_DOMAIN, client_id),
        _digest_component(_JTI_HASH_DOMAIN, jti),
    )


class MCPClientAssertionReplayService:
    """Atomically claim validated client assertions across all app workers."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        now: Callable[[], datetime] | None = None,
        max_rows: int = DEFAULT_MAX_REPLAY_LEDGER_ROWS,
        max_rows_per_client: int = DEFAULT_MAX_REPLAY_LEDGER_ROWS_PER_CLIENT,
    ) -> None:
        if max_rows <= 0 or max_rows_per_client <= 0:
            raise ValueError("Client assertion replay capacities must be positive")
        if max_rows_per_client > max_rows:
            raise ValueError(
                "Per-client assertion replay capacity cannot exceed global capacity"
            )
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._max_rows = max_rows
        self._max_rows_per_client = max_rows_per_client

    async def reserve(
        self,
        *,
        client_id: str,
        jti: str,
        expires_at: datetime,
    ) -> None:
        """Claim ``(client_id, jti)`` or reject an active duplicate."""

        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("Client assertion client_id must be a non-empty string")
        if len(client_id.encode("utf-8")) > MAX_MCP_CLIENT_ID_BYTES:
            raise ValueError("Client assertion client_id is too long")
        if not isinstance(jti, str) or not jti.strip():
            raise ValueError("Client assertion jti must be a non-empty string")
        if len(jti.encode("utf-8")) > MAX_CLIENT_ASSERTION_JTI_BYTES:
            raise ValueError("Client assertion jti is too long")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("Client assertion replay expiry must be timezone-aware")
        now = self._now()
        if expires_at <= now:
            raise ValueError("Client assertion replay expiry must be in the future")
        if expires_at > now + timedelta(
            seconds=MAX_REPLAY_RESERVATION_LIFETIME_SECONDS
        ):
            raise ValueError("Client assertion replay expiry is too far in the future")
        client_id_hash, jti_hash = assertion_replay_digests(client_id, jti)
        # The database clock is authoritative at the instant the row is claimed.
        # This prevents a validated assertion that waited on a pool or row lock from
        # being accepted after its replay deadline, and keeps conflict replacement
        # in the same atomic statement as initial insertion.
        claim_statement = text(
            "INSERT INTO mcp_oauth_client_assertion_jtis AS existing "
            "(client_id_hash, jti_hash, created_at, expires_at) "
            "SELECT :client_id_hash, :jti_hash, clock_timestamp(), "
            "CAST(:expires_at AS TIMESTAMPTZ) "
            "WHERE CAST(:expires_at AS TIMESTAMPTZ) > clock_timestamp() "
            "ON CONFLICT (client_id_hash, jti_hash) DO UPDATE SET "
            "created_at = EXCLUDED.created_at, "
            "expires_at = EXCLUDED.expires_at "
            "WHERE existing.expires_at <= clock_timestamp() "
            "AND EXCLUDED.expires_at > clock_timestamp() "
            "RETURNING jti_hash, "
            "expires_at > clock_timestamp() AS deadline_valid"
        )

        try:
            async with self._session_factory() as db:
                # Serialize this small capacity-and-claim critical section, but
                # never let waiters occupy the shared application DB pool. pg_cron
                # deletes can proceed independently and only create more headroom.
                lock_acquired = bool(
                    (
                        await db.execute(
                            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                            {
                                "lock_id": (
                                    MCP_CLIENT_ASSERTION_REPLAY_CAPACITY_LOCK_ID
                                )
                            },
                        )
                    ).scalar_one()
                )
                if not lock_acquired:
                    await db.rollback()
                    raise MCPClientAssertionReplayBusyError(
                        "Client assertion replay protection is busy"
                    )
                capacity = (
                    await db.execute(
                        text(
                            "SELECT "
                            "(SELECT count(*) FROM "
                            "mcp_oauth_client_assertion_jtis) AS total_rows, "
                            "(SELECT count(*) FROM "
                            "mcp_oauth_client_assertion_jtis "
                            "WHERE client_id_hash = :client_id_hash) "
                            "AS client_rows, "
                            "EXISTS(SELECT 1 FROM "
                            "mcp_oauth_client_assertion_jtis "
                            "WHERE client_id_hash = :client_id_hash "
                            "AND jti_hash = :jti_hash) AS key_exists"
                        ),
                        {
                            "client_id_hash": client_id_hash,
                            "jti_hash": jti_hash,
                        },
                    )
                ).mappings().one()
                if not bool(capacity["key_exists"]) and (
                    int(capacity["total_rows"]) >= self._max_rows
                    or int(capacity["client_rows"])
                    >= self._max_rows_per_client
                ):
                    await db.rollback()
                    raise MCPClientAssertionReplayCapacityError(
                        "Client assertion replay protection is at capacity"
                    )
                result = await db.execute(
                    claim_statement,
                    {
                        "client_id_hash": client_id_hash,
                        "jti_hash": jti_hash,
                        "expires_at": expires_at,
                    },
                )
                claim = result.mappings().one_or_none()
                claimed = claim is not None and bool(claim["deadline_valid"])
                if claimed:
                    await db.commit()
                else:
                    await db.rollback()
        except (OSError, SQLAlchemyError) as exc:
            logger.exception("MCP client assertion replay ledger is unavailable")
            raise MCPClientAssertionReplayStoreError(
                "Client assertion replay protection is unavailable"
            ) from exc

        if not claimed:
            raise MCPClientAssertionReplayError("Client assertion replay detected")


__all__ = [
    "DEFAULT_MAX_REPLAY_LEDGER_ROWS",
    "DEFAULT_MAX_REPLAY_LEDGER_ROWS_PER_CLIENT",
    "MCP_CLIENT_ASSERTION_REPLAY_CAPACITY_LOCK_ID",
    "MCPClientAssertionReplayBusyError",
    "MCPClientAssertionReplayCapacityError",
    "MCPClientAssertionReplayError",
    "MCPClientAssertionReplayService",
    "MCPClientAssertionReplayStoreError",
    "MAX_CLIENT_ASSERTION_JTI_BYTES",
    "MAX_MCP_CLIENT_ID_BYTES",
    "MAX_REPLAY_RESERVATION_LIFETIME_SECONDS",
    "assertion_replay_digests",
]
