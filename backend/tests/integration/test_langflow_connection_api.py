from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

import app.api.routes.langflow as langflow_routes
from app.core.settings_registry import get_local
from app.services.settings_service import SettingsService
from app.services.langflow_service import LangFlowCheckResult, LangFlowConfigurationError
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


async def _login_and_get_session_cookie(
    client: AsyncClient,
    session_maker: Any,
    user_factory,
) -> str:
    user = user_factory()

    async with session_maker() as session:
        session.add(user)
        await session.commit()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200

    session_cookie = login_response.cookies.get(get_local("auth.session.cookie_name"))
    assert session_cookie is not None
    return session_cookie


@pytest.mark.asyncio
async def test_langflow_connection_endpoint_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/langflow/test-connection")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_langflow_connection_endpoint_returns_both_successful_checks(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    configured_values = {
        "langflow.default_flow_id": "tmi_general_purpose",
        "langflow.case_detail_flow_id": "tmi_case_agent",
        "langflow.task_detail_flow_id": "tmi_task_agent",
        "langflow.alert_triage_flow_id": "tmi_alert_triage",
    }

    async def fake_get_typed_value(self, key: str, default=None):
        return configured_values.get(key, default)

    monkeypatch.setattr(SettingsService, "get_typed_value", fake_get_typed_value)

    class FakeLangFlowService:
        async def run_connectivity_check(self) -> LangFlowCheckResult:
            return LangFlowCheckResult(
                check_id="connectivity",
                label="Connectivity",
                success=True,
                message="Connected to the LangFlow health endpoint",
            )

        async def list_flows(self):
            class Result:
                check_result = LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=True,
                    message="Authenticated LangFlow API returned 2 flows",
                )
                flows = [
                    {"id": "uuid-default", "endpoint_name": "tmi_general_purpose", "name": "General"},
                    {"id": "uuid-alert", "endpoint_name": "tmi_alert_triage", "name": "Alert"},
                    {"id": "uuid-case", "endpoint_name": "tmi_case_agent", "name": "Case"},
                    {"id": "uuid-task", "endpoint_name": "tmi_task_agent", "name": "Task"},
                ]

            return Result()

        def validate_configured_flows(self, configured_flows: dict[str, str], flows):
            assert configured_flows == {
                "Default flow": "tmi_general_purpose",
                "Case detail flow": "tmi_case_agent",
                "Task detail flow": "tmi_task_agent",
                "Alert triage flow": "tmi_alert_triage",
            }
            assert len(flows) == 4
            return LangFlowCheckResult(
                check_id="configured_flows",
                label="Configured flow existence",
                success=True,
                message="Validated 4 configured LangFlow flow references",
            )

        async def close(self) -> None:
            return None

    async def fake_get_langflow_service(_db):
        return FakeLangFlowService()

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/test-connection",
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "LangFlow connectivity, flow listing, and configured flow checks passed"
    assert payload["checks"] == [
        {
            "id": "connectivity",
            "label": "Connectivity",
            "success": True,
            "message": "Connected to the LangFlow health endpoint",
        },
        {
            "id": "flow_listing",
            "label": "Authenticated flow listing",
            "success": True,
            "message": "Authenticated LangFlow API returned 2 flows",
        },
        {
            "id": "configured_flows",
            "label": "Configured flow existence",
            "success": True,
            "message": "Validated 4 configured LangFlow flow references",
        },
    ]


@pytest.mark.asyncio
async def test_langflow_connection_endpoint_reports_partial_failure(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    configured_values = {
        "langflow.default_flow_id": "tmi_general_purpose",
        "langflow.case_detail_flow_id": "tmi_case_agent",
        "langflow.task_detail_flow_id": "tmi_task_agent",
        "langflow.alert_triage_flow_id": "tmi_alert_triage",
    }

    async def fake_get_typed_value(self, key: str, default=None):
        return configured_values.get(key, default)

    monkeypatch.setattr(SettingsService, "get_typed_value", fake_get_typed_value)

    class FakeLangFlowService:
        async def run_connectivity_check(self) -> LangFlowCheckResult:
            return LangFlowCheckResult(
                check_id="connectivity",
                label="Connectivity",
                success=True,
                message="Connected to the LangFlow health endpoint",
            )

        async def list_flows(self):
            class Result:
                check_result = LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=True,
                    message="Authenticated LangFlow API returned 2 flows",
                )
                flows = [
                    {"id": "uuid-default", "endpoint_name": "tmi_general_purpose", "name": "General"},
                    {"id": "uuid-alert", "endpoint_name": "tmi_alert_triage", "name": "Alert"},
                ]

            return Result()

        def validate_configured_flows(self, configured_flows: dict[str, str], flows):
            assert configured_flows["Default flow"] == "tmi_general_purpose"
            return LangFlowCheckResult(
                check_id="configured_flows",
                label="Configured flow existence",
                success=False,
                message="Missing configured LangFlow flows: Case detail flow (tmi_case_agent), Task detail flow (tmi_task_agent)",
            )

        async def close(self) -> None:
            return None

    async def fake_get_langflow_service(_db):
        return FakeLangFlowService()

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/test-connection",
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "2 of 3 LangFlow checks passed"
    assert payload["checks"][0]["success"] is True
    assert payload["checks"][1] == {
        "id": "flow_listing",
        "label": "Authenticated flow listing",
        "success": True,
        "message": "Authenticated LangFlow API returned 2 flows",
    }
    assert payload["checks"][2] == {
        "id": "configured_flows",
        "label": "Configured flow existence",
        "success": False,
        "message": "Missing configured LangFlow flows: Case detail flow (tmi_case_agent), Task detail flow (tmi_task_agent)",
    }


@pytest.mark.asyncio
async def test_langflow_connection_endpoint_reports_configuration_errors_as_failed_checks(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    async def fake_get_langflow_service(_db):
        raise LangFlowConfigurationError("LangFlow base URL not configured")

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/test-connection",
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "LangFlow base URL not configured"
    assert payload["checks"] == [
        {
            "id": "connectivity",
            "label": "Connectivity",
            "success": False,
            "message": "LangFlow base URL not configured",
        },
        {
            "id": "flow_listing",
            "label": "Authenticated flow listing",
            "success": False,
            "message": "LangFlow base URL not configured",
        },
        {
            "id": "configured_flows",
            "label": "Configured flow existence",
            "success": False,
            "message": "LangFlow base URL not configured",
        },
    ]