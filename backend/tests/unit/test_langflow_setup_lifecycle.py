from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.routes import langflow as langflow_routes
from app.models.models import ApiKeyRead
from app.services.langflow_service import (
    LangFlowCheckResult,
    LangFlowConfigurationError,
    LangFlowError,
    LangFlowProvisioningResult,
    LangFlowSetupConfigurationError,
    LangFlowSummaryResult,
)
from app.services.settings_service import SettingNotFoundError


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/langflow/admin/setup-intercept-mcp",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        }
    )


def _service() -> SimpleNamespace:
    return SimpleNamespace(
        upsert_credential_variable=AsyncMock(
            return_value=LangFlowProvisioningResult(action="created", payload={})
        ),
        upsert_mcp_server=AsyncMock(
            return_value=LangFlowProvisioningResult(action="created", payload={})
        ),
        ensure_project=AsyncMock(
            return_value=LangFlowProvisioningResult(
                action="created",
                payload={"id": "project-1"},
            )
        ),
        list_flows=AsyncMock(
            return_value=LangFlowSummaryResult(
                check_result=LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=True,
                    message="ok",
                ),
                flows=[],
            )
        ),
        close=AsyncMock(),
    )


def _setup_arguments() -> dict[str, Any]:
    return {
        "payload": langflow_routes.LangFlowSetupRequest(
            backend_api_base_url="http://localhost:8000/api/v1"
        ),
        "request": _request(),
        "db": cast(AsyncSession, SimpleNamespace(rollback=AsyncMock())),
        "current_user": SimpleNamespace(id=uuid4(), username="admin"),
    }


@pytest.mark.asyncio
async def test_setup_closes_langflow_service_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    nhi_user = SimpleNamespace(id=uuid4(), username="tidemark_ai")
    now = datetime.now(timezone.utc)
    api_key = ApiKeyRead(
        id=uuid4(),
        user_id=nhi_user.id,
        name="Intercept Langflow MCP",
        prefix="tmi_12345678",
        expires_at=now,
        last_used_at=None,
        revoked_at=None,
        created_at=now,
    )
    monkeypatch.setattr(
        langflow_routes,
        "get_langflow_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(
        langflow_routes,
        "_ensure_langflow_nhi_account",
        AsyncMock(return_value=(nhi_user, "created")),
    )
    monkeypatch.setattr(
        langflow_routes.api_key_service,
        "create_api_key",
        AsyncMock(return_value=(api_key, "raw-key")),
    )
    monkeypatch.setattr(langflow_routes, "LANGFLOW_BUNDLED_FLOW_ASSETS", ())

    arguments = _setup_arguments()
    response = await langflow_routes.setup_intercept_mcp_server(**arguments)

    assert response.success is True
    service.close.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        LangFlowConfigurationError("configuration failed"),
        LangFlowError("provisioning failed"),
        LangFlowSetupConfigurationError("invalid setup value"),
    ],
)
async def test_setup_closes_langflow_service_after_handled_failure(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    service = _service()
    monkeypatch.setattr(
        langflow_routes,
        "get_langflow_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(
        langflow_routes,
        "_ensure_langflow_nhi_account",
        AsyncMock(side_effect=error),
    )

    arguments = _setup_arguments()
    response = await langflow_routes.setup_intercept_mcp_server(**arguments)

    assert response.success is False
    assert response.message == str(error)
    service.close.assert_awaited_once_with()
    arguments["db"].rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_setup_closes_langflow_service_after_unhandled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    monkeypatch.setattr(
        langflow_routes,
        "get_langflow_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(
        langflow_routes,
        "_ensure_langflow_nhi_account",
        AsyncMock(side_effect=RuntimeError("unexpected failure")),
    )

    arguments = _setup_arguments()
    with pytest.raises(RuntimeError, match="unexpected failure"):
        await langflow_routes.setup_intercept_mcp_server(**arguments)

    service.close.assert_awaited_once_with()
    arguments["db"].rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_setup_rolls_back_and_propagates_internal_value_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    monkeypatch.setattr(
        langflow_routes,
        "get_langflow_service",
        AsyncMock(return_value=service),
    )
    monkeypatch.setattr(
        langflow_routes,
        "_ensure_langflow_nhi_account",
        AsyncMock(side_effect=ValueError("internal invariant failed")),
    )

    arguments = _setup_arguments()
    with pytest.raises(ValueError, match="internal invariant failed"):
        await langflow_routes.setup_intercept_mcp_server(**arguments)

    arguments["db"].rollback.assert_awaited_once_with()
    service.close.assert_awaited_once_with()


@pytest.mark.parametrize("base_url", ["", "relative/path", "://invalid"])
def test_setup_url_validation_uses_typed_public_error(base_url: str) -> None:
    with pytest.raises(LangFlowSetupConfigurationError):
        langflow_routes._derive_intercept_mcp_streamable_url(base_url)


@pytest.mark.asyncio
async def test_setup_asset_json_error_is_curated_and_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decoder_error = json.JSONDecodeError(
        "upstream parser detail",
        "secret malformed asset contents",
        0,
    )
    monkeypatch.setattr(
        langflow_routes,
        "_load_langflow_asset",
        AsyncMock(side_effect=decoder_error),
    )

    with pytest.raises(
        LangFlowSetupConfigurationError,
        match="Bundled Langflow asset 'broken.json' does not contain valid JSON",
    ) as exc_info:
        await langflow_routes._load_setup_flow_asset("broken.json")

    assert "secret malformed asset contents" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_bundled_asset_loading_runs_in_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset_path = Path("flow.json")
    to_thread = AsyncMock(return_value={"endpoint_name": "test-flow"})
    monkeypatch.setattr(langflow_routes.asyncio, "to_thread", to_thread)

    payload = await langflow_routes._load_langflow_asset(asset_path)

    assert payload == {"endpoint_name": "test-flow"}
    to_thread.assert_awaited_once_with(langflow_routes._read_langflow_asset, asset_path)


@pytest.mark.asyncio
async def test_setup_setting_upsert_creates_only_after_typed_not_found() -> None:
    settings = SimpleNamespace(
        update_setting_in_transaction=AsyncMock(
            side_effect=SettingNotFoundError("setting absent")
        ),
        create_setting_in_transaction=AsyncMock(),
    )

    await langflow_routes._upsert_setting_value(
        settings,
        key="langflow.default_flow_id",
        value="flow-1",
        performed_by="admin",
        audit_context=None,
    )

    settings.create_setting_in_transaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_setting_upsert_does_not_treat_internal_value_error_as_missing() -> None:
    settings = SimpleNamespace(
        update_setting_in_transaction=AsyncMock(
            side_effect=ValueError("internal serialization defect")
        ),
        create_setting_in_transaction=AsyncMock(),
    )

    with pytest.raises(ValueError, match="internal serialization defect"):
        await langflow_routes._upsert_setting_value(
            settings,
            key="langflow.default_flow_id",
            value="flow-1",
            performed_by="admin",
            audit_context=None,
        )

    settings.create_setting_in_transaction.assert_not_awaited()
