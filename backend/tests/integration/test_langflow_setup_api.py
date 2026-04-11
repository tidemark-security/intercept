from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select, col

import app.api.routes.langflow as langflow_routes
from app.core.settings_registry import get_local
from app.models.enums import AccountType, SettingType, UserRole
from app.models.models import AppSetting, UserAccount
from app.services.langflow_service import (
    LangFlowCheckResult,
    LangFlowProvisioningResult,
    LangFlowService,
    LangFlowSummaryResult,
)
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


def test_langflow_bundled_assets_live_under_backend_static() -> None:
    asset_dir = langflow_routes._get_langflow_asset_dir()

    assert asset_dir == Path("/home/gb/projects/tmi/backend/app/static/langflow")
    assert (asset_dir / "tmi_general_purpose.json").is_file()
    assert (asset_dir / "tmi_case_agent.json").is_file()
    assert (asset_dir / "tmi_task_agent.json").is_file()
    assert (asset_dir / "tmi_alert_triage.json").is_file()
    assert (asset_dir / "tmi_rag_confluence.json").is_file()


def _find_string_values(payload: Any, needle: str) -> list[str]:
    matches: list[str] = []

    if isinstance(payload, dict):
        for value in payload.values():
            matches.extend(_find_string_values(value, needle))
        return matches

    if isinstance(payload, list):
        for item in payload:
            matches.extend(_find_string_values(item, needle))
        return matches

    if isinstance(payload, str) and payload == needle:
        matches.append(payload)

    return matches


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


async def _seed_langflow_settings(session_maker: Any) -> None:
    setting_keys = [
        "langflow.default_flow_id",
        "langflow.case_detail_flow_id",
        "langflow.task_detail_flow_id",
        "langflow.alert_triage_flow_id",
    ]
    async with session_maker() as session:
        for key in setting_keys:
            existing = (
                await session.execute(select(AppSetting).where(AppSetting.key == key))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    AppSetting(
                        key=key,
                        value=None,
                        value_type=SettingType.STRING,
                        is_secret=False,
                        description=key,
                        category="langflow",
                    )
                )
        await session.commit()


