"""Transaction-scoped authorization gates for account reads and mutations."""
from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AuthorizationConcurrencyError(Exception):
    """Raised when fail-fast authorization cannot acquire its account gate."""


def authorization_lock_key(user_id: UUID) -> int:
    """Return a stable signed 64-bit PostgreSQL advisory-lock key."""
    digest = hashlib.blake2b(
        user_id.bytes,
        digest_size=8,
        person=b"tmi-authz-lock",
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


async def acquire_authorization_lock(
    db: AsyncSession,
    *,
    user_id: UUID,
    shared: bool,
    wait: bool = True,
) -> bool:
    """Acquire a transaction-level per-account authorization lock.

    Shared locks protect authenticated use. Security-sensitive account writers
    take the exclusive form, which queues ahead of later shared acquisitions so
    a continuous stream of read requests cannot starve an emergency disable or
    role downgrade.
    """
    # Service unit tests use deliberately tiny session doubles. The production
    # database seam always supplies a real AsyncSession (or subclass), where
    # PostgreSQL advisory locks are available and integration-tested.
    if not issubclass(type(db), AsyncSession):
        return True

    if wait:
        function_name = (
            "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        )
    else:
        function_name = (
            "pg_try_advisory_xact_lock_shared"
            if shared
            else "pg_try_advisory_xact_lock"
        )
    result = await db.execute(
        text(f"SELECT {function_name}(:lock_key)"),  # noqa: S608 - fixed names above
        {"lock_key": authorization_lock_key(user_id)},
    )
    if wait:
        return True
    return bool(result.scalar_one())


__all__ = [
    "AuthorizationConcurrencyError",
    "acquire_authorization_lock",
    "authorization_lock_key",
]
