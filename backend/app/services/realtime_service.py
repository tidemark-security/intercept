"""
Real-time notification service using PostgreSQL LISTEN/NOTIFY.

Provides multi-node WebSocket event fan-out without external dependencies.
Each backend node maintains a dedicated asyncpg connection for LISTEN on
the 'timeline_events' channel. When a mutation commits, pg_notify() is
called within the same transaction — PostgreSQL holds delivery until commit.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

import asyncpg
from fastapi import WebSocket
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings_registry import get_local
from app.models.enums import RealtimeEventType

logger = logging.getLogger(__name__)

CHANNEL = "timeline_events"
HEARTBEAT_INTERVAL = 30  # seconds


def _get_raw_dsn() -> str:
    """Convert the SQLAlchemy DSN to a raw asyncpg DSN."""
    url = get_local("database.url")
    # SQLAlchemy uses 'postgresql+asyncpg://', asyncpg needs 'postgresql://'
    return url.replace("postgresql+asyncpg://", "postgresql://")


class ConnectionManager:
    """Manages WebSocket connections and subscription routing."""

    def __init__(self) -> None:
        # ws → set of subscription keys ("alert:5", "case:12")
        self._connections: Dict[WebSocket, Set[str]] = {}
        # subscription key → set of WebSockets
        self._subscriptions: Dict[str, Set[WebSocket]] = {}
        # ws → session token (for re-validation)
        self._session_tokens: Dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    async def connect(self, ws: WebSocket, session_token: str) -> None:
        async with self._lock:
            self._connections[ws] = set()
            self._session_tokens[ws] = session_token

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            keys = self._connections.pop(ws, set())
            self._session_tokens.pop(ws, None)
            for key in keys:
                subs = self._subscriptions.get(key)
                if subs:
                    subs.discard(ws)
                    if not subs:
                        del self._subscriptions[key]

    async def subscribe(self, ws: WebSocket, entity_type: str, entity_id: int) -> None:
        key = f"{entity_type}:{entity_id}"
        async with self._lock:
            if ws not in self._connections:
                return
            self._connections[ws].add(key)
            self._subscriptions.setdefault(key, set()).add(ws)

    async def unsubscribe(self, ws: WebSocket, entity_type: str, entity_id: int) -> None:
        key = f"{entity_type}:{entity_id}"
        async with self._lock:
            conn_keys = self._connections.get(ws)
            if conn_keys:
                conn_keys.discard(key)
            subs = self._subscriptions.get(key)
            if subs:
                subs.discard(ws)
                if not subs:
                    del self._subscriptions[key]

    def get_session_token(self, ws: WebSocket) -> Optional[str]:
        return self._session_tokens.get(ws)

    async def broadcast(self, entity_type: str, entity_id: int, message: dict) -> set[WebSocket]:
        """Send message to all local subscribers of a specific entity.

        Returns the set of WebSockets that were notified (for dedup).
        """
        key = f"{entity_type}:{entity_id}"
        async with self._lock:
            subscribers = list(self._subscriptions.get(key, set()))

        await self._send_to_many(subscribers, message)
        return set(subscribers)

    async def broadcast_list(self, entity_type: str, message: dict, exclude: set[WebSocket] | None = None) -> None:
        """Send message to ALL connected clients for list invalidation.

        Any connected client may be viewing a list of this entity type,
        so we broadcast to everyone (minus those already notified).
        """
        async with self._lock:
            all_clients = set(self._connections.keys())
            if exclude:
                all_clients -= exclude
            subscriber_list = list(all_clients)

        await self._send_to_many(subscriber_list, message)

    async def _send_to_many(self, subscribers: list[WebSocket], message: dict) -> None:
        stale: list[WebSocket] = []
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)


class NotificationListener:
    """Listens on a dedicated asyncpg connection for NOTIFY events."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager
        self._conn: Optional[asyncpg.Connection] = None
        self._running = False
        self._reconnect_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        await self._connect_and_listen()

    async def stop(self) -> None:
        self._running = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        await self._close_conn()

    async def _connect_and_listen(self) -> None:
        try:
            dsn = _get_raw_dsn()
            self._conn = await asyncpg.connect(dsn)
            await self._conn.add_listener(CHANNEL, self._on_notify)  # type: ignore[union-attr]
            logger.info(f"LISTEN {CHANNEL} — notification listener started")
        except Exception as e:
            logger.error(f"Failed to start notification listener: {e}")
            self._schedule_reconnect()

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        asyncio.ensure_future(self._handle_notify(payload))

    async def _handle_notify(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            entity_type = data["entity_type"]
            entity_id = data["entity_id"]

            message = {"type": "event", "payload": data}

            # Fan out to detail subscribers
            already_notified = await self._manager.broadcast(entity_type, entity_id, message)
            # Fan out to ALL connected clients for list invalidation (excluding already-notified)
            await self._manager.broadcast_list(entity_type, message, exclude=already_notified)
        except Exception:
            logger.exception("Error handling NOTIFY payload")

    async def _close_conn(self) -> None:
        if self._conn and not self._conn.is_closed():
            try:
                await self._conn.remove_listener(CHANNEL, self._on_notify)
                await self._conn.close()
            except Exception:
                pass
        self._conn = None

    def _schedule_reconnect(self) -> None:
        if not self._running:
            return
        self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        delay = 3
        max_delay = 60
        while self._running:
            logger.info(f"Reconnecting notification listener in {delay}s…")
            await asyncio.sleep(delay)
            try:
                await self._close_conn()
                await self._connect_and_listen()
                if self._conn and not self._conn.is_closed():
                    logger.info("Notification listener reconnected")
                    return
            except Exception as e:
                logger.warning(f"Reconnect failed: {e}")
            delay = min(delay * 2, max_delay)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

connection_manager = ConnectionManager()
notification_listener = NotificationListener(connection_manager)


# ---------------------------------------------------------------------------
# Event emission (call within a transaction, before commit)
# ---------------------------------------------------------------------------


async def emit_event(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: int,
    event_type: RealtimeEventType,
    performed_by: str,
    item_id: Optional[str] = None,
) -> None:
    """Emit a real-time event via PostgreSQL NOTIFY.

    Must be called within an active transaction (before ``await db.commit()``).
    PostgreSQL holds the NOTIFY until the transaction commits and drops it on
    rollback — giving us free transactional guarantees.
    """
    payload: Dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "event_type": event_type.value,
        "performed_by": performed_by,
    }
    if item_id is not None:
        payload["item_id"] = item_id

    payload_json = json.dumps(payload)

    if len(payload_json) > 7500:
        logger.warning(
            "NOTIFY payload exceeds 7500 bytes (%d), approaching 8000-byte PG limit",
            len(payload_json),
        )

    await db.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": CHANNEL, "payload": payload_json})
