from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

from app import main
from app.services.maxmind_service import maxmind_service
from app.services.realtime_service import notification_listener


@pytest.mark.asyncio
async def test_lifespan_attempts_every_cleanup_after_startup_failure(monkeypatch) -> None:
    monkeypatch.setattr(main, "initialize_encryption_service", lambda _key: None)
    monkeypatch.setattr(main, "test_db_connection", AsyncMock(return_value=False))

    stop_listener = AsyncMock(side_effect=RuntimeError("listener stop failed"))
    stop_queue = AsyncMock(side_effect=RuntimeError("queue stop failed"))
    close_readers = AsyncMock()
    monkeypatch.setattr(notification_listener, "stop", stop_listener)
    monkeypatch.setattr(main, "shutdown_task_queue_service", stop_queue)
    monkeypatch.setattr(maxmind_service, "close_readers", close_readers)

    with pytest.raises(RuntimeError, match="Database connection failed"):
        async with main.app_lifespan(FastAPI()):
            pytest.fail("startup failure must prevent the application from yielding")

    stop_listener.assert_awaited_once_with()
    stop_queue.assert_awaited_once_with()
    close_readers.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_lifespan_propagates_handler_registration_defects(monkeypatch) -> None:
    monkeypatch.setattr(main, "initialize_encryption_service", Mock())
    monkeypatch.setattr(main, "test_db_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "register_providers", Mock())
    monkeypatch.setattr(main, "initialize_task_queue_service", AsyncMock())
    register_handlers = AsyncMock(side_effect=RuntimeError("broken handler"))
    monkeypatch.setattr(main, "register_task_handlers", register_handlers)
    start_listener = AsyncMock()
    monkeypatch.setattr(notification_listener, "start", start_listener)
    monkeypatch.setattr(notification_listener, "stop", AsyncMock())
    monkeypatch.setattr(main, "shutdown_task_queue_service", AsyncMock())
    monkeypatch.setattr(maxmind_service, "close_readers", AsyncMock())

    with pytest.raises(RuntimeError, match="broken handler"):
        async with main.app_lifespan(FastAPI()):
            pytest.fail("handler defects must prevent the application from yielding")

    register_handlers.assert_awaited_once_with()
    start_listener.assert_not_awaited()


@pytest.mark.asyncio
async def test_lifespan_tolerates_transient_task_queue_connection_failure(monkeypatch) -> None:
    monkeypatch.setattr(main, "initialize_encryption_service", Mock())
    monkeypatch.setattr(main, "test_db_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "register_providers", Mock())
    monkeypatch.setattr(
        main,
        "initialize_task_queue_service",
        AsyncMock(side_effect=ConnectionError("queue database unavailable")),
    )
    register_handlers = AsyncMock()
    monkeypatch.setattr(main, "register_task_handlers", register_handlers)
    monkeypatch.setattr(notification_listener, "start", AsyncMock(return_value=False))
    monkeypatch.setattr(notification_listener, "stop", AsyncMock())
    monkeypatch.setattr(main, "shutdown_task_queue_service", AsyncMock())
    monkeypatch.setattr(maxmind_service, "close_readers", AsyncMock())

    async with main.app_lifespan(FastAPI()):
        pass

    register_handlers.assert_not_awaited()
