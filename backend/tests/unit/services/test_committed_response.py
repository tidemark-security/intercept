from __future__ import annotations

import logging
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.committed_response import load_committed_response


class _RollbackOnlySession:
    """Small session double that models a failed SQLAlchemy read transaction."""

    def __init__(self, *, rollback_fails: bool = False) -> None:
        self.calls: list[str] = []
        self.rollback_only = False
        self.rollback_fails = rollback_fails

    def expunge_all(self) -> None:
        self.calls.append("detach")

    async def rollback(self) -> None:
        self.calls.append("rollback")
        if self.rollback_fails:
            raise RuntimeError("connection lost during rollback")
        self.rollback_only = False

    async def invalidate(self) -> None:
        self.calls.append("invalidate")
        self.rollback_only = False

    async def close(self) -> None:
        self.calls.append("close")
        self.rollback_only = False

    async def commit(self) -> None:
        self.calls.append("commit")
        if self.rollback_only:
            raise RuntimeError("session transaction must be rolled back")


@pytest.mark.asyncio
async def test_failed_response_read_is_reset_before_returning_committed_fallback() -> None:
    session = _RollbackOnlySession()
    fallback = object()

    async def fail_response_read() -> object:
        session.calls.append("load")
        session.rollback_only = True
        raise RuntimeError("response SELECT failed")

    result = await load_committed_response(
        cast(AsyncSession, session),
        fail_response_read,
        fallback,
        logger=logging.getLogger(__name__),
        entity_type="alert",
        entity_id=7,
        operation="update",
    )

    assert result is fallback
    assert session.calls == ["detach", "load", "rollback"]

    # Mirrors get_db() teardown: cleanup of the failed response read makes the
    # dependency's final commit safe instead of surfacing a false mutation error.
    await session.commit()
    assert session.calls[-1] == "commit"


@pytest.mark.asyncio
async def test_missing_response_is_rolled_back_before_returning_fallback() -> None:
    session = _RollbackOnlySession()
    fallback = object()

    async def missing_response() -> None:
        session.calls.append("load")
        return None

    result = await load_committed_response(
        cast(AsyncSession, session),
        missing_response,
        fallback,
        logger=logging.getLogger(__name__),
        entity_type="task",
        entity_id=3,
        operation="creation",
    )

    assert result is fallback
    assert session.calls == ["detach", "load", "rollback"]


@pytest.mark.asyncio
async def test_failed_cleanup_invalidates_session_and_keeps_fallback_safe() -> None:
    session = _RollbackOnlySession(rollback_fails=True)
    fallback = object()

    async def fail_response_read() -> object:
        session.calls.append("load")
        session.rollback_only = True
        raise RuntimeError("response SELECT failed")

    result = await load_committed_response(
        cast(AsyncSession, session),
        fail_response_read,
        fallback,
        logger=logging.getLogger(__name__),
        entity_type="case",
        entity_id=4,
        operation="update",
    )

    assert result is fallback
    assert session.calls == ["detach", "load", "rollback", "invalidate"]

    await session.commit()
    assert session.calls[-1] == "commit"