class FakeLangFlowSetupService:
    def __init__(self, existing_flows: list[dict[str, Any]] | None = None) -> None:
        self._delegate = LangFlowService(base_url="http://example.com/api/v1", api_key="test-key")
        self.existing_flows = list(existing_flows or [])
        self.created_flows: list[dict[str, Any]] = []
        self.updated_flows: list[tuple[str, dict[str, Any]]] = []
        self.projects: list[dict[str, Any]] = []
        self.created_projects: list[dict[str, Any]] = []
        self.variables: dict[str, str] = {}
        self.server_payloads: dict[str, dict[str, Any]] = {}

    def sanitize_flow_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._delegate.sanitize_flow_payload(payload)

    def flow_matches_expected(self, existing_flow: dict[str, Any], expected_flow: dict[str, Any]) -> bool:
        return self._delegate.flow_matches_expected(existing_flow, expected_flow)

    async def upsert_credential_variable(self, *, name: str, value: str) -> LangFlowProvisioningResult:
        action = "updated" if name in self.variables else "created"
        self.variables[name] = value
        return LangFlowProvisioningResult(
            action=action,
            payload={"id": f"variable-{name}", "name": name},
        )

    async def upsert_mcp_server(
        self,
        *,
        server_name: str,
        url: str,
        api_key_variable_name: str,
    ) -> LangFlowProvisioningResult:
        desired_payload = {
            "url": url,
            "headers": {"x-api-key": api_key_variable_name},
        }
        action = "updated" if server_name in self.server_payloads else "created"
        if self.server_payloads.get(server_name) == desired_payload:
            action = "reused"
        self.server_payloads[server_name] = desired_payload
        return LangFlowProvisioningResult(action=action, payload=desired_payload)

    async def list_flows(self) -> LangFlowSummaryResult:
        return LangFlowSummaryResult(
            check_result=LangFlowCheckResult(
                check_id="flow_listing",
                label="Authenticated flow listing",
                success=True,
                message=f"Authenticated LangFlow API returned {len(self.existing_flows)} flows",
            ),
            flows=list(self.existing_flows),
        )

    async def list_projects(self) -> list[dict[str, Any]]:
        return list(self.projects)

    async def create_project(self, *, name: str, description: str | None = None) -> dict[str, Any]:
        created_project = {
            "id": f"project-{len(self.created_projects) + 1}",
            "name": name,
            "description": description,
            "parent_id": None,
        }
        self.created_projects.append(created_project)
        self.projects.append(created_project)
        return created_project

    async def ensure_project(
        self,
        *,
        name: str,
        description: str | None = None,
    ) -> LangFlowProvisioningResult:
        existing = next(
            (
                project
                for project in self.projects
                if isinstance(project.get("name"), str)
                and project["name"].strip().casefold() == name.strip().casefold()
            ),
            None,
        )
        if existing is not None:
            return LangFlowProvisioningResult(action="reused", payload=existing)

        created_project = await self.create_project(name=name, description=description)
        return LangFlowProvisioningResult(action="created", payload=created_project)

    async def create_flow(self, payload: dict[str, Any]) -> dict[str, Any]:
        created_flow = {
            **payload,
            "id": f"generated-{len(self.created_flows) + 1}",
        }
        self.created_flows.append(created_flow)
        self.existing_flows.append(created_flow)
        return created_flow

    async def update_flow(self, flow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.updated_flows.append((flow_id, payload))
        for index, flow in enumerate(self.existing_flows):
            if flow.get("id") == flow_id:
                updated_flow = {**flow, **payload}
                self.existing_flows[index] = updated_flow
                return updated_flow

        raise AssertionError(f"Unknown flow id {flow_id}")

    async def close(self) -> None:
        await self._delegate.close()


@pytest.mark.asyncio
async def test_langflow_setup_endpoint_requires_admin_role(
    client: AsyncClient,
    session_maker: Any,
    analyst_user_factory,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, analyst_user_factory)

    response = await client.post(
        "/api/v1/langflow/admin/setup-intercept-mcp",
        json={"backend_api_base_url": "http://localhost:8000/api/v1"},
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_langflow_setup_endpoint_provisions_nhi_key_server_and_flow_settings(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, admin_user_factory)
    await _seed_langflow_settings(session_maker)

    fake_service = FakeLangFlowSetupService()

    async def fake_get_langflow_service(_db):
        return fake_service

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/admin/setup-intercept-mcp",
        json={"backend_api_base_url": "http://localhost:8000/api/v1"},
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Intercept MCP server setup completed"
    assert payload["nhi_username"] == "tidemark_ai"
    assert payload["variable_name"] == "intercept_api_key"
    assert payload["mcp_server_name"] == "intercept"
    assert payload["mcp_server_url"] == "http://localhost:8000/mcp/sse"
    assert payload["api_key"]["prefix"]
    assert "key" not in payload["api_key"]
    assert payload["warnings"] == []
    assert any(step["id"] == "langflow_project" for step in payload["steps"])
    assert set(payload["flow_assignments"].keys()) == {
        "langflow.default_flow_id",
        "langflow.case_detail_flow_id",
        "langflow.task_detail_flow_id",
        "langflow.alert_triage_flow_id",
    }
    assert len(fake_service.created_flows) == 5
    assert len(fake_service.created_projects) == 1
    assert fake_service.created_projects[0]["name"] == "Intercept"
    project_id = fake_service.created_projects[0]["id"]
    assert all(flow["folder_id"] == project_id for flow in fake_service.created_flows)
    assert not any(
        _find_string_values(flow, "http://host.docker.internal:8000/mcp/sse")
        for flow in fake_service.created_flows
    )
    assert any(
        _find_string_values(flow, "http://localhost:8000/mcp/sse")
        for flow in fake_service.created_flows
    )
    assert fake_service.server_payloads == {
        "intercept": {
            "url": "http://localhost:8000/mcp/sse",
            "headers": {"x-api-key": "intercept_api_key"},
        }
    }

    async with session_maker() as session:
        nhi_user = (
            await session.execute(
                select(UserAccount).where(col(UserAccount.username) == "tidemark_ai")
            )
        ).scalar_one_or_none()
        assert nhi_user is not None
        assert nhi_user.account_type == AccountType.NHI
        assert nhi_user.role == UserRole.ANALYST

        settings = (
            await session.execute(
                select(AppSetting).where(
                    AppSetting.key.in_(
                        [
                            "langflow.default_flow_id",
                            "langflow.case_detail_flow_id",
                            "langflow.task_detail_flow_id",
                            "langflow.alert_triage_flow_id",
                        ]
                    )
                )
            )
        ).scalars().all()

    assert {setting.key: setting.value for setting in settings} == payload["flow_assignments"]


@pytest.mark.asyncio
async def test_langflow_setup_endpoint_creates_missing_flow_settings(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, admin_user_factory)

    fake_service = FakeLangFlowSetupService()

    async def fake_get_langflow_service(_db):
        return fake_service

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/admin/setup-intercept-mcp",
        json={"backend_api_base_url": "http://localhost:8000/api/v1"},
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    async with session_maker() as session:
        settings = (
            await session.execute(
                select(AppSetting).where(
                    AppSetting.key.in_(
                        [
                            "langflow.default_flow_id",
                            "langflow.case_detail_flow_id",
                            "langflow.task_detail_flow_id",
                            "langflow.alert_triage_flow_id",
                        ]
                    )
                )
            )
        ).scalars().all()

    assert {setting.key: setting.value for setting in settings} == payload["flow_assignments"]


@pytest.mark.asyncio
async def test_langflow_setup_endpoint_warns_on_drifted_existing_flow_without_overwrite(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, admin_user_factory)
    await _seed_langflow_settings(session_maker)

    fake_service = FakeLangFlowSetupService(
        existing_flows=[
            {
                "id": "existing-general",
                "endpoint_name": "tmi_general_purpose",
                "name": "Customized General Flow",
                "description": "Customized",
                "data": {"nodes": []},
                "tags": [],
                "locked": None,
                "mcp_enabled": True,
                "is_component": False,
                "webhook": False,
            }
        ]
    )

    async def fake_get_langflow_service(_db):
        return fake_service

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/admin/setup-intercept-mcp",
        json={"backend_api_base_url": "http://localhost:8000/api/v1"},
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "Intercept MCP server setup completed with warnings"
    assert payload["flow_assignments"]["langflow.default_flow_id"] == "existing-general"
    assert len(payload["warnings"]) == 1
    assert "was not overwritten" in payload["warnings"][0]
    assert all(flow["endpoint_name"] != "tmi_general_purpose" for flow in fake_service.created_flows)
    assert len(fake_service.created_flows) == 4


@pytest.mark.asyncio
async def test_langflow_setup_endpoint_assigns_existing_matching_flow_to_intercept_project(
    client: AsyncClient,
    session_maker: Any,
    admin_user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cookie = await _login_and_get_session_cookie(client, session_maker, admin_user_factory)
    await _seed_langflow_settings(session_maker)

    asset_path = langflow_routes._get_langflow_asset_dir() / "tmi_general_purpose.json"
    raw_asset = json.loads(asset_path.read_text(encoding="utf-8"))
    transformed_asset = langflow_routes._replace_cached_intercept_mcp_server_url(
        raw_asset,
        "http://localhost:8000/mcp/sse",
    )

    fake_service = FakeLangFlowSetupService(
        existing_flows=[
            {
                **LangFlowService(base_url="http://example.com/api/v1", api_key="test-key").sanitize_flow_payload(transformed_asset),
                "id": "existing-general",
                "folder_id": None,
            }
        ]
    )

    async def fake_get_langflow_service(_db):
        return fake_service

    monkeypatch.setattr(langflow_routes, "get_langflow_service", fake_get_langflow_service)

    response = await client.post(
        "/api/v1/langflow/admin/setup-intercept-mcp",
        json={"backend_api_base_url": "http://localhost:8000/api/v1"},
        cookies={get_local("auth.session.cookie_name"): session_cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["warnings"] == []
    assert payload["flow_assignments"]["langflow.default_flow_id"] == "existing-general"
    assert len(fake_service.updated_flows) == 1
    updated_flow_id, updated_payload = fake_service.updated_flows[0]
    assert updated_flow_id == "existing-general"
    assert updated_payload == {"folder_id": "project-1"}
    assert fake_service.existing_flows[0]["folder_id"] == "project-1"
    general_step = next(step for step in payload["steps"] if step["id"] == "flow:tmi_general_purpose")
    assert general_step["status"] == "updated"
    assert "assigned it to project 'Intercept'" in general_step["message"]
