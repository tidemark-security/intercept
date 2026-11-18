from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import asyncpg
import pytest
from fastapi import WebSocket

from app.services.realtime_service import (
    ConnectionManager,
    NotificationListener,
    _serialize_notify_payload,
)


class MockWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.closed_with: tuple[int, str] | None = None

    async def send_json(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    async def close(self, *, code: int, reason: str) -> None:
        self.closed_with = (code, reason)


class MockPgConnection:
    def __init__(self) -> None:
        self.add_listener = AsyncMock()
        self.remove_listener = AsyncMock()
        self.close = AsyncMock(side_effect=self._mark_closed)
        self.is_closed = Mock(return_value=False)

    def _mark_closed(self) -> None:
        self.is_closed.return_value = True


def test_notify_payload_serializer_warns_for_oversized_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = {"content": "x" * 7500}

    with caplog.at_level(logging.WARNING):
        serialized = _serialize_notify_payload(payload)

    assert json.loads(serialized) == payload
    assert "NOTIFY payload exceeds 7500 bytes" in caplog.text


@pytest.mark.asyncio
async def test_broadcast_list_sends_to_all_clients_except_excluded() -> None:
    manager = ConnectionManager(node_id="node-a")
    included = cast(WebSocket, MockWebSocket())
    excluded = cast(WebSocket, MockWebSocket())
    await manager.connect(included, "included-token", "Included")
    await manager.connect(excluded, "excluded-token", "Excluded")

    message = {"type": "event", "payload": {"entity_id": 12}}
    await manager.broadcast_list(message, exclude={excluded})

    assert cast(Any, included).messages == [message]
    assert cast(Any, excluded).messages == []


@pytest.mark.asyncio
async def test_invalidated_session_cannot_subscribe_after_connect() -> None:
    valid_tokens = {"session-token"}

    async def validate_session(session_token: str) -> bool:
        return session_token in valid_tokens

    async def publish(_: dict[str, Any]) -> None:
        return None

    manager = ConnectionManager(
        node_id="node-a",
        presence_publisher=publish,
        session_validator=validate_session,
    )
    ws = cast(WebSocket, MockWebSocket())
    await manager.connect(ws, "session-token", "Glenn")
    valid_tokens.clear()

    subscribed = await manager.subscribe(ws, "case", 12)

    assert subscribed is False
    assert manager.active_connections == 0
    assert cast(Any, ws).messages == []
    assert cast(Any, ws).closed_with == (4001, "Session expired")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_state", "expected_close"),
    [
        ("invalid", (4001, "Session expired")),
        ("backend-error", (1011, "Session validation unavailable")),
    ],
)
async def test_invalidated_session_cannot_receive_broadcast_after_subscribe(
    invalid_state: str,
    expected_close: tuple[int, str],
) -> None:
    validation_state = "valid"

    async def validate_session(_session_token: str) -> bool:
        if validation_state == "backend-error":
            raise RuntimeError("session backend unavailable")
        return validation_state == "valid"

    async def publish(_: dict[str, Any]) -> None:
        return None

    manager = ConnectionManager(
        node_id="node-a",
        presence_publisher=publish,
        session_validator=validate_session,
    )
    ws = cast(WebSocket, MockWebSocket())
    await manager.connect(ws, "session-token", "Glenn")
    assert await manager.subscribe(ws, "case", 12) is True
    cast(Any, ws).messages.clear()
    validation_state = invalid_state

    notified = await manager.broadcast(
        "case",
        12,
        {"type": "event", "payload": {"entity_id": 12}},
    )

    assert notified == set()
    assert manager.active_connections == 0
    assert cast(Any, ws).messages == []
    assert cast(Any, ws).closed_with == expected_close


