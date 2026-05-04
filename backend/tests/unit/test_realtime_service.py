from __future__ import annotations

import json
from typing import Any, cast

import pytest
from fastapi import WebSocket

from app.services.realtime_service import ConnectionManager, NotificationListener


class MockWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


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