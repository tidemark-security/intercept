from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from app.api.routes import websocket as websocket_route


class FakeWebSocket:
    def __init__(self, raw_message: str) -> None:
        self._messages = [raw_message]
        self.sent_messages: list[dict[str, object]] = []
        self.closed_with: tuple[int, str] | None = None
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, *, code: int, reason: str) -> None:
        self.closed_with = (code, reason)

    async def receive_text(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect

    async def send_json(self, message: dict[str, object]) -> None:
        self.sent_messages.append(message)


async def _run_message(
    monkeypatch: pytest.MonkeyPatch,
    raw_message: str,
    *,
    session_valid: bool = True,
) -> tuple[FakeWebSocket, SimpleNamespace]:
    ws = FakeWebSocket(raw_message)
    manager = SimpleNamespace(
        active_connections=1,
        connect=AsyncMock(),
        disconnect=AsyncMock(),
        subscribe=AsyncMock(return_value=True),
        unsubscribe=AsyncMock(return_value=True),
        validate_connection=AsyncMock(return_value=session_valid),
        get_session_token=Mock(return_value="session-token"),
    )

    async def authenticate(_ws: WebSocket) -> SimpleNamespace:
        return SimpleNamespace(
            session_token="session-token",
            user=SimpleNamespace(username="websocket-user"),
        )

    monkeypatch.setattr(websocket_route, "_origin_allowed", lambda _ws: True)
    monkeypatch.setattr(websocket_route, "_authenticate", authenticate)
    monkeypatch.setattr(websocket_route, "connection_manager", manager)

    await websocket_route.websocket_endpoint(cast(WebSocket, ws))
    await asyncio.sleep(0)
    return ws, manager


@pytest.mark.asyncio
async def test_websocket_accepts_object_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    ws, manager = await _run_message(
        monkeypatch,
        '{"type":"subscribe","entity_type":"case","entity_id":12}',
    )

    manager.subscribe.assert_awaited_once_with(cast(WebSocket, ws), "case", 12)
    assert ws.sent_messages == [
        {
            "type": "subscribed",
            "payload": {"entity_type": "case", "entity_id": 12},
        }
    ]


@pytest.mark.asyncio
async def test_websocket_unsubscribes_from_valid_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws, manager = await _run_message(
        monkeypatch,
        '{"type":"unsubscribe","entity_type":"task","entity_id":7}',
    )

    manager.unsubscribe.assert_awaited_once_with(cast(WebSocket, ws), "task", 7)
    assert ws.sent_messages == [
        {
            "type": "unsubscribed",
            "payload": {"entity_type": "task", "entity_id": 7},
        }
    ]


@pytest.mark.asyncio
async def test_invalidated_session_cannot_subscribe_after_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws, manager = await _run_message(
        monkeypatch,
        '{"type":"subscribe","entity_type":"case","entity_id":12}',
        session_valid=False,
    )

    assert ws.accepted is True
    manager.validate_connection.assert_awaited_once_with(cast(WebSocket, ws))
    manager.subscribe.assert_not_awaited()
    manager.disconnect.assert_awaited_once_with(cast(WebSocket, ws))
    assert ws.sent_messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["subscribe", "unsubscribe"])
async def test_websocket_rejects_boolean_entity_ids(
    monkeypatch: pytest.MonkeyPatch,
    message_type: str,
) -> None:
    ws, manager = await _run_message(
        monkeypatch,
        (
            f'{{"type":"{message_type}","entity_type":"alert",'
            '"entity_id":true}'
        ),
    )

    manager.subscribe.assert_not_awaited()
    manager.unsubscribe.assert_not_awaited()
    assert ws.sent_messages == [
        {
            "type": "error",
            "payload": {"message": f"Invalid {message_type} params"},
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_message",
    [
        pytest.param("[]", id="list"),
        pytest.param('"pong"', id="string-scalar"),
        pytest.param("42", id="number-scalar"),
        pytest.param("null", id="null"),
        pytest.param("{", id="invalid-json"),
    ],
)
async def test_websocket_rejects_non_object_or_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
    raw_message: str,
) -> None:
    ws, _manager = await _run_message(monkeypatch, raw_message)

    assert ws.sent_messages == [
        {"type": "error", "payload": {"message": "Invalid JSON"}}
    ]


@pytest.mark.asyncio
async def test_websocket_closes_safely_when_authentication_backend_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = FakeWebSocket("unused")

    async def fail_authentication(_ws: WebSocket) -> None:
        raise RuntimeError("database credentials and host details")

    monkeypatch.setattr(websocket_route, "_origin_allowed", lambda _ws: True)
    monkeypatch.setattr(websocket_route, "_authenticate", fail_authentication)

    await websocket_route.websocket_endpoint(cast(WebSocket, ws))

    assert ws.accepted is False
    assert ws.closed_with == (1011, "Authentication service unavailable")


@pytest.mark.asyncio
async def test_heartbeat_closes_safely_when_session_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = FakeWebSocket("unused")
    manager = SimpleNamespace(get_session_token=Mock(return_value="session-token"))

    async def no_wait(_delay: float) -> None:
        return None

    async def fail_revalidation(_token: str) -> bool:
        raise RuntimeError("database credentials and host details")

    monkeypatch.setattr(websocket_route.asyncio, "sleep", no_wait)
    monkeypatch.setattr(websocket_route, "connection_manager", manager)
    monkeypatch.setattr(websocket_route, "_revalidate_session", fail_revalidation)

    await websocket_route._heartbeat(cast(WebSocket, ws))

    assert ws.sent_messages == [
        {
            "type": "error",
            "payload": {"message": "Session validation unavailable"},
        }
    ]
    assert ws.closed_with == (1011, "Session validation unavailable")
