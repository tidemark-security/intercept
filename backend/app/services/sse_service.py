"""Server-Sent Events formatting for LangFlow response streams."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _format_event(event: str, data: Any) -> str:
    data_string = data if isinstance(data, str) else json.dumps(data)
    normalized_data = data_string.replace("\r\n", "\n").replace("\r", "\n")
    data_lines = "\n".join(
        f"data: {line}" for line in normalized_data.split("\n")
    )
    return f"event: {event}\n{data_lines}\n\n"


async def stream_events(
    session_id: UUID,
    source: AsyncIterator[dict[str, Any]],
    *,
    on_close: Callable[[], Awaitable[None]] | None = None,
    before_emit: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[str, None]:
    """Format source events and release source-scoped resources on disconnect."""
    logger.info("Started SSE stream", extra={"session_id": str(session_id)})

    try:
        if before_emit is not None and not await before_emit():
            return
        yield _format_event(
            "connected",
            {
                "session_id": str(session_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        async for event_data in source:
            event_type = event_data.get("event", "message")
            data = event_data.get("data", event_data)
            if before_emit is not None and not await before_emit():
                return
            yield _format_event(event_type, data)

        logger.info("Completed SSE stream", extra={"session_id": str(session_id)})
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled", extra={"session_id": str(session_id)})
        raise
    finally:
        source_close = getattr(source, "aclose", None)
        if source_close is not None:
            try:
                await source_close()
            except Exception:
                logger.exception(
                    "Failed to close SSE event source",
                    extra={"session_id": str(session_id)},
                )
        if on_close is not None:
            try:
                await on_close()
            except Exception:
                logger.exception(
                    "Failed to release SSE stream resources",
                    extra={"session_id": str(session_id)},
                )
        logger.info("Closed SSE stream", extra={"session_id": str(session_id)})
