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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import async_session_factory
from app.core.settings_registry import get_local
from app.services.auth_service import auth_service, SessionNotFoundError
from app.services.realtime_service import connection_manager, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_ENTITY_TYPES = {"alert", "case", "task"}


async def _authenticate(ws: WebSocket) -> str | None:
    """Validate the session cookie and return the token, or None."""
    cookie_name = get_local("auth.session.cookie_name")
    session_token = ws.cookies.get(cookie_name)
    if not session_token:
        return None

    try:
        async with async_session_factory() as db:
            await auth_service.validate_session(db, session_token=session_token)
            await db.commit()
        return session_token
    except SessionNotFoundError:
        return None
    except Exception:
        logger.exception("WebSocket auth error")
        return None


async def _revalidate_session(session_token: str) -> bool:
    """Re-validate the session token. Returns True if still valid."""
    try:
        async with async_session_factory() as db:
            await auth_service.validate_session(db, session_token=session_token)
            await db.commit()
        return True
    except SessionNotFoundError:
        return False
    except Exception:
        logger.exception("WebSocket session re-validation error")
        return False


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # --- Authenticate on handshake ---
    session_token = await _authenticate(ws)
    if not session_token:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    await connection_manager.connect(ws, session_token)
    logger.info("WebSocket connected (active: %d)", connection_manager.active_connections)

    # Background heartbeat + session re-validation
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                # Re-validate session
                token = connection_manager.get_session_token(ws)
                if not token or not await _revalidate_session(token):
                    await ws.send_json({"type": "error", "payload": {"message": "Session expired"}})
                    await ws.close(code=4001, reason="Session expired")
                    return
                await ws.send_json({"type": "ping"})
        except Exception:
            pass  # Connection closed; heartbeat exits

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "payload": {"message": "Invalid JSON"}})
                continue

            msg_type = msg.get("type")

            if msg_type == "subscribe":
                entity_type = msg.get("entity_type")
                entity_id = msg.get("entity_id")
                if entity_type not in VALID_ENTITY_TYPES or not isinstance(entity_id, int):
                    await ws.send_json({"type": "error", "payload": {"message": "Invalid subscribe params"}})
                    continue
                await connection_manager.subscribe(ws, entity_type, entity_id)
                await ws.send_json({
                    "type": "subscribed",
                    "payload": {"entity_type": entity_type, "entity_id": entity_id},
                })

            elif msg_type == "unsubscribe":
                entity_type = msg.get("entity_type")
                entity_id = msg.get("entity_id")
                if entity_type not in VALID_ENTITY_TYPES or not isinstance(entity_id, int):
                    await ws.send_json({"type": "error", "payload": {"message": "Invalid unsubscribe params"}})
                    continue
                await connection_manager.unsubscribe(ws, entity_type, entity_id)
                await ws.send_json({
                    "type": "unsubscribed",
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
        await connection_manager.disconnect(ws)
        logger.info("WebSocket disconnected (active: %d)", connection_manager.active_connections)
