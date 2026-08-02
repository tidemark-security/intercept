"""
WebSocket endpoint for real-time timeline notifications.

Authenticates via session cookie on handshake, then allows clients to
subscribe/unsubscribe to entity updates.  Server heartbeats every 30s
and re-validates the session on each cycle.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import async_session_factory
from app.core.settings_registry import get_local
from app.services.auth_service import (
    LoginResult,
    PasswordChangeRequiredError,
    SessionNotFoundError,
    auth_service,
)
from app.services.realtime_service import connection_manager, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_ENTITY_TYPES = {"alert", "case", "task"}


def _parse_message(raw: str) -> dict[str, Any] | None:
    """Decode a client message, accepting JSON objects only."""
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return message if isinstance(message, dict) else None


def _parse_subscription_target(
    message: dict[str, Any],
) -> tuple[str, int] | None:
    """Return a valid subscription target, excluding boolean pseudo-integers."""
    entity_type = message.get("entity_type")
    entity_id = message.get("entity_id")
    if (
        entity_type not in VALID_ENTITY_TYPES
        or not isinstance(entity_id, int)
        or isinstance(entity_id, bool)
    ):
        return None
    return entity_type, entity_id


def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        return False
    return origin in set(get_local("cors_origins") or [])


async def _authenticate(ws: WebSocket) -> LoginResult | None:
    """Validate the session cookie and return login details, or None."""
    cookie_name = get_local("auth.session.cookie_name")
    session_token = ws.cookies.get(cookie_name)
    if not session_token:
        return None

    try:
        async with async_session_factory() as db:
            login_result = await auth_service.validate_session(db, session_token=session_token)
            await db.commit()
        return login_result
    except (SessionNotFoundError, PasswordChangeRequiredError):
        return None


async def _revalidate_session(session_token: str) -> bool:
    """Re-validate the session token. Returns True if still valid."""
    try:
        async with async_session_factory() as db:
            await auth_service.validate_session(db, session_token=session_token)
            await db.commit()
        return True
    except (SessionNotFoundError, PasswordChangeRequiredError):
        return False


async def _close_for_session_validation_failure(ws: WebSocket) -> None:
    """Best-effort close when the session backend cannot be reached."""
    try:
        await ws.send_json(
            {
                "type": "error",
                "payload": {"message": "Session validation unavailable"},
            }
        )
        await ws.close(code=1011, reason="Session validation unavailable")
    except (RuntimeError, WebSocketDisconnect):
        # The peer may have disconnected while validation was in progress.
        pass


async def _heartbeat(ws: WebSocket) -> None:
    """Ping a connection and close it when its session expires or cannot be checked."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            token = connection_manager.get_session_token(ws)
            session_valid = bool(token and await _revalidate_session(token))
        except Exception:
            logger.exception("WebSocket session validation error")
            await _close_for_session_validation_failure(ws)
            return

        try:
            if not session_valid:
                await ws.send_json(
                    {"type": "error", "payload": {"message": "Session expired"}}
                )
                await ws.close(code=4001, reason="Session expired")
                return
            await ws.send_json({"type": "ping"})
        except (RuntimeError, WebSocketDisconnect):
            # Sending to an already-closed connection is an expected race.
            return


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if not _origin_allowed(ws):
        await ws.close(code=4003, reason="Origin not allowed")
        return

    # --- Authenticate on handshake ---
    try:
        login_result = await _authenticate(ws)
    except Exception:
        logger.exception("WebSocket authentication service error")
        await ws.close(code=1011, reason="Authentication service unavailable")
        return
    if not login_result:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    await connection_manager.connect(ws, login_result.session_token, login_result.user.username)
    logger.info("WebSocket connected (active: %d)", connection_manager.active_connections)

    heartbeat_task = asyncio.create_task(_heartbeat(ws))

    try:
        while True:
            raw = await ws.receive_text()
            msg = _parse_message(raw)
            if msg is None:
                await ws.send_json({"type": "error", "payload": {"message": "Invalid JSON"}})
                continue

            msg_type = msg.get("type")

            if msg_type in {"subscribe", "unsubscribe"}:
                target = _parse_subscription_target(msg)
                if target is None:
                    await ws.send_json({
                        "type": "error",
                        "payload": {"message": f"Invalid {msg_type} params"},
                    })
                    continue
                entity_type, entity_id = target
                subscription_action = getattr(connection_manager, msg_type)
                await subscription_action(ws, entity_type, entity_id)
                await ws.send_json({
                    "type": f"{msg_type}d",
                    "payload": {"entity_type": entity_type, "entity_id": entity_id},
                })

            elif msg_type == "pong":
                pass  # Client responded to heartbeat ping

            else:
                await ws.send_json({"type": "error", "payload": {"message": f"Unknown message type: {msg_type}"}})

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            # Cancellation is expected after stopping the heartbeat on disconnect.
            pass
        await connection_manager.disconnect(ws)
        logger.info("WebSocket disconnected (active: %d)", connection_manager.active_connections)
