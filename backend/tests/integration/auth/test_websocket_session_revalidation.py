from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.api.routes import websocket as websocket_route
from app.core.security import hash_opaque_token
from app.models.enums import SessionRevokedReason
from app.models.models import AuthSession, UserAccount
from app.services.realtime_service import ConnectionManager


class RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.closed_with: tuple[int, str] | None = None

    async def send_json(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    async def close(self, *, code: int, reason: str) -> None:
        self.closed_with = (code, reason)


@pytest.mark.asyncio
async def test_broadcast_crossing_committed_session_revocation_sends_nothing(
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broadcast may not authorize from a session snapshot older than revocation."""
    user = analyst_user_factory(username="websocket-revocation-race")
    session_token = "websocket-revocation-race-token"
    now = datetime.now(timezone.utc)
    auth_session = AuthSession(
        id=uuid4(),
        user_id=user.id,
        session_token_hash=hash_opaque_token(session_token),
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )
    async with session_maker() as setup_db:
        setup_db.add(user)
        await setup_db.flush()
        setup_db.add(auth_session)
        await setup_db.commit()

    session_snapshot_read = asyncio.Event()

    class SignallingRevalidationSession(AsyncSession):
        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            is_session_read = (
                str(statement).lstrip().upper().startswith("SELECT")
                and "auth_sessions" in str(statement)
            )
            result = await super().execute(statement, *args, **kwargs)
            if is_session_read:
                session_snapshot_read.set()
            return result

    revalidation_session_maker = async_sessionmaker(
        async_engine,
        expire_on_commit=False,
        class_=SignallingRevalidationSession,
    )
    monkeypatch.setattr(
        websocket_route,
        "async_session_factory",
        revalidation_session_maker,
    )

    async def publish_presence(_: dict[str, Any]) -> None:
        return None

    manager = ConnectionManager(
        node_id="websocket-revocation-race-node",
        presence_publisher=publish_presence,
    )
    websocket = cast(WebSocket, RecordingWebSocket())
    await manager.connect(websocket, session_token, user.username)
    assert await manager.subscribe(websocket, "case", 12) is True
    cast(Any, websocket).messages.clear()
    manager.set_session_validator(websocket_route._revalidate_session)

    event = {"type": "event", "payload": {"entity_id": 12}}
    async with session_maker() as revocation_db:
        locked_user = await revocation_db.get(
            UserAccount,
            user.id,
            populate_existing=True,
            with_for_update=True,
        )
        assert locked_user is not None
        locked_session = await revocation_db.get(
            AuthSession,
            auth_session.id,
            populate_existing=True,
            with_for_update=True,
        )
        assert locked_session is not None
        locked_session.revoked_at = datetime.now(timezone.utc)
        locked_session.revoked_reason = SessionRevokedReason.ADMIN_FORCE
        await revocation_db.flush()

        broadcast_task = asyncio.create_task(manager.broadcast("case", 12, event))
        await asyncio.wait_for(session_snapshot_read.wait(), timeout=2)
        await revocation_db.commit()

    notified = await asyncio.wait_for(broadcast_task, timeout=2)

    assert notified == set()
    assert manager.active_connections == 0
    assert cast(Any, websocket).messages == []
    assert cast(Any, websocket).closed_with == (4001, "Session expired")