@pytest.mark.asyncio
async def test_presence_is_broadcast_on_subscribe_and_unsubscribe() -> None:
    published: list[dict[str, Any]] = []

    async def publish(message: dict[str, Any]) -> None:
        published.append(message)

    manager = ConnectionManager(node_id="node-a", presence_publisher=publish)
    glenn_ws = cast(WebSocket, MockWebSocket())
    alex_ws = cast(WebSocket, MockWebSocket())

    await manager.connect(glenn_ws, "glenn-token", "Glenn")
    await manager.connect(alex_ws, "alex-token", "Alex")

    await manager.subscribe(glenn_ws, "case", 12)
    await manager.subscribe(alex_ws, "case", 12)

    assert cast(Any, glenn_ws).messages[-1] == {
        "type": "presence",
        "payload": {"entity_type": "case", "entity_id": 12, "viewers": ["Alex", "Glenn"]},
    }
    assert cast(Any, alex_ws).messages[-1] == {
        "type": "presence",
        "payload": {"entity_type": "case", "entity_id": 12, "viewers": ["Alex", "Glenn"]},
    }

    await manager.unsubscribe(alex_ws, "case", 12)

    assert cast(Any, glenn_ws).messages[-1] == {
        "type": "presence",
        "payload": {"entity_type": "case", "entity_id": 12, "viewers": ["Glenn"]},
    }
    assert cast(Any, alex_ws).messages[-1]["payload"]["viewers"] == ["Alex", "Glenn"]

    assert published[-1] == {
        "message_type": "presence_state",
        "origin_node_id": "node-a",
        "entity_type": "case",
        "entity_id": 12,
        "viewers": ["Glenn"],
    }


@pytest.mark.asyncio
async def test_remote_presence_snapshots_are_merged_for_local_subscribers() -> None:
    async def publish(_: dict[str, Any]) -> None:
        return None

    manager = ConnectionManager(node_id="node-a", presence_publisher=publish)
    glenn_ws = cast(WebSocket, MockWebSocket())

    await manager.connect(glenn_ws, "glenn-token", "Glenn")
    await manager.subscribe(glenn_ws, "case", 12)

    await manager.handle_presence_state(
        origin_node_id="node-b",
        entity_type="case",
        entity_id=12,
        viewers=["Alex", "John"],
    )

    assert cast(Any, glenn_ws).messages[-1] == {
        "type": "presence",
        "payload": {"entity_type": "case", "entity_id": 12, "viewers": ["Alex", "Glenn", "John"]},
    }


@pytest.mark.asyncio
async def test_presence_request_publishes_local_snapshot() -> None:
    published: list[dict[str, Any]] = []

    async def publish(message: dict[str, Any]) -> None:
        published.append(message)

    manager = ConnectionManager(node_id="node-a", presence_publisher=publish)
    glenn_ws = cast(WebSocket, MockWebSocket())

    await manager.connect(glenn_ws, "glenn-token", "Glenn")
    await manager.subscribe(glenn_ws, "case", 12)
    published.clear()

    await manager.handle_presence_request(
        origin_node_id="node-b",
        entity_type="case",
        entity_id=12,
    )

    assert published == [{
        "message_type": "presence_state",
        "origin_node_id": "node-a",
        "entity_type": "case",
        "entity_id": 12,
        "viewers": ["Glenn"],
    }]


@pytest.mark.asyncio
async def test_listener_routes_presence_state_notifications() -> None:
    async def publish(_: dict[str, Any]) -> None:
        return None

    manager = ConnectionManager(node_id="node-a", presence_publisher=publish)
    listener = NotificationListener(manager)
    glenn_ws = cast(WebSocket, MockWebSocket())

    await manager.connect(glenn_ws, "glenn-token", "Glenn")
    await manager.subscribe(glenn_ws, "case", 12)

    await listener._handle_notify(json.dumps({
        "message_type": "presence_state",
        "origin_node_id": "node-b",
        "entity_type": "case",
        "entity_id": 12,
        "viewers": ["Alex"],
    }))

    assert cast(Any, glenn_ws).messages[-1] == {
        "type": "presence",
        "payload": {"entity_type": "case", "entity_id": 12, "viewers": ["Alex", "Glenn"]},
    }


@pytest.mark.asyncio
async def test_listener_tracks_notify_tasks_until_they_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = NotificationListener(ConnectionManager(node_id="node-a"))
    listener._running = True
    started = asyncio.Event()
    release = asyncio.Event()

    async def handle_notify(_payload: str) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(listener, "_handle_notify", handle_notify)

    listener._on_notify(cast(Any, None), 1, "intercept_events", "{}")
    await started.wait()

    assert len(listener._notify_tasks) == 1
    task = next(iter(listener._notify_tasks))
    assert not task.done()

    release.set()
    await task
    await asyncio.sleep(0)

    assert listener._notify_tasks == set()
    await listener.stop()


