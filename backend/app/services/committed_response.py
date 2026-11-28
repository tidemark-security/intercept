"""Best-effort response hydration for already committed mutations."""

from collections.abc import Awaitable, Callable
from inspect import isawaitable
import logging
from typing import Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession


T = TypeVar("T")


async def detach_committed_state(db: AsyncSession, logger: logging.Logger) -> None:
    """Keep committed fallbacks usable if the response read must be rolled back."""
    try:
        maybe_awaitable = db.expunge_all()
        if isawaitable(maybe_awaitable):
            await maybe_awaitable
    except Exception:
        logger.exception(
            "Could not detach committed response state before response hydration"
        )


async def reset_post_commit_session(
    db: AsyncSession,
    logger: logging.Logger,
) -> None:
    """Clear a failed transaction opened after the owning mutation committed."""
    try:
        await db.rollback()
    except Exception:
        logger.exception(
            "Could not roll back failed post-commit work; invalidating the session"
        )
        try:
            await db.invalidate()
            return
        except Exception:
            logger.exception(
                "Could not invalidate the session after post-commit recovery failed; "
                "closing it"
            )
        try:
            await db.close()
        except Exception:
            logger.exception(
                "Could not close the session after post-commit recovery failed"
            )


async def load_committed_response(
    db: AsyncSession,
    loader: Callable[[], Awaitable[Optional[T]]],
    fallback: T,
    *,
    logger: logging.Logger,
    entity_type: str,
    entity_id: object,
    operation: str,
) -> T:
    """Hydrate a response without turning a durable mutation into a failure."""
    # ``rollback()`` expires attached ORM instances. Detach the committed graph
    # before starting the optional response read so it remains a usable fallback.
    await detach_committed_state(db, logger)

    try:
        loaded = await loader()
    except Exception:
        await reset_post_commit_session(db, logger)
        logger.exception(
            "%s %s was committed for %s %s, but response hydration failed; "
            "returning detached committed state",
            entity_type.title(),
            operation,
            entity_type,
            entity_id,
        )
        return fallback

    if loaded is None:
        await reset_post_commit_session(db, logger)
        logger.error(
            "%s %s was committed for %s %s, but response hydration returned no "
            "entity; returning detached committed state",
            entity_type.title(),
            operation,
            entity_type,
            entity_id,
        )
        return fallback
    return loaded
