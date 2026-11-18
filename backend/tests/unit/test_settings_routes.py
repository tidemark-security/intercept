from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import settings as settings_routes
from app.models.enums import SettingType
from app.models.models import AppSettingCreate, AppSettingUpdate
from app.services.settings_service import (
    SettingConflictError,
    SettingNotFoundError,
    SettingValidationError,
)


BULK_SYNC_TIME_KEY = "enrichment.ldap.bulk_sync_time_utc"


class _FakeSettingsService:
    def __init__(self, *, create_result: Any, update_result: Any) -> None:
        self.create_setting = AsyncMock(return_value=create_result)
        self.update_setting = AsyncMock(return_value=update_result)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/settings",
            "headers": [
                (b"user-agent", b"settings-route-test"),
                (b"x-correlation-id", b"correlation-123"),
            ],
            "client": ("203.0.113.10", 4321),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def _setting_create(value: str = "03:45") -> AppSettingCreate:
    return AppSettingCreate(
        key=BULK_SYNC_TIME_KEY,
        value=value,
        value_type=SettingType.STRING,
        is_secret=False,
        description="LDAP bulk sync time",
        category="enrichment",
    )


def _install_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    create_result: Any = None,
    update_result: Any = None,
) -> tuple[_FakeSettingsService, Mock, AsyncMock]:
    service = _FakeSettingsService(
        create_result=create_result,
        update_result=update_result,
    )
    service_factory = Mock(return_value=service)
    enqueue_refresh = AsyncMock()
    monkeypatch.setattr(settings_routes, "SettingsService", service_factory)
    monkeypatch.setattr(
        settings_routes,
        "_enqueue_bulk_sync_schedule_refresh_if_needed",
        enqueue_refresh,
    )
    return service, service_factory, enqueue_refresh


@pytest.mark.asyncio
async def test_create_setting_preserves_write_context_and_schedule_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = object()
    service, service_factory, enqueue_refresh = _install_service(
        monkeypatch,
        create_result=expected,
    )
    db = cast(AsyncSession, object())
    setting = _setting_create()

    result = await settings_routes.create_setting(
        request=_request(),
        setting=setting,
        current_user=SimpleNamespace(username="admin-user"),
        db=db,
    )

    assert result is expected
    service_factory.assert_called_once_with(db)
    service.create_setting.assert_awaited_once()
    call = service.create_setting.await_args
    assert call.args == (setting,)
    assert call.kwargs["performed_by"] == "admin-user"
    assert call.kwargs["audit_context"].to_payload() == {
        "correlation_id": "correlation-123",
        "ip_address": "203.0.113.10",
        "user_agent": "settings-route-test",
    }
    enqueue_refresh.assert_awaited_once_with(BULK_SYNC_TIME_KEY)


@pytest.mark.asyncio
async def test_update_setting_preserves_write_context_and_schedule_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = object()
    service, service_factory, enqueue_refresh = _install_service(
        monkeypatch,
        update_result=expected,
    )
    db = cast(AsyncSession, object())
    setting_update = AppSettingUpdate(value="04:30", description="Updated")

    result = await settings_routes.update_setting(
        request=_request(),
        key=BULK_SYNC_TIME_KEY,
        setting_update=setting_update,
        current_user=SimpleNamespace(username="admin-user"),
        db=db,
    )

    assert result is expected
    service_factory.assert_called_once_with(db)
    service.update_setting.assert_awaited_once()
    call = service.update_setting.await_args
    assert call.args == (BULK_SYNC_TIME_KEY, setting_update)
    assert call.kwargs["performed_by"] == "admin-user"
    assert call.kwargs["audit_context"].to_payload() == {
        "correlation_id": "correlation-123",
        "ip_address": "203.0.113.10",
        "user_agent": "settings-route-test",
    }
    enqueue_refresh.assert_awaited_once_with(BULK_SYNC_TIME_KEY)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "error", "expected_status"),
    [
        (
            "create",
            SettingConflictError("Setting with key already exists"),
            status.HTTP_409_CONFLICT,
        ),
        (
            "create",
            SettingValidationError("Invalid setting value"),
            status.HTTP_400_BAD_REQUEST,
        ),
        (
            "update",
            SettingNotFoundError("Setting with key not found"),
            status.HTTP_404_NOT_FOUND,
        ),
        (
            "update",
            SettingValidationError("Invalid setting value"),
            status.HTTP_400_BAD_REQUEST,
        ),
    ],
)
async def test_setting_writes_use_typed_error_mapping(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    error: Exception,
    expected_status: int,
) -> None:
    service, _, enqueue_refresh = _install_service(monkeypatch)
    getattr(service, f"{operation}_setting").side_effect = error

    with pytest.raises(HTTPException) as exc_info:
        if operation == "create":
            await settings_routes.create_setting(
                request=_request(),
                setting=_setting_create(),
                current_user=SimpleNamespace(username="admin-user"),
                db=cast(AsyncSession, object()),
            )
        else:
            await settings_routes.update_setting(
                request=_request(),
                key=BULK_SYNC_TIME_KEY,
                setting_update=AppSettingUpdate(value="03:45"),
                current_user=SimpleNamespace(username="admin-user"),
                db=cast(AsyncSession, object()),
            )

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == str(error)
    enqueue_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_setting_write_does_not_misclassify_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, enqueue_refresh = _install_service(monkeypatch)
    service.update_setting.side_effect = ValueError("internal serialization defect")

    with pytest.raises(ValueError, match="internal serialization defect"):
        await settings_routes.update_setting(
            request=_request(),
            key=BULK_SYNC_TIME_KEY,
            setting_update=AppSettingUpdate(value="03:45"),
            current_user=SimpleNamespace(username="admin-user"),
            db=cast(AsyncSession, object()),
        )

    enqueue_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_setting_validation_does_not_mask_unexpected_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, enqueue_refresh = _install_service(monkeypatch)

    def raise_validator_defect(*_args: object) -> None:
        raise ValueError("validator defect")

    monkeypatch.setattr(
        settings_routes,
        "_validate_bulk_sync_setting_value",
        raise_validator_defect,
    )

    with pytest.raises(ValueError, match="validator defect"):
        await settings_routes.update_setting(
            request=_request(),
            key=BULK_SYNC_TIME_KEY,
            setting_update=AppSettingUpdate(value="03:45"),
            current_user=SimpleNamespace(username="admin-user"),
            db=cast(AsyncSession, object()),
        )

    service.update_setting.assert_not_awaited()
    enqueue_refresh.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_setting_writes_validate_bulk_sync_time_before_persisting(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    service, _, enqueue_refresh = _install_service(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        if operation == "create":
            await settings_routes.create_setting(
                request=_request(),
                setting=_setting_create("25:00"),
                current_user=SimpleNamespace(username="admin-user"),
                db=cast(AsyncSession, object()),
            )
        else:
            await settings_routes.update_setting(
                request=_request(),
                key=BULK_SYNC_TIME_KEY,
                setting_update=AppSettingUpdate(value="25:00"),
                current_user=SimpleNamespace(username="admin-user"),
                db=cast(AsyncSession, object()),
            )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Bulk sync time must use HH:MM 24-hour UTC format"
    service.create_setting.assert_not_awaited()
    service.update_setting.assert_not_awaited()
    enqueue_refresh.assert_not_awaited()