@pytest.mark.asyncio
async def test_listener_stop_cancels_and_drains_notify_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = NotificationListener(ConnectionManager(node_id="node-a"))
    listener._running = True
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handle_notify(_payload: str) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(listener, "_handle_notify", handle_notify)

    listener._on_notify(cast(Any, None), 1, "intercept_events", "{}")
    await started.wait()
    task = next(iter(listener._notify_tasks))

    await listener.stop()

    assert task.cancelled()
    assert cancelled.is_set()
    assert listener._notify_tasks == set()


@pytest.mark.asyncio
async def test_listener_reuses_one_reconnect_task_until_eventual_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ConnectionManager(node_id="node-a")
    listener = NotificationListener(manager)
    connection = MockPgConnection()
    connect = AsyncMock(
        side_effect=[
            ConnectionError("initial failure"),
            ConnectionError("retry failure"),
            connection,
        ]
    )
    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def immediate_sleep(delay: float) -> None:
        delays.append(delay)
        await real_sleep(0)

    async def idle_presence_loop() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr("app.services.realtime_service.asyncpg.connect", connect)
    monkeypatch.setattr("app.services.realtime_service.asyncio.sleep", immediate_sleep)
    monkeypatch.setattr(listener, "_presence_snapshot_loop", idle_presence_loop)

    initially_connected = await listener.start()
    reconnect_task = listener._reconnect_task
    assert reconnect_task is not None
    assert initially_connected is False

    listener._schedule_reconnect()
    listener._schedule_reconnect()
    assert listener._reconnect_task is reconnect_task

    await asyncio.wait_for(reconnect_task, timeout=1)

    assert listener._reconnect_task is reconnect_task
    assert reconnect_task.done()
    assert connect.await_count == 3
    assert delays == [3, 6]
    assert listener._conn is connection

    await listener.stop()


@pytest.mark.asyncio
async def test_connect_attempt_failure_does_not_schedule_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = NotificationListener(ConnectionManager(node_id="node-a"))
    listener._running = True
    connect = AsyncMock(side_effect=ConnectionError("database unavailable"))
    monkeypatch.setattr("app.services.realtime_service.asyncpg.connect", connect)

    connected = await listener._connect_and_listen()

    assert connected is False
    assert listener._reconnect_task is None
    await listener.stop()


@pytest.mark.asyncio
async def test_listener_setup_failure_closes_and_forgets_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = NotificationListener(ConnectionManager(node_id="node-a"))
    connection = MockPgConnection()
    connection.add_listener.side_effect = asyncpg.InterfaceError("listener setup failed")
    connection.remove_listener.side_effect = RuntimeError("listener was not registered")
    monkeypatch.setattr(
        "app.services.realtime_service.asyncpg.connect",
        AsyncMock(return_value=connection),
    )

    connected = await listener._connect_and_listen()

    assert connected is False
    connection.close.assert_awaited_once_with()
    assert listener._conn is None


@pytest.mark.asyncio
async def test_listener_setup_does_not_hide_programming_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = NotificationListener(ConnectionManager(node_id="node-a"))
    connection = MockPgConnection()
    connection.add_listener.side_effect = RuntimeError("listener integration bug")
    monkeypatch.setattr(
        "app.services.realtime_service.asyncpg.connect",
        AsyncMock(return_value=connection),
    )

    with pytest.raises(RuntimeError, match="listener integration bug"):
        await listener._connect_and_listen()

    connection.close.assert_awaited_once_with()
    assert listener._conn is None


@pytest.mark.asyncio
async def test_stop_cancels_the_single_pending_reconnect_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = NotificationListener(ConnectionManager(node_id="node-a"))
    connect = AsyncMock(side_effect=ConnectionError("database unavailable"))
    monkeypatch.setattr("app.services.realtime_service.asyncpg.connect", connect)

    await listener.start()
    reconnect_task = listener._reconnect_task
    assert reconnect_task is not None
    listener._schedule_reconnect()
    assert listener._reconnect_task is reconnect_task

    await asyncio.sleep(0)
    await listener.stop()

    assert reconnect_task.cancelled()
    assert listener._reconnect_task is reconnect_task
    assert connect.await_count == 1
