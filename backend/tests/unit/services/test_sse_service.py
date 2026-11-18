from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.sse_service import _format_event, stream_events


async def _source_events(
    events: list[dict[str, Any]],
) -> AsyncGenerator[dict[str, Any], None]:
    for event in events:
        yield event


def _event_names(formatted_events: list[str]) -> list[str]:
    return [event.splitlines()[0].removeprefix("event: ") for event in formatted_events]


def test_format_event_prefixes_each_plain_text_data_line() -> None:
    assert _format_event("message", "first\r\nsecond\n") == (
        "event: message\n"
        "data: first\n"
        "data: second\n"
        "data: \n\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_event", ["complete", "error"])
async def test_stream_events_preserves_one_source_owned_terminal_event(
    terminal_event: str,
) -> None:
    source = _source_events(
        [
            {"event": "message", "data": {"content": "partial"}},
            {"event": terminal_event, "data": {"status": terminal_event}},
        ]
    )

    formatted_events = [
        event async for event in stream_events(uuid4(), source)
    ]

    assert _event_names(formatted_events) == [
        "connected",
        "message",
        terminal_event,
    ]


@pytest.mark.asyncio
async def test_stream_events_releases_resources_when_client_disconnects_after_connect() -> None:
    source_started = False

    async def source() -> AsyncGenerator[dict[str, Any], None]:
        nonlocal source_started
        source_started = True
        yield {"event": "message", "data": {"content": "late"}}

    on_close = AsyncMock()
    stream = stream_events(uuid4(), source(), on_close=on_close)

    first_event = await anext(stream)
    await stream.aclose()

    assert "event: connected" in first_event
    assert source_started is False
    on_close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_stream_cleanup_failure_does_not_escape_generator_close() -> None:
    source = _source_events([])
    on_close = AsyncMock(side_effect=RuntimeError("close failed"))
    stream = stream_events(uuid4(), source, on_close=on_close)

    await anext(stream)
    await stream.aclose()

    on_close.assert_awaited_once_with()
